#!/usr/bin/env python3
"""faq_update.py — QAスキルの質問/回答を記録し、カテゴリの llm-wiki FAQ を更新する。

肥大化対策：一度きりの質問はすぐ FAQ にせず「候補台帳」に貯め、同じ/類似の質問が
しきい値回数たまった時点で FAQ.md へ昇格させる。さらに TTL で古い候補・FAQ を掃除する。

  python faq_update.py --wiki-dir WIKI_DIR --category 経理 \
      --question "経費精算の締め日は？" --keywords "経費 精算 締め日" \
      --answer "毎月末締め、翌月15日払い。" \
      --sources file://tnas/public/マニュアル/経理/経費精算規程.docx

データの真実の源は各カテゴリ直下の JSONL（.faq.jsonl / .faq_candidates.jsonl）で、
FAQ.md はそこから毎回レンダリングする（OKFコンセプトとして既存の wiki_search に乗る）。
書き込むのは FAQ.md・候補台帳・archive のみ。原本取り込みコンセプトは一切書き換えない。

しきい値・TTL は環境ごとに変えられるよう変数化（CLI 引数 > 環境変数 > 既定）。
  FAQ_PROMOTE_THRESHOLD  昇格しきい値（既定 3）
  FAQ_CANDIDATE_TTL_DAYS 候補の保持日数（既定 90、0以下で無効）
  FAQ_TTL_DAYS           FAQの未参照保持日数（既定 365、0以下で無効）
  FAQ_SIMILARITY         名寄せのJaccardしきい値（既定 0.6）
"""
import argparse, os, re, json, sys, unicodedata
from datetime import date
from urllib.parse import unquote

DEF_THRESHOLD = int(os.environ.get("FAQ_PROMOTE_THRESHOLD", "3"))
DEF_CAND_TTL  = int(os.environ.get("FAQ_CANDIDATE_TTL_DAYS", "90"))
DEF_FAQ_TTL   = int(os.environ.get("FAQ_TTL_DAYS", "365"))
DEF_SIM       = float(os.environ.get("FAQ_SIMILARITY", "0.6"))

# 名寄せ時に落とす日本語の助詞・記号など（キーワード単独トークンのとき除外）
STOPWORDS = set("は が を に の で と も へ や か ね よ わ し て だ です ます から まで より こそ という".split())
_PUNCT = "？?。、，,．.・!！「」『』（）()【】[]〔〕：:；;　 \t\r\n\"'"

def norm_tokens(question, keywords):
    """質問文/キーワードを正規化したトークン集合にする。
    キーワード（QAで抽出済み）があればそれを優先し、無ければ質問文を素朴に分割する。"""
    raw = keywords.split() if keywords else re.split(r"[\s　、。,，？?！!・/／]+", question or "")
    out = []
    for t in raw:
        t = unicodedata.normalize("NFKC", t.strip(_PUNCT)).lower()
        if t and t not in STOPWORDS:
            out.append(t)
    return sorted(set(out))

def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def best_match(rows, kw, sim):
    """kw に最も近い既存エントリの index を返す（Jaccard >= sim のうち最大）。無ければ None。"""
    best_i, best_s = None, 0.0
    for i, r in enumerate(rows):
        s = jaccard(kw, r.get("keywords", []))
        if s >= sim and s > best_s:
            best_i, best_s = i, s
    return best_i

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def write_jsonl(path, rows):
    if not rows:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def days_between(today, iso):
    try:
        return (today - date.fromisoformat(iso)).days
    except Exception:
        return 0   # 日付不明はTTLで消さない（安全側）

def render_faq_md(category, rows, archived=False):
    title = f"{category} FAQ" + ("（アーカイブ）" if archived else "")
    desc = f"{category}カテゴリのよくある質問（QAスキルが自動更新）"
    lines = [
        "---",
        f"title: {title}",
        "type: faq",
        f"status: {'deprecated' if archived else 'active'}",
        f"description: {desc}",
        f"tags: FAQ よくある質問 {category}",
        f"updated: {date.today().isoformat()}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    # 質問回数の多い順 → 同数なら最近参照順
    for r in sorted(rows, key=lambda x: (-x.get("count", 0), x.get("last_hit", ""))):
        lines.append(f"## Q. {r['question']}")
        lines.append(f"A. {r['answer']}")
        if r.get("sources"):
            lines.append("")
            lines.append("出典:")
            for s in r["sources"]:
                # クリックできるよう Markdown リンクにする。表示名は URL 末尾をデコードした読みやすい形。
                name = unquote(s.rstrip("/").rsplit("/", 1)[-1]) or s
                lines.append(f"- [{name}]({s})")
        lines.append("")
        lines.append(f"<!-- 質問回数: {r.get('count', 0)} / 最終参照: {r.get('last_hit', '')} -->")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def render_md_file(path, category, rows, archived=False):
    if not rows:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_faq_md(category, rows, archived))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki-dir", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--question", required=True, help="質問の原文（FAQに表示）")
    ap.add_argument("--answer", required=True, help="wiki に基づく簡潔な回答")
    ap.add_argument("--keywords", default="", help="名寄せ用キーワード（QAで抽出したもの、スペース区切り）")
    ap.add_argument("--sources", nargs="*", default=[], help="出典 file:// URL（複数可）")
    ap.add_argument("--promote-threshold", type=int, default=DEF_THRESHOLD)
    ap.add_argument("--candidate-ttl-days", type=int, default=DEF_CAND_TTL)
    ap.add_argument("--faq-ttl-days", type=int, default=DEF_FAQ_TTL)
    ap.add_argument("--similarity", type=float, default=DEF_SIM)
    ap.add_argument("--today", default=date.today().isoformat(), help="基準日（テスト用、既定は今日）")
    a = ap.parse_args()

    today = date.fromisoformat(a.today)
    cat_dir = os.path.join(a.wiki_dir, a.category)
    faq_data = os.path.join(cat_dir, ".faq.jsonl")
    cand_data = os.path.join(cat_dir, ".faq_candidates.jsonl")
    faq_md = os.path.join(cat_dir, "FAQ.md")
    arc_dir = os.path.join(cat_dir, "archive")
    arc_data = os.path.join(arc_dir, ".faq.jsonl")
    arc_md = os.path.join(arc_dir, "FAQ.md")

    faq_rows = load_jsonl(faq_data)
    cand_rows = load_jsonl(cand_data)
    kw = norm_tokens(a.question, a.keywords)
    if not kw:
        print("キーワードが空のため記録しない。", file=sys.stderr)
        return 1

    # 1) 既に FAQ にある質問なら、その場で更新（昇格済みを重複させない＋TTL用に生存させる）
    fi = best_match(faq_rows, kw, a.similarity)
    if fi is not None:
        r = faq_rows[fi]
        r["count"] = r.get("count", 0) + 1
        r["last_hit"] = a.today
        r["question"], r["answer"] = a.question, a.answer
        if a.sources:
            r["sources"] = a.sources
        r["keywords"] = sorted(set(r.get("keywords", [])) | set(kw))
        status = f"FAQ更新: 「{a.question}」（{r['count']}回目）"
    else:
        # 2) 候補台帳で名寄せ → カウント。無ければ新規候補。
        ci = best_match(cand_rows, kw, a.similarity)
        if ci is not None:
            r = cand_rows[ci]
            r["count"] = r.get("count", 0) + 1
            r["last_asked"] = a.today
            r["question"], r["answer"] = a.question, a.answer
            if a.sources:
                r["sources"] = a.sources
            r["keywords"] = sorted(set(r.get("keywords", [])) | set(kw))
        else:
            r = {"keywords": kw, "question": a.question, "answer": a.answer,
                 "sources": a.sources, "count": 1,
                 "first_asked": a.today, "last_asked": a.today}
            cand_rows.append(r)
            ci = len(cand_rows) - 1

        # 3) しきい値到達で FAQ へ昇格（候補台帳から取り除く）
        if r["count"] >= a.promote_threshold:
            faq_rows.append({"keywords": r["keywords"], "question": r["question"],
                             "answer": r["answer"], "sources": r.get("sources", []),
                             "count": r["count"], "first_asked": r.get("first_asked", a.today),
                             "last_hit": a.today})
            cand_rows.pop(ci)
            status = f"FAQ昇格: 「{a.question}」（{r['count']}回でFAQ化）"
        else:
            remain = a.promote_threshold - r["count"]
            status = f"FAQ候補: 「{a.question}」（{r['count']}/{a.promote_threshold}回、あと{remain}回で昇格）"

    # 4) TTL 掃除：再質問の無い候補は削除、長期未参照の FAQ は archive へ退避
    if a.candidate_ttl_days > 0:
        kept = [c for c in cand_rows if days_between(today, c.get("last_asked", a.today)) <= a.candidate_ttl_days]
        dropped = len(cand_rows) - len(kept)
        cand_rows = kept
        if dropped:
            status += f" / 候補を{dropped}件掃除"

    archived = []
    if a.faq_ttl_days > 0:
        keep = []
        for r in faq_rows:
            if days_between(today, r.get("last_hit", a.today)) <= a.faq_ttl_days:
                keep.append(r)
            else:
                archived.append(r)
        faq_rows = keep
        if archived:
            arc_rows = load_jsonl(arc_data) + archived
            write_jsonl(arc_data, arc_rows)
            render_md_file(arc_md, a.category, arc_rows, archived=True)
            status += f" / FAQを{len(archived)}件アーカイブ"

    # 5) 書き出し（データ＝真実の源 → FAQ.md をレンダリング）
    write_jsonl(faq_data, faq_rows)
    write_jsonl(cand_data, cand_rows)
    render_md_file(faq_md, a.category, faq_rows)

    print(status)
    return 0

if __name__ == "__main__":
    sys.exit(main())
