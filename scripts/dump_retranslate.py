"""导出待重译题目的英文原文（供人工/AI 重译）。

用法：
    python -X utf8 scripts/dump_retranslate.py [起始] [数量] [主题号]

不传主题号时按全库顺序取；传主题号（如 3）只在该主题内取。
只看 translation_status 仍为 machine 的题。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
bank = json.loads((DATA / "question-bank.json").read_text(encoding="utf-8"))
overrides = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))

start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
topic = sys.argv[3] if len(sys.argv) > 3 else None

todo = [q for q in bank["questions"] if q.get("translation_status") == "machine"]
if topic:
    todo = [q for q in todo if str(q["topic"]) == topic]

print(f"# 待重译 {len(todo)} 题 | 本次显示 {start}..{min(start + count, len(todo))}")
for q in todo[start : start + count]:
    ov = overrides.get(q["id"], {})
    print(f"\n===== {q['id']} | {q['type']} | 第 {q['pages']} 页")
    print("EN:", q.get("en", "").strip())
    if q.get("case_en"):
        print("CASE_EN:", q["case_en"].strip()[:200], "..." if len(q["case_en"]) > 200 else "")
    for op in q.get("options") or []:
        print(f"  opt {op['id']}: {op.get('en', '').strip()}")
    for s in q.get("slots") or []:
        print(
            f"  slot {s.get('id')}: "
            + " | ".join(f"{x['id']}={x.get('en', '').strip()}" for x in s.get("options") or [])
        )
    if ov:
        print("  (overrides 现有键:", sorted(ov.keys()), ")")
