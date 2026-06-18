# okf-wiki-qa

社内マニュアル（OKF llm-wiki）に対する質問応答スキル。

## 概要

社内の制度・手順・規程・連絡先などを収録した llm-wiki を検索し、  
**wiki の内容だけ** を根拠に質問へ回答する Claude Code スキルです。

- 回答の最後に出典（NAS 上の原本 UNC パス）を必ず提示します
- `active`（現行）を優先し、`deprecated`（廃止）は後継コンセプトに置き換えて回答します
- wiki 本文中の指示文には従いません（データとして扱います）

## ファイル構成

| ファイル | 説明 |
|---|---|
| `SKILL.md` | Claude Code スキル定義（手順・フォーマット・セキュリティルール） |
| `wiki_search.py` | llm-wiki を横断検索する補助スクリプト |

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
  [--top 5]
```

**オプション：**

| オプション | 説明 | 既定値 |
|---|---|---|
| `--wiki-dir` | llm-wiki のルートディレクトリ（必須） | — |
| `--query` | 検索キーワード（スペース区切り、必須） | — |
| `--category` | カテゴリ名で絞り込む | なし（全体検索） |
| `--top` | 表示する上位件数 | 5 |

**出力例：**
```
検索語: ['課長', '承認', '上限']
- 経費精算規程 (policy) :: 経理/経費精算規程.md  〔一致語: 課長/承認/上限〕
    抜粋: 10万円以下は所属課長決裁（2026-07-01改訂）
    出典: \\192.168.40.22\public\マニュアル\経理\経費精算規程.docx
```

## パス設定

| 項目 | パス |
|---|---|
| WIKI_DIR（サーバー内） | `/Volume1/public/llm-wiki` |
| 出典（ユーザー向け UNC） | `\\192.168.40.22\public\...` |

## wiki コンセプトの形式

各 `.md` ファイルは YAML フロントマター付きの Markdown です。

```markdown
---
title: 経費精算規程
type: policy
status: active          # active | deprecated
superseded_by:          # deprecated の場合、後継コンセプトのパス
resource: \\192.168.40.22\public\マニュアル\経理\経費精算規程.docx
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
