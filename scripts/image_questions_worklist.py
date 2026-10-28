"""列出还没结构化的图片题（无 answer/slots），并带出解析文件里给出的答案。

用法：
    python -X utf8 scripts/image_questions_worklist.py            # 全部剩余
    python -X utf8 scripts/image_questions_worklist.py --limit 10 # 只看前 10 道
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_answer_lines():
    path = ROOT / "SC-200_全题库解析.txt"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out = {}
    for block in re.split(r"-{20,}\n(?=第 \d+ 题)", text):
        m = re.search(r"\[ID: ([^\]]+)\]", block)
        if not m:
            continue
        a = re.search(r"【正确答案】(.+?)\n", block)
        out[m.group(1)] = a.group(1).strip() if a else ""
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    bank = json.loads((ROOT / "data/question-bank.json").read_text(encoding="utf-8"))
    answers = load_answer_lines()
    pending = [q for q in bank["questions"] if not q.get("answer") and not q.get("slots")]
    pending.sort(key=lambda q: (int(q["id"].split("-")[0][1:]), q["number"]))

    total = len(pending)
    shown = pending[: args.limit] if args.limit else pending
    for q in shown:
        blanks = len(re.findall(r"空\d+\s*=", answers.get(q["id"], "")))
        print(f"{q['id']}\t{q['type']}\t空白数={blanks}")
        print(f"    解析答案: {answers.get(q['id'], '')[:120]}")
        print(f"    答案图: {', '.join(q.get('answer_assets') or [])}")
    print(f"\n剩余 {total} 道（本次列出 {len(shown)} 道）")


if __name__ == "__main__":
    main()
