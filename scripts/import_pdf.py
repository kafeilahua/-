"""Reproducible, conservative extraction. Run: uv run python -m scripts.import_pdf."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
HEADER = re.compile(r"Question\s*#(\d+)\s+Topic\s*(\d+)")
NOISE = re.compile(r"^.*(?:91exam|淘宝|快速拿证|Exam SC-200 All Actual Questions).*$")


def clean(text):
    return "\n".join(line.rstrip() for line in text.splitlines() if not NOISE.match(line)).strip()


def infer_tags(text):
    tags = []
    for keyword, tag in [
        ("Sentinel", "Microsoft Sentinel"),
        ("Defender", "Microsoft Defender"),
        ("KQL", "KQL"),
        ("query", "KQL"),
        ("Cloud Apps", "Cloud Apps"),
        ("Azure AD", "Microsoft Entra ID"),
        ("Purview", "Microsoft Purview"),
    ]:
        if keyword.lower() in text.lower() and tag not in tags:
            tags.append(tag)
    if re.search(r"hunt|Kusto|\bKQL\b|query", text, re.I):
        domain = "hunting"
    elif re.search(r"investigat|incident|remediat|respond", text, re.I):
        domain = "response"
    else:
        domain = "operations"
    return tags, domain


def parse_question(item):
    text = clean("\n".join(item["chunks"]))
    before, _, after = text.partition("Correct Answer:")
    before = before.replace("Most Voted", "")
    matches = list(re.finditer(r"^\s*([A-H])\.\s+(.+)", before, re.M))
    opts = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(before)
        opts.append({"id": m[1], "en": re.sub(r"\s+", " ", before[m.start() : end]).strip()[3:], "zh": ""})
    stem = before[: matches[0].start()].strip() if matches else before.strip()
    answer_match = re.match(r"\s*([A-H]{1,8})\b", after)
    answer = list(answer_match[1]) if answer_match else []
    typ = (
        "hotspot"
        if "HOTSPOT" in stem
        else "matching"
        if "DRAG DROP" in stem
        else "multiple"
        if len(answer) > 1
        else "single"
    )
    reasons = []
    if typ in ("matching", "hotspot"):
        reasons.append("图片题需结构化核对")
    if not answer:
        reasons.append("未提取到文本答案")
    if len({x["id"] for x in opts}) != len(opts):
        reasons.append("原文选项编号重复")
    if not opts or not set(answer).issubset({o["id"] for o in opts}):
        reasons.append("选项与答案需核对")
    votes = re.findall(r"\b([A-H]{1,8})\s*\((\d+)%\)", after)
    if votes and max(votes, key=lambda v: int(v[1]))[0] != "".join(answer) and answer:
        reasons.append("原文答案与最高票答案冲突")
    case_en = ""
    if "Introductory Info" in stem or re.search(r"Case study\s*-", stem, re.I):
        positions = list(re.finditer(r"(?:^|\n)You need to ", stem))
        if positions:
            cut = positions[-1].start()
            case_en, stem = stem[:cut].strip(), stem[cut:].strip()
        else:
            reasons.append("案例题干分界需核对")
    tags, domain = infer_tags(stem)
    return dict(
        id=item["id"],
        topic=item["topic"],
        number=item["number"],
        pages=item["pages"],
        type=typ,
        en=stem,
        zh="",
        options=opts,
        answer=answer,
        slots=[],
        explanation_en="",
        explanation_zh="",
        reference=re.findall(r"https?://\S+", after),
        case_en=case_en,
        case_zh="",
        assets=[],
        answer_assets=[],
        tags=tags,
        domain=domain,
        domain_status="inferred",
        status="review" if reasons else "ready",
        issues=reasons,
        translation_status="pending",
        votes=votes,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=str(ROOT / "SC-200_问题+答案.pdf"))
    parser.add_argument("--assets", action="store_true")
    args = parser.parse_args()
    pdf = PdfReader(args.pdf)
    items = []
    current = None
    for i, p in enumerate(pdf.pages):
        text = p.extract_text(extraction_mode="layout") or ""
        match = HEADER.search(text)
        if match:
            current = dict(
                id=f"t{match[2]}-q{match[1]}", topic=int(match[2]), number=int(match[1]), pages=[], chunks=[]
            )
            items.append(current)
            text = text[match.end() :]
        if current:
            current["pages"].append(i + 1)
            current["chunks"].append(text)
    questions = [parse_question(x) for x in items]
    cases = {}
    for q in questions:
        if q["case_en"] and q["topic"] >= 8:
            cases[q["topic"]] = q["case_en"]
    for q in questions:
        q["case_en"] = cases.get(q["topic"], q["case_en"])
    if args.assets:
        extract_assets(args.pdf, questions)
    elif (ROOT / "data/question-bank.json").exists():
        previous = {
            q["id"]: q for q in json.loads((ROOT / "data/question-bank.json").read_text())["questions"]
        }
        for q in questions:
            for field in ("assets", "answer_assets", "case_assets"):
                q[field] = previous.get(q["id"], {}).get(field, [])
    patches = ROOT / "data/overrides.json"
    overrides = json.loads(patches.read_text()) if patches.exists() else {}
    for q in questions:
        q.update(overrides.get(q["id"], {}))
    digest = hashlib.sha256(Path(args.pdf).read_bytes()).hexdigest()
    bank = dict(
        version=digest[:12], source=Path(args.pdf).name, page_count=len(pdf.pages), questions=questions
    )
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data/question-bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=2))
    report = dict(
        source_pages=len(pdf.pages),
        total=len(questions),
        unique_ids=len({q["id"] for q in questions}),
        topics=dict(Counter(q["topic"] for q in questions)),
        types=dict(Counter(q["type"] for q in questions)),
        statuses=dict(Counter(q["status"] for q in questions)),
        translated=sum(bool(q["zh"]) for q in questions),
        review=[
            dict(id=q["id"], pages=q["pages"], issues=q["issues"])
            for q in questions
            if q["status"] != "ready"
        ],
    )
    (ROOT / "data/import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "review"}, ensure_ascii=False))


def extract_assets(path, questions):
    """Only original embedded figures before the answer boundary become public question assets."""
    import pdfplumber
    import pypdfium2 as pdfium

    assets = ROOT / "data/assets"
    assets.mkdir(parents=True, exist_ok=True)
    render = pdfium.PdfDocument(path)
    ocr_path = ROOT / "data/ocr-result.json"
    ocr = json.loads(ocr_path.read_text())["pages"] if ocr_path.exists() else []
    with pdfplumber.open(path) as pdf:
        for q in questions:
            answer_seen = False
            areas_seen = 0
            for page_no in q["pages"]:
                page = pdf.pages[page_no - 1]
                o = ocr[page_no - 1]["ocr"] if ocr else {}
                recognized = list(zip(o.get("rec_texts", []), o.get("rec_boxes", [])))
                if not recognized:
                    recognized = [
                        (
                            t,
                            [
                                min(p[0] for p in poly),
                                min(p[1] for p in poly),
                                max(p[0] for p in poly),
                                max(p[1] for p in poly),
                            ],
                        )
                        for t, poly in zip(o.get("rec_texts", []), o.get("rec_polys", []))
                    ]
                correct = [
                    box[1] / (200 / 72)
                    for t, box in recognized
                    if re.match(r"^\s*Correct\s+Answer\s*:", t, re.I)
                ]
                headers = [box[3] / (200 / 72) for t, box in recognized if "question #" in t.lower()]
                areas = sorted(
                    box[1] / (200 / 72)
                    for t, box in recognized
                    if re.match(r"^\s*Answer\s*Area\s*$", t, re.I)
                )
                repeated = [y for i, y in enumerate(areas) if areas_seen + i >= 1]
                areas_seen += len(areas)
                boundaries = correct + repeated
                answer_top = min(boundaries) if boundaries else page.height
                top = min(headers) if headers else 0
                image = None
                for n, im in enumerate(page.images):
                    if (
                        im["width"] < 35
                        or im["height"] < 16
                        or im["top"] < top
                        or im["top"] > page.height - 25
                    ):
                        continue
                    if image is None:
                        image = render[page_no - 1].render(scale=1.7).to_pil()
                    box = tuple(
                        round(v * 1.7)
                        for v in (
                            max(0, im["x0"]),
                            max(0, im["top"]),
                            min(page.width, im["x1"]),
                            min(page.height, im["bottom"]),
                        )
                    )
                    name = f"{q['id']}-p{page_no}-{n}.webp"
                    image.crop(box).save(assets / name, "WEBP", quality=90)
                    key = (
                        "answer_assets"
                        if answer_seen or (boundaries and im["bottom"] >= answer_top)
                        else "assets"
                    )
                    q[key].append(name)
                if boundaries:
                    answer_seen = True
                page.close()
            if q["number"] == 1 and q["case_en"]:
                # Shared case graphics are associated below via the case's first question.
                pass
            if q["number"] % 30 == 0:
                print("assets", q["id"], flush=True)
    for q in questions:
        first = next(
            (x for x in questions if x["topic"] == q["topic"] and x["number"] == 1 and x["case_en"]), None
        )
        q["case_assets"] = first["assets"] if first and q is not first else []


if __name__ == "__main__":
    main()
