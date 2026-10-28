"""导出单题的全量英文原文 + 现有中文（供人工/AI 重译reviewed 题）。

用法：
    python -X utf8 scripts/dump_full.py [起始] [数量] [主题号] [--all]

默认只列"机翻腔"的 reviewed 题（题干含「您」、多余空格、机翻词，或案例含「您」）。
加 --all 则列出全部 reviewed 题。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
bank = json.loads((DATA / "question-bank.json").read_text(encoding="utf-8"))
overrides = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))

args = [a for a in sys.argv[1:] if not a.startswith("--")]
show_all = "--all" in sys.argv
start = int(args[0]) if len(args) > 0 else 0
count = int(args[1]) if len(args) > 1 else 10
topic = args[2] if len(args) > 2 else None

PAT_YOU = re.compile("您")
PAT_SPACE = re.compile(r"(设备|用户|规则|组|服务器|计算机|域|站点|工作区)\s+\d")
PAT_ISM = re.compile(r"(想要|希望您|对您|您的|请确保您|以下哪项|下列哪项|进行一个|作出一个)")


def mt_flags(q):
    t = q.get("zh", "") or ""
    c = (q.get("case_zh", "") or "")[:3000]
    f = []
    if PAT_YOU.search(t):
        f.append("题干含您")
    if PAT_SPACE.search(t):
        f.append("题干多余空格")
    if PAT_ISM.search(t):
        f.append("题干机翻词")
    if PAT_YOU.search(c):
        f.append("案例含您")
    return f


todo = [q for q in bank["questions"] if q.get("translation_status") != "machine"]
if not show_all:
    todo = [q for q in todo if mt_flags(q)]
if topic:
    todo = [q for q in todo if str(q["topic"]) == topic]

print(f"# 候选 {len(todo)} 题 | 本次显示 {start}..{min(start + count, len(todo))}")
print("# 全库题号顺序：" + " ".join(q["id"] for q in todo))
for q in todo[start : start + count]:
    ov = overrides.get(q["id"], {})
    print(f"\n===== {q['id']} | {q['type']} | 第 {q['pages']} 页 | overrides键 {sorted(ov.keys())}")
    print("EN:", q.get("en", "").strip())
    print("ZH:", (q.get("zh", "") or "").strip())
    if q.get("case_en"):
        print("CASE_EN:", q["case_en"].strip()[:400], "..." if len(q["case_en"]) > 400 else "")
        print("CASE_ZH:", (q.get("case_zh", "") or "").strip()[:400])
    for op in q.get("options") or []:
        print(f"  opt {op['id']}: {op.get('en', '').strip()}  ||  zh={op.get('zh', '')}")
    for s in q.get("slots") or []:
        print(f"  slot {s.get('id')} label={s.get('zh', '')}")
        for x in s.get("options") or []:
            print(f"    {x['id']}: {x.get('en', '').strip()}  ||  zh={x.get('zh', '')}")
