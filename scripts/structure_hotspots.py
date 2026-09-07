"""Extract highlighted answer cells as reviewable candidates, never silently publish guesses."""

import json
import re
from pathlib import Path

import numpy as np
import pdfplumber
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]


def regions(mask):
    # Run-based connected components, avoiding Python work for every background pixel.
    runs = []
    parent = []
    prev = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for y, row in enumerate(mask):
        edges = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.where(edges == 1)[0]
        ends = np.where(edges == -1)[0]
        current = []
        for x0, x1 in zip(starts, ends):
            i = len(runs)
            runs.append((int(x0), y, int(x1), y + 1))
            parent.append(i)
            for a, b, j in prev:
                if b >= x0 and a <= x1:
                    parent[find(i)] = find(j)
            current.append((x0, x1, i))
        prev = current
    groups = {}
    for i, b in enumerate(runs):
        root = find(i)
        if root not in groups:
            groups[root] = list(b) + [0]
        g = groups[root]
        g[0] = min(g[0], b[0])
        g[1] = min(g[1], b[1])
        g[2] = max(g[2], b[2])
        g[3] = max(g[3], b[3])
        g[4] += b[2] - b[0]
    return [g[:4] for g in groups.values() if g[2] - g[0] > 20 and g[3] - g[1] > 12 and g[4] > 50]


def main():
    qs = json.loads((ROOT / "data/question-bank.json").read_text())["questions"]
    ocr = json.loads((ROOT / "data/ocr-result.json").read_text())["pages"]
    source = ROOT / "SC-200_问题+答案.pdf"
    pdf = pdfplumber.open(source)
    render = pdfium.PdfDocument(source)
    result = {}
    for q in qs:
        if q["type"] != "hotspot":
            continue
        slots = []
        selection = []
        evidence = []
        for pno in q["pages"]:
            names = [x for x in q["answer_assets"] if f"-p{pno}-" in x]
            if not names:
                continue
            page = pdf.pages[pno - 1]
            pic = np.array(render[pno - 1].render(scale=200 / 72).to_pil().convert("RGB")).astype(np.int16)
            r, g, b = pic[:, :, 0], pic[:, :, 1], pic[:, :, 2]
            red = (r > 150) & (g < 140) & (b < 150) & (r - g > 60)
            green = (g > r + 12) & (g > b + 10) & (g > 140) & (r > 100)
            area = np.zeros(red.shape, dtype=bool)
            for name in names:
                im = page.images[int(re.search(r"-(\d+)\.webp$", name)[1])]
                x0, y0, x1, y1 = [
                    max(0, round(v * 200 / 72)) for v in [im["x0"], im["top"], im["x1"], im["bottom"]]
                ]
                area[y0:y1, x0:x1] = True
            colored = regions((red | green) & area)
            # Hand-drawn black rectangles are thick, unlike the thin dropdown borders.
            black = (r < 80) & (g < 80) & (b < 80) & area
            outlined = []
            for box in regions(black):
                x0, y0, x1, y1 = box
                w = x1 - x0
                h = y1 - y0
                if w < 50 or h < 20 or h > 180 or w / h < 1.4:
                    continue
                k = black[y0:y1, x0:x1]
                if (
                    k[:5].mean() > 0.55
                    and k[-5:].mean() > 0.55
                    and k[:, :5].mean() > 0.4
                    and k[:, -5:].mean() > 0.4
                ):
                    outlined.append(box)
            raw = colored + outlined
            boxes = []
            for rect in sorted(raw, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
                if any(
                    min(rect[2], b[2]) > max(rect[0], b[0]) and min(rect[3], b[3]) > max(rect[1], b[1])
                    for b in boxes
                ):
                    continue
                boxes.append(rect)
            boxes.sort(key=lambda box: (box[1], box[0]))
            o = ocr[pno - 1]["ocr"]
            texts = [
                (t, box, float(conf))
                for t, box, conf in zip(o["rec_texts"], o["rec_boxes"], o["rec_scores"])
                if t.strip()
            ]
            for rect in boxes:
                x0, y0, x1, y1 = rect
                yes = [(t, b, c) for t, b, c in texts if t.lower() == "yes" and b[1] < y0]
                no = [(t, b, c) for t, b, c in texts if t.lower() == "no" and b[1] < y0]
                if x1 - x0 < 100 and y1 - y0 < 100 and yes and no:
                    yheader = max(yes, key=lambda item: item[1][1])
                    nheader = max(no, key=lambda item: item[1][1])
                    yc = (yheader[1][0] + yheader[1][2]) / 2
                    nc = (nheader[1][0] + nheader[1][2]) / 2
                    center = (x0 + x1) / 2
                    if min(abs(center - yc), abs(center - nc)) < 35:
                        choice = "yes" if abs(center - yc) < abs(center - nc) else "no"
                        statements = [
                            t
                            for t, b, c in texts
                            if b[2] < min(yc, nc) - 20 and abs((b[1] + b[3]) / 2 - (y0 + y1) / 2) < 35
                        ]
                        slotid = str(len(slots) + 1)
                        slots.append(
                            dict(
                                id=slotid,
                                en=" ".join(statements) or f"Statement {slotid} (see figure)",
                                zh="",
                                options=[dict(id="yes", en="Yes", zh="是"), dict(id="no", en="No", zh="否")],
                            )
                        )
                        selection.append(choice)
                        evidence.append(
                            dict(
                                page=pno,
                                rect=rect,
                                text=choice,
                                min_confidence=min(yheader[2], nheader[2]),
                                method="radio-column",
                            )
                        )
                        continue
                inside = [
                    (t, box, c)
                    for t, box, c in texts
                    if x0 - 3 <= (box[0] + box[2]) / 2 <= x1 + 3 and y0 - 3 <= (box[1] + box[3]) / 2 <= y1 + 3
                ]
                if not inside:
                    continue
                answer = " ".join(t for t, _, _ in inside)
                # Dropdown alternatives share a left edge, fit within the selected rectangle's horizontal span,
                # and form a vertically contiguous list. Preserve their original text and ordering.
                tx = min(box[0] for _, box, _ in inside)
                nearby = [
                    (t, box, c)
                    for t, box, c in texts
                    if abs(box[0] - tx) < 20
                    and box[2] <= x1 + 12
                    and box[3] >= y0 - 230
                    and box[1] <= y1 + 230
                ]
                nearby.sort(key=lambda item: item[1][1])
                center = [i for i, v in enumerate(nearby) if v in inside]
                if not center:
                    continue
                lo = min(center)
                hi = max(center)
                while lo > 0 and nearby[lo][1][1] - nearby[lo - 1][1][3] < 18:
                    lo -= 1
                while hi < len(nearby) - 1 and nearby[hi + 1][1][1] - nearby[hi][1][3] < 18:
                    hi += 1
                choices = []
                for t, box, c in nearby[lo : hi + 1]:
                    if t not in choices:
                        choices.append(t)
                if answer not in choices:
                    choices.append(answer)
                if len(choices) < 2 or len(choices) > 12:
                    continue
                slotid = str(len(slots) + 1)
                slots.append(
                    dict(
                        id=slotid,
                        en=f"Answer area {slotid} (top to bottom)",
                        zh=f"第 {slotid} 个答题区域（从上到下）",
                        options=[dict(id=str(i + 1), en=t, zh="") for i, t in enumerate(choices)],
                    )
                )
                selection.append(str(choices.index(answer) + 1))
                evidence.append(
                    dict(page=pno, rect=rect, text=answer, min_confidence=min(c for _, _, c in inside))
                )
            page.close()
        if slots:
            result[q["id"]] = {"slots": slots, "answer": selection, "evidence": evidence}
        if len(result) % 15 == 0:
            print("candidates", len(result), q["id"], flush=True)
    (ROOT / "data/hotspot-candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("total candidates", len(result), flush=True)


if __name__ == "__main__":
    main()
