"""Validate all items, assets, and scoring contracts before publishing an import."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(bank):
    qs = bank["questions"]
    errors = []
    if len(qs) != 410 or len({q["id"] for q in qs}) != 410:
        errors.append("题号未完整对账至 410 题")
    for q in qs:
        if q["status"] == "ready":
            if not q["answer"]:
                errors.append(q["id"] + " 缺少答案")
            if q["type"] in ("single", "multiple"):
                options = [o["id"] for o in q["options"]]
                if len(options) != len(set(options)) or not set(q["answer"]) <= set(options):
                    errors.append(q["id"] + " 选项无效")
            else:
                if len(q["slots"]) != len(q["answer"]):
                    errors.append(q["id"] + " 答题槽数量不符")
                for slot, answer in zip(q["slots"], q["answer"]):
                    if answer not in [o["id"] for o in slot["options"]]:
                        errors.append(q["id"] + " 答题槽答案无效")
        if set(q["assets"]) & set(q["answer_assets"]):
            errors.append(q["id"] + " 题图答案资源混用")
        for asset in q.get("assets", []) + q.get("answer_assets", []) + q.get("case_assets", []):
            if not (ROOT / "data/assets" / asset).is_file():
                errors.append(q["id"] + " 图片缺失 " + asset)
    return errors


if __name__ == "__main__":
    bank = json.loads((ROOT / "data/question-bank.json").read_text())
    errors = validate(bank)
    if errors:
        raise SystemExit("\n".join(errors))
    print("通过：410 个唯一题号，全部答案契约及图片引用有效。")
