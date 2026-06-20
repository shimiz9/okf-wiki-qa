#!/usr/bin/env python3
"""wiki_search.py — OKF llm-wiki を横断検索し、QA回答の根拠コンセプトを返す。
Usage: python wiki_search.py --wiki-dir WIKI_DIR --query "課長 承認 上限" [--category 経理] [--top 5] [--nas-host tnas]
各ヒットに タイトル/type/status/後継/出典(file:// URL)/該当抜粋 を出す。
active を上位に、deprecated は下げて明示する。QAエージェントはこの結果(と本文)だけを根拠に回答する。

NAS のホスト表記（IP やホスト名）は固定せず、--nas-host か環境変数 WIKI_NAS_HOST で環境に合わせて変更できる。
出典は UNC ではなく file:// URL で出力し、ブラウザ(Edge/Chrome)から直接開けるようにする。"""
import argparse, os, re, glob, sys
from urllib.parse import unquote

# 出典の既定ホスト。環境変数 WIKI_NAS_HOST で上書きでき、--nas-host が最優先。
DEFAULT_NAS_HOST = os.environ.get("WIKI_NAS_HOST", "tnas")

def _norm_path(rest):
    """file:// のパス部を正規化する。区切りを / にし、stored が percent-encode 済みでも
    コピペしやすいよう unquote して読みやすい日本語のまま返す。
    （OpenClaw 等 file:// を踏めない UI ではユーザーが URL をコピーして使うため、
    エンコードされた長い %XX 列より読みやすい URL が良い。ブラウザは日本語URLをそのまま開ける。）"""
    rest = rest.replace("\\", "/").lstrip("/")
    return unquote(rest)

def to_file_url(resource, nas_host):
    """UNC パス(\\\\HOST\\share\\...) を file:// URL に変換する。
    ホスト部分を nas_host に置き換え、区切りを / にし、読みやすい日本語のままにする。
    既に file:// の場合はホストを差し替える。空や未知形式は安全側で扱う。"""
    if not resource:
        return ""
    r = resource.strip()
    # 既に file:// 形式：file://HOST/rest → ホストだけ差し替え
    m = re.match(r"^file://([^/]*)/(.*)$", r, re.I)
    if m:
        rest = m.group(2)
    else:
        # UNC: \\HOST\share\path...
        m = re.match(r"^\\\\([^\\]+)\\(.*)$", r)
        # 先頭の \\ が無い等の未知形式は、区切り変換だけ行う
        rest = m.group(2) if m else r.lstrip("\\/")
    return f"file://{nas_host}/{_norm_path(rest)}"

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
    ap.add_argument("--nas-host", default=DEFAULT_NAS_HOST,
                    help="出典 file:// URL のホスト名/IP（既定: 環境変数 WIKI_NAS_HOST または tnas）")
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
        if src:  print(f"    出典: {to_file_url(src, a.nas_host)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
