"""Apply reviewed overrides and versioned translations without replacing source evidence."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "data/question-bank.json"
    bank = json.loads(path.read_text())
    translations = (
        json.loads((ROOT / "data/translations.json").read_text())
        if (ROOT / "data/translations.json").exists()
        else {}
    )
    reviewed = (
        json.loads((ROOT / "data/overrides.json").read_text())
        if (ROOT / "data/overrides.json").exists()
        else {}
    )
    for q in bank["questions"]:
        patch = translations.get(q["id"], {})
        q["zh"] = patch.get("zh", q["zh"])
        q["case_zh"] = patch.get("case_zh", q.get("case_zh", ""))
        q["translation_status"] = patch.get("translation_status", "pending")
        for o in q["options"]:
            o["zh"] = patch.get("options_zh", {}).get(o["id"], "")
        if q["id"] in reviewed:
            q.update({k: v for k, v in reviewed[q["id"]].items() if k != "options_zh"})
            for o in q["options"]:
                o["zh"] = reviewed[q["id"]].get("options_zh", {}).get(o["id"], o["zh"])
        # Preserve proper nouns when a draft did not preserve them. Do not pretend this is reviewed.
        if q["translation_status"] == "machine":
            substitutions = {
                "阿苏雷哨兵": "Microsoft Sentinel",
                "Azure 哨兵": "Azure Sentinel",
                "微软365": "Microsoft 365",
                "微软 365": "Microsoft 365",
                "微软维权为办公室365": "Microsoft Defender for Office 365",
                "微软维权者": "Microsoft Defender",
                "微软维权": "Microsoft Defender",
                "微软辩护者": "Microsoft Defender",
                "Microsoft 365 维权者": "Microsoft 365 Defender",
                "微软": "Microsoft",
                "安全提示": "安全告警",
                "检测政策": "检测策略",
                "预防(DLP)政策": "防护（DLP）策略",
                "狩猎": "威胁搜寻",
                "野蛮武力攻击": "暴力破解攻击",
                "共享点": "SharePoint",
                "签名时": "登录时",
                "签入": "登录",
                "无法进行的旅行": "不可能的旅行",
                "恶意检测": "恶意软件检测",
            }
            for target in [q] + q["options"]:
                for old, new in substitutions.items():
                    target["zh"] = target.get("zh", "").replace(old, new)
    qs = bank["questions"]
    # Version the actual immutable question content, not just the input file.
    bank["source_version"] = bank.get("source_version", bank["version"])
    bank["version"] = hashlib.sha256(json.dumps(qs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[
        :12
    ]
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=2))
    report = dict(
        source_pages=bank["page_count"],
        total=len(qs),
        unique_ids=len({q["id"] for q in qs}),
        topics=dict(Counter(q["topic"] for q in qs)),
        types=dict(Counter(q["type"] for q in qs)),
        statuses=dict(Counter(q["status"] for q in qs)),
        translated=sum(bool(q["zh"]) for q in qs),
        translation_states=dict(Counter(q["translation_status"] for q in qs)),
        review=[dict(id=q["id"], pages=q["pages"], issues=q["issues"]) for q in qs if q["status"] != "ready"],
    )
    (ROOT / "data/import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "review"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
