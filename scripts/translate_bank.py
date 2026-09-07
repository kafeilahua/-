"""Build a transparent offline Chinese draft. No question text leaves the machine.
uv run --group translation python -m scripts.translate_bank --model /path/to/translate-en_zh-1_9
"""

import argparse
import json
import re
from pathlib import Path

import ctranslate2
import sentencepiece

ROOT = Path(__file__).resolve().parents[1]


def segments(text):
    paragraphs = re.split(r"\n\s*\n", text)
    out = []
    for p in paragraphs:
        p = re.sub(r"\s+", " ", p).strip()
        out.extend(re.split(r"(?<=[.?])\s+(?=[A-Z])", p))
    return [s for s in out if s]


def code(text):
    return bool(
        re.match(
            r"^(?:\||\(?c:c\)|Project1\(c:c\)|\w+-MpPreference|search\s|union\s|join\s|evaluate\s|SecurityEvent\s*\||[A-Za-z][A-Za-z0-9]*\s*\|)",
            text,
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    a = p.parse_args()
    model = Path(a.model)
    engine = ctranslate2.Translator(str(model / "model"), device="cpu", intra_threads=4)
    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(model / "sentencepiece.model"))
    bank = json.loads((ROOT / "data/question-bank.json").read_text())
    cache_path = ROOT / "data/translation-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    qs = bank["questions"]
    fields = []
    for q in qs:
        fields += [q["en"], q.get("case_en", "")]
        fields += [o["en"] for o in q["options"]]
        for s in q.get("slots", []):
            fields += [s["en"]] + [o["en"] for o in s["options"]]
    chunks = list(
        dict.fromkeys(s for f in fields for s in segments(f) if s and s not in cache and not code(s))
    )
    terminology = {
        "警戒": "告警",
        "警报": "告警",
        "狩猎": "威胁搜寻",
        "租户者": "租户",
        "虚拟机器": "虚拟机",
        "订阅者": "订阅",
    }
    for i in range(0, len(chunks), 32):
        batch = chunks[i : i + 32]
        result = engine.translate_batch(
            [tokenizer.encode(x, out_type=str) for x in batch],
            beam_size=4,
            max_batch_size=32,
            replace_unknowns=True,
            max_decoding_length=512,
        )
        for source, row in zip(batch, result):
            target = tokenizer.decode(row.hypotheses[0]).replace("▁", " ").strip()
            for old, new in terminology.items():
                target = target.replace(old, new)
            target = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", target)
            cache[source] = target
        if i % 128 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
            print(f"translated {min(i + 32, len(chunks))}/{len(chunks)} segments", flush=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

    def translate(text):
        if code(text):
            return text
        if text in ("Yes", "No"):
            return {"Yes": "是", "No": "否"}[text]
        return "\n".join(cache.get(s, s) for s in segments(text))

    results = {}
    for q in qs:
        results[q["id"]] = {
            "zh": translate(q["en"]),
            "case_zh": translate(q.get("case_en", "")),
            "options_zh": {o["id"]: translate(o["en"]) for o in q["options"]},
            "translation_status": "machine",
            "slots_zh": [
                {"zh": translate(s["en"]), "options_zh": {o["id"]: translate(o["en"]) for o in s["options"]}}
                for s in q.get("slots", [])
            ],
        }
    (ROOT / "data/translations.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Completed {len(results)} question drafts", flush=True)


if __name__ == "__main__":
    main()
