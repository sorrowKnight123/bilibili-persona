#!/usr/bin/env python3
"""Score one ASR hypothesis against a hand-corrected gold text.

Two numbers, because they answer different questions:
  CER       -- overall character error rate (what benchmarks report)
  term hit  -- how many of the course's technical terms came out right (what we care about)

    python bench/score_asr.py gold.txt hyp.txt --terms terms.txt --label "whisper raw"

Normalisation drops whitespace and punctuation, keeping CJK + Latin + digits: the standard
CER convention, which stops the score from being dominated by comma placement.

Term hit is a substring test on the normalised text -- a term counts as hit if it appears
anywhere. That answers "was the term spelled right", not "was it used in the right place".
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

KEEP = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf0-9a-zA-Z]")


def norm(text: str) -> str:
    return "".join(KEEP.findall(unicodedata.normalize("NFKC", text).lower()))


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def selftest() -> int:
    assert norm("Ａ Ｂ，c！") == "abc"
    assert edit_distance("abc", "abd") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "abc") == 0
    print("[ok] score_asr self-test passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gold", nargs="?", help="hand-corrected reference text")
    ap.add_argument("hyp", nargs="?", help="ASR output to score")
    ap.add_argument("--terms", help="one technical term per line")
    ap.add_argument("--label", default="", help="name shown in the report")
    ap.add_argument("--selftest", action="store_true", help="check the scorer itself and exit")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.gold or not args.hyp:
        ap.error("gold and hyp are required (or use --selftest)")

    gold, hyp = norm(Path(args.gold).read_text(encoding="utf-8")), norm(Path(args.hyp).read_text(encoding="utf-8"))
    dist = edit_distance(gold, hyp)
    cerr = dist / len(gold) if gold else 0.0

    print(f"[{args.label or Path(args.hyp).stem}]")
    print(f"  chars  gold={len(gold)}  hyp={len(hyp)}")
    print(f"  CER    {cerr * 100:.2f}%   (edit={dist})")

    if args.terms:
        terms = [t.strip() for t in Path(args.terms).read_text(encoding="utf-8").splitlines() if t.strip()]
        hit = [t for t in terms if norm(t) in hyp]
        miss = [t for t in terms if t not in hit]
        print(f"  terms  {len(hit)}/{len(terms)} = {len(hit) / len(terms) * 100:.0f}%")
        print(f"    hit : {'、'.join(hit) if hit else '(none)'}")
        print(f"    miss: {'、'.join(miss) if miss else '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
