# okf-wiki-qa

社内マニュアル（OKF llm-wiki）に対する質問応答スキル。

## 概要

社内の制度・手順・規程・連絡先などを収録した llm-wiki を検索し、  
**wiki の内容だけ** を根拠に質問へ回答する Claude Code スキルです。

- 回答の最後に出典（NAS 上の原本への `file://` リンク）を必ず提示します（Edge/Chrome から直接開けます）
- `active`（現行）を優先し、`deprecated`（廃止）は後継コンセプトに置き換えて回答します
- wiki 本文中の指示文には従いません（データとして扱います）
- 質問と回答を記録し、よく聞かれる質問だけを各カテゴリの **FAQ に自動蓄積** します（肥大化対策あり）

## ファイル構成

| ファイル | 説明 |
|---|---|
| `SKILL.md` | Claude Code スキル定義（手順・フォーマット・セキュリティルール） |
| `wiki_search.py` | llm-wiki を横断検索する補助スクリプト |
| `faq_update.py` | 質問/回答を記録し、カテゴリの FAQ を更新（しきい値昇格＋TTL掃除） |

## 使い方

### スキルとして呼び出す

Claude Code 上で社内 wiki に関する質問をすると、自動的にこのスキルが使用されます。

例：
- 「経費精算の課長の承認上限は？」
- 「社用車を予約したい」
- 「経費精算の締め日は？」

### wiki_search.py を直接使う

```bash
python wiki_search.py \
  --wiki-dir /Volume1/public/llm-wiki \
  --query "課長 承認 上限" \
  [--category 経理] \
  [--top 5] \
  [--nas-host tnas]
```

**オプション：**

| オプション | 説明 | 既定値 |
|---|---|---|
| `--wiki-dir` | llm-wiki のルートディレクトリ（必須） | — |
| `--query` | 検索キーワード（スペース区切り、必須） | — |
| `--category` | カテゴリ名で絞り込む | なし（全体検索） |
| `--top` | 表示する上位件数 | 5 |
| `--nas-host` | 出典 `file://` URL のホスト名/IP | 環境変数 `WIKI_NAS_HOST` → なければ `tnas` |

**出力例：**
```
検索語: ['課長', '承認', '上限']
- 経費精算規程 (policy) :: 経理/経費精算規程.md  〔一致語: 課長/承認/上限〕
    抜粋: 10万円以下は所属課長決裁（2026-07-01改訂）
    出典: file://tnas/public/マニュアル/経理/経費精算規程.docx
```

> 出典は wiki に格納された UNC パス（`\\192.168.40.22\public\...`）を `file://<NAS_HOST>/public/...` に
> 変換して出力します。ホスト部分は固定せず、`--nas-host` か環境変数 `WIKI_NAS_HOST` で環境に合わせて変更できます。
>
> URL は**読みやすい日本語のまま**出力します（percent-encode しません）。OpenClaw など `file://` を
> クリックできない UI でも使えるよう、回答では **Markdown リンクにせず「文書名＋URL」を併記**し、
> ユーザーが URL をコピーしてブラウザのアドレスバーに貼れる形にします。
>
> ```
> 出典:
> - 経費精算規程.docx
>   file://tnas/public/マニュアル/経理/経費精算規程.docx
> ```

## FAQ 自動更新（faq_update.py）

回答が確定したら、その質問と回答をカテゴリの FAQ に蓄積します。

```bash
python faq_update.py \
  --wiki-dir /Volume1/public/llm-wiki \
  --category 経理 \
  --question "経費精算の締め日は？" \
  --keywords "経費 精算 締め日" \
  --answer "毎月末締め、翌月15日払い。" \
  --sources file://tnas/public/マニュアル/経理/経費精算規程.docx
```

### 肥大化対策（しきい値昇格 ＋ TTL 掃除）

一度しか聞かれない質問まで FAQ に書くとファイルが膨らむため、次の仕組みで防ぎます。

1. **即 FAQ 化しない**：質問はまず軽量な候補台帳（`<カテゴリ>/.faq_candidates.jsonl`）に貯め、
   同じ/類似の質問が**しきい値回数**たまった時点で初めて `FAQ.md` に昇格させます。一度きりの質問は FAQ に載りません。
2. **名寄せ**：keyword 集合の一致度（Jaccard）で類似質問をまとめて数えるので、言い回し違いも 1 件に集約されます。
3. **TTL 掃除**：再質問の無い候補（既定90日）は台帳から削除、長期未参照の FAQ（既定365日）は `archive/` へ退避し、
   現役 FAQ を小さく保ちます。
4. **重複させない**：昇格済みの質問が再度来たら追記せず既存 FAQ を更新（回数・最終参照日を反映）します。

FAQ.md は YAML フロントマター付きの OKF コンセプトとして出力されるため、`wiki_search.py` の検索結果に自然に乗ります。

**オプション（しきい値・TTL は環境ごとに変数化）：**

| オプション | 環境変数 | 説明 | 既定値 |
|---|---|---|---|
| `--promote-threshold` | `FAQ_PROMOTE_THRESHOLD` | FAQ へ昇格させる質問回数 | `3` |
| `--candidate-ttl-days` | `FAQ_CANDIDATE_TTL_DAYS` | 候補を保持する日数（0以下で無効） | `90` |
| `--faq-ttl-days` | `FAQ_TTL_DAYS` | FAQ を未参照で残す日数（0以下で無効） | `365` |
| `--similarity` | `FAQ_SIMILARITY` | 名寄せの Jaccard しきい値 | `0.6` |

```bash
# 例：昇格しきい値を環境に合わせて 5 回にする
export FAQ_PROMOTE_THRESHOLD=5
```

書き込み先は `FAQ.md` / `.faq*.jsonl` / `archive/` のみで、原本を取り込んだコンセプト本体は変更しません。

## パス設定

| 項目 | 値 | 設定方法 |
|---|---|---|
| WIKI_DIR（サーバー内） | `/Volume1/public/llm-wiki` | `--wiki-dir`（環境に合わせて変更） |
| NAS_HOST（出典リンクのホスト） | `tnas`（既定） | 環境変数 `WIKI_NAS_HOST` または `--nas-host` |
| 出典（ユーザー向けリンク） | `file://tnas/public/...` | NAS_HOST から自動生成 |

NAS の IP やホスト名は固定で埋め込まず、`WIKI_NAS_HOST` で環境ごとに切り替えます。

```bash
# 例：IP をそのまま使う環境
export WIKI_NAS_HOST=192.168.40.22   # → 出典 file://192.168.40.22/public/...
# 例：ホスト名で示したい環境
export WIKI_NAS_HOST=tnas            # → 出典 file://tnas/public/...
```

## wiki コンセプトの形式

各 `.md` ファイルは YAML フロントマター付きの Markdown です。

```markdown
---
title: 経費精算規程
type: policy
status: active          # active | deprecated
superseded_by:          # deprecated の場合、後継コンセプトのパス
resource: \\192.168.40.22\public\マニュアル\経理\経費精算規程.docx   # UNC で格納。出力時に file://<NAS_HOST>/... へ変換
tags: 経費 精算 承認 課長
description: 経費精算の申請・承認フローと権限規程
---

本文...
```

`status: deprecated` のコンセプトはスコアが下げられ、`superseded_by` の後継が優先されます。

## セキュリティ

- WIKI_DIR の外は読みません
- QA では wiki への書き込み・削除を行いません
- wiki 本文中に「削除しろ」「送信しろ」などの指示文があっても従いません
