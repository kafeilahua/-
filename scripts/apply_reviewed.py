"""把重译后的 reviewed 题写回 translations.json / overrides.json。

用法：
    python -X utf8 scripts/apply_reviewed.py 批次.json

批次格式同 apply_retranslation.py：
    {"t1-q38": {"zh": "...", "options_zh": {"A": "..."}, "case_zh": "...", "slots_zh": {"1": {"1": "..."}}}}

与 apply_retranslation.py 的区别：reviewed 题的 overrides.json 优先级更高，
如果 overrides 里也带了 zh / options_zh / case_zh，这里会同步写进 overrides，
否则改了 translations 也看不到效果。状态统一记为 ai。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
tr_path = DATA / "translations.json"
ov_path = DATA / "overrides.json"
translations = json.loads(tr_path.read_text(encoding="utf-8"))
overrides = json.loads(ov_path.read_text(encoding="utf-8"))

batch = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))

mirrored = []
for qid, item in batch.items():
    if qid not in translations:
        raise SystemExit(f"未知题号：{qid}")
    patch = translations[qid]
    if "case_from" in item:
        text = translations[item["case_from"]].get("case_zh") or ""
        if not text:
            raise SystemExit(f"{item['case_from']} 没有 case_zh 可复用")
        item = dict(item, case_zh=text)
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

    ov = overrides.get(qid)
    if ov is not None:
        touched = []
        for key in ("zh", "case_zh"):
            if key in ov and key in item:
                ov[key] = item[key]
                touched.append(key)
        if "options_zh" in ov and "options_zh" in item:
            ov["options_zh"].update(item["options_zh"])
            touched.append("options_zh")
        # 少数题 overrides 直接用 options 覆盖整个选项列表，中文只能写进那里
        if "options" in ov and "options_zh" in item:
            for o in ov["options"]:
                if o.get("id") in item["options_zh"]:
                    o["zh"] = item["options_zh"][o["id"]]
            touched.append("options")
        if "translation_status" in ov:
            ov["translation_status"] = "ai"
        if touched:
            mirrored.append(f"{qid}({'+'.join(touched)})")

print(f"合并 {len(batch)} 题；状态记为 ai")
print(f"overrides 同步 {len(mirrored)} 题：{' '.join(mirrored) if mirrored else '无'}")

tr_path.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")
ov_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")

