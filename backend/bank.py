import json
from functools import lru_cache

from .db import DATA, ROOT


@lru_cache
def bank():
    path = DATA / "question-bank.json"
    if not path.exists():
        path = ROOT / "data/question-bank.json"
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"version": "empty", "questions": [], "page_count": 0}
    )


def question_map():
    return {q["id"]: q for q in bank()["questions"]}


def public_question(q, reveal=False):
    keys = [
        "id",
        "topic",
        "number",
        "pages",
        "type",
        "en",
        "zh",
        "options",
        "slots",
        "assets",
        "case_assets",
        "case_en",
        "case_zh",
        "tags",
        "domain",
        "status",
        "translation_status",
    ]
    result = {k: q.get(k) for k in keys}
    # Slot descriptors carry no answer keys.
    result["slots"] = [{k: v for k, v in s.items() if k != "answer"} for s in (q.get("slots") or [])]
    if reveal:
        result.update(
            {
                k: q.get(k)
                for k in [
                    "answer",
                    "answer_assets",
                    "explanation_en",
                    "explanation_zh",
                    "reference",
                    "issues",
                ]
            }
        )
    return result


def grade(q, answer):
    if q["type"] in ("single", "multiple"):
        correct = set(answer) == set(q["answer"]) and len(answer) == len(set(answer))
        return int(correct), 1
    expected = q["answer"]
    return sum(a == b for a, b in zip(answer, expected)), len(expected)
