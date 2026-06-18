#!/usr/bin/env python3
"""wiki_search.py — OKF llm-wiki を横断検索し、QA回答の根拠コンセプトを返す。
Usage: python wiki_search.py --wiki-dir WIKI_DIR --query "課長 承認 上限" [--category 経理] [--top 5]
各ヒットに タイトル/type/status/後継/出典UNC/該当抜粋 を出す。
active を上位に、deprecated は下げて明示する。QAエージェントはこの結果(と本文)だけを根拠に回答する。"""
import argparse, os, re, glob, sys

def parse(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    fmraw, body = (m.group(1), m.group(2)) if m else ("", text)
    d = {}
    for line in fmraw.splitlines():
        mm = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if mm: d[mm.group(1)] = mm.group(2).strip()
    return d, body

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki-dir", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--category", default=None)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    root = a.wiki_dir if not a.category else os.path.join(a.wiki_dir, a.category)
    terms = [t for t in re.split(r"[\s　]+", a.query.strip()) if t]
    hits = []
    for p in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, a.wiki_dir).replace("\\", "/")
        if os.path.basename(p) in ("index.md", "log.md"): continue
        d, body = parse(open(p, encoding="utf-8").read())
        title = d.get("title", os.path.basename(p)[:-3])
        hay = f"{title}\n{d.get('description','')}\n{d.get('tags','')}\n{body}"
        score = 0; matched = []
        for t in terms:
            c = hay.count(t)
            if c: matched.append(t)
            score += c + (title.count(t) * 5)
        if score <= 0: continue
        if d.get("status") == "deprecated": score -= 3   # 現行を優先
        snip = ""
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and any(t in s for t in terms):
                snip = re.sub(r"\s+", " ", s)[:90]; break
        hits.append((score, rel, title, d.get("type",""), d.get("status","active"),
                     d.get("superseded_by",""), d.get("resource",""), snip, matched))
    hits.sort(key=lambda x: -x[0])
    if not hits:
        print("該当なし。wiki にこの話題のコンセプトが見つからない。"); return 0
    print(f"検索語: {terms}")
    for sc, rel, title, typ, st, sby, src, snip, matched in hits[:a.top]:
        tag = f"  [{st}]" if st != "active" else ""
        print(f"- {title}{tag} ({typ}) :: {rel}  〔一致語: {'/'.join(matched)}〕")
        if sby:  print(f"    後継: {sby}")
        if snip: print(f"    抜粋: {snip}")
        if src:  print(f"    出典: {src}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
