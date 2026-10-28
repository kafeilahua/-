"""把一批重译结果合并进 data/translations.json（并把状态标记为 ai）。

用法：
    python -X utf8 scripts/apply_retranslation.py 批次文件.json

批次文件格式（每题可只给一部分字段）：
    {
      "t1-q36": {
        "zh": "题干中文",
        "options_zh": {"A": "选项中文", "B": "..."},
        "slots_zh": {"1": {"1": "槽位选项中文"}},
        "case_zh": "案例材料中文",
        "case_from": "t2-q50"     # 或：直接复制另一题的 case_zh
      }
    }

合并后重跑 scripts/enrich_bank.py 才会进题库。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / "data" / "translations.json"
translations = json.loads(path.read_text(encoding="utf-8"))
batch = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

for qid, item in batch.items():
    if qid not in translations:
        raise SystemExit(f"未知题号：{qid}")
    patch = translations[qid]
    if "case_from" in item:
        text = translations[item["case_from"]].get("case_zh") or ""
        if not text:
            raise SystemExit(f"{item['case_from']} 没有 case_zh 可复用")
        patch["case_zh"] = text
    for key in ("zh", "case_zh"):
        if key in item:
            patch[key] = item[key]
    if "options_zh" in item:
        patch.setdefault("options_zh", {}).update(item["options_zh"])
    if "slots_zh" in item:
        merged = patch.get("slots_zh")
        if not isinstance(merged, dict):
            merged = {}
        for slot_id, options in item["slots_zh"].items():
            merged.setdefault(str(slot_id), {}).update(options)
        patch["slots_zh"] = merged
    patch["translation_status"] = "ai"

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(translations, ensure_ascii=False, indent=2) + "\n")
print(f"合并 {len(batch)} 题；状态记为 ai")
