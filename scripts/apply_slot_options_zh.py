"""给热点/匹配题的槽位选项补中文（写入 overrides.json）。

用法：
    python -X utf8 scripts/apply_slot_options_zh.py 批次.json

批次格式：
    {"t1-q14": {"1": {"1": "中文", "2": "中文"}}}

为什么不用 translations.json 的 slots_zh：这些题的 slots 结构本身来自 overrides.json，
enrich_bank 先套 translations 再套 overrides，overrides 会把整个 slots 列表覆盖掉，
所以槽位选项中文只能写进 overrides。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ov_path = DATA / "overrides.json"
overrides = json.loads(ov_path.read_text(encoding="utf-8"))
batch = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))

filled = 0
for qid, slots in batch.items():
    ov = overrides.get(qid)
    if not ov or "slots" not in ov:
        raise SystemExit(f"{qid} 在 overrides.json 里没有 slots")
    by_id = {str(s.get("id")): s for s in ov["slots"]}
    for slot_id, options in slots.items():
        slot = by_id.get(str(slot_id))
        if slot is None:
            raise SystemExit(f"{qid} 没有槽位 {slot_id}（现有 {sorted(by_id)}）")
        opt_by_id = {str(o.get("id")): o for o in slot.get("options") or []}
        for opt_id, text in options.items():
            o = opt_by_id.get(str(opt_id))
            if o is None:
                raise SystemExit(f"{qid} 槽位 {slot_id} 没有选项 {opt_id}（现有 {sorted(opt_by_id)}）")
            o["zh"] = text
            filled += 1

print(f"写入 {len(batch)} 题 / {filled} 个槽位选项的中文")
ov_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")

