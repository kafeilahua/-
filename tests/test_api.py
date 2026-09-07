import os
import tempfile
from pathlib import Path

os.environ["SC200_DATABASE_URL"] = "sqlite:///" + str(Path(tempfile.mkdtemp()) / "test.db")
import pytest
from fastapi.testclient import TestClient

from backend.bank import bank
from backend.db import Exam, SessionLocal
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        import uuid

        r = c.post(
            "/api/v1/auth/register",
            json={"username": "test" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        assert r.status_code == 201, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        yield c


def new(client, **kwargs):
    r = client.post("/api/v1/sessions", json={"mode": "random", "count": 3, **kwargs})
    assert r.status_code == 201, r.text
    return r.json()


def test_no_answer_leak_and_unique(client):
    s = new(client)
    assert len({q["id"] for q in s["questions"]}) == 3
    assert all("answer" not in q and "answer_assets" not in q for q in s["questions"])


def test_grade_and_idempotent_finish(client):
    s = new(client, count=1)
    q = s["questions"][0]
    expected = next(x["answer"] for x in bank()["questions"] if x["id"] == q["id"])
    r = client.put(
        f"/api/v1/sessions/{s['id']}/answer",
        json={"question_id": q["id"], "answer": expected, "version": s["version"], "submit": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][q["id"]]["correct"]
    a = client.post(f"/api/v1/sessions/{s['id']}/finish").json()
    b = client.post(f"/api/v1/sessions/{s['id']}/finish").json()
    assert a["score"] == b["score"] == 100
    assert client.get("/api/v1/stats").json()["total"] == 1


def test_unanswered_wrong_mastery_and_relearn(client):
    s = new(client, count=1)
    client.post(f"/api/v1/sessions/{s['id']}/finish")
    m = client.get("/api/v1/mistakes").json()[0]
    assert not m["mastered"]
    assert client.patch("/api/v1/mistakes/" + m["id"], json={"mastered": True}).status_code == 200
    assert client.get("/api/v1/stats").json()["wrong"] == 0
    assert client.post("/api/v1/sessions", json={"mode": "wrong", "count": 1}).status_code == 400


def test_cross_account_isolation(client):
    s = new(client)
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register", json={"username": "other" + s["id"][:10], "password": "testing123!"}
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        assert other.get("/api/v1/sessions/" + s["id"]).status_code == 404
        assert other.get("/api/v1/stats").json()["total"] == 0


def test_csrf_and_origin(client):
    client.headers["X-CSRF-Token"] = "bad"
    assert client.post("/api/v1/sessions", json={"count": 1}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"origin": "https://evil.invalid"},
            json={"username": "xx", "password": "testing123!"},
        ).status_code
        == 403
    )


def test_stale_version(client):
    s = new(client, count=1)
    q = s["questions"][0]
    payload = {"question_id": q["id"], "answer": [], "version": s["version"]}
    assert client.put("/api/v1/sessions/" + s["id"] + "/answer", json=payload).status_code == 200
    assert client.put("/api/v1/sessions/" + s["id"] + "/answer", json=payload).status_code == 409


def test_expiration_rejects_late_answer(client):
    s = new(client, count=1)
    with SessionLocal() as db:
        e = db.get(Exam, s["id"])
        e.deadline = e.started - 1
        db.commit()
    r = client.get("/api/v1/sessions/" + s["id"]).json()
    assert r["finished"] and r["score"] == 0
    assert client.get("/api/v1/stats").json()["total"] == 1


def test_export_import_deduplicates(client):
    s = new(client, count=1)
    client.post("/api/v1/sessions/" + s["id"] + "/finish")
    backup = client.get("/api/v1/export").json()
    r = client.post("/api/v1/import", json=backup)
    assert r.json() == {"imported": 0, "skipped": 1}, r.text
    assert client.get("/api/v1/stats").json()["total"] == 1


@pytest.mark.parametrize("count", [40, 50, 60])
def test_exam_distribution(client, count):
    s = new(client, mode="exam", count=count)
    from collections import Counter

    assert len(s["questions"]) == count
    assert len({q["id"] for q in s["questions"]}) == count
    if count == 50:
        assert Counter(q["domain"] for q in s["questions"]) == {
            "operations": 20,
            "response": 18,
            "hunting": 12,
        }
    assert not s["feedback"]
    assert 5990 < s["deadline"] - s["started"] < 6010


def test_bank_integrity():
    qs = bank()["questions"]
    assert len(qs) == 410 and len({q["id"] for q in qs}) == 410
    for q in qs:
        if q["status"] == "ready":
            assert q["answer"]
            if q["type"] in ("single", "multiple"):
                assert set(q["answer"]) <= {x["id"] for x in q["options"]}
        for image in q["assets"] + q["answer_assets"]:
            assert (Path("data/assets") / image).is_file()


def test_compound_scores_each_slot_without_ordering_multiselect():
    from backend.bank import grade

    qs = {q["id"]: q for q in bank()["questions"]}
    q = qs["t1-q7"]
    assert grade(q, q["answer"]) == (3, 3)
    assert grade(q, [q["answer"][0], "invalid"]) == (1, 3)
    multi = next(x for x in qs.values() if x["type"] == "multiple" and x["status"] == "ready")
    assert grade(multi, list(reversed(multi["answer"]))) == (1, 1)
    assert grade(multi, multi["answer"] + multi["answer"][:1]) == (0, 1)


def test_answer_images_protected_until_submission(client):
    import copy
    import time
    import uuid

    from sqlalchemy import select

    from backend.db import User

    q = next(q for q in bank()["questions"] if q["id"] == "t1-q7")
    assert "t1-q7-p9-2.webp" not in q["assets"]
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.username == client.get("/api/v1/auth/me").json()["username"])
        )
        e = Exam(
            id=uuid.uuid4().hex,
            user_id=user.id,
            mode="random",
            started=time.time(),
            state={
                "questions": [copy.deepcopy(q)],
                "answers": {},
                "feedback": True,
                "flags": [],
                "seconds": 0,
            },
        )
        db.add(e)
        db.commit()
        eid = e.id
    image = q["answer_assets"][0]
    assert client.get(f"/api/v1/sessions/{eid}/assets/{image}").status_code == 404
    assert client.post(f"/api/v1/sessions/{eid}/finish").status_code == 200
    assert client.get(f"/api/v1/sessions/{eid}/assets/{image}").status_code == 200


def test_review_cannot_reveal_ready_question(client):
    assert client.get("/api/v1/bank/review/t1-q7").status_code == 404
    q = next(q for q in bank()["questions"] if q["status"] == "review")
    r = client.get("/api/v1/bank/review/" + q["id"])
    assert r.status_code == 200 and r.json()["issues"]


def test_wrong_relearning_restores_pending_state(client):
    import copy
    import time
    import uuid

    first = new(client, count=1)
    client.post("/api/v1/sessions/" + first["id"] + "/finish")
    qid = first["questions"][0]["id"]
    client.patch("/api/v1/mistakes/" + qid, json={"mastered": True})
    with SessionLocal() as db:
        original = db.get(Exam, first["id"])
        e = Exam(
            id=uuid.uuid4().hex,
            user_id=original.user_id,
            mode="random",
            started=time.time(),
            state=copy.deepcopy(original.state),
        )
        db.add(e)
        db.commit()
        eid = e.id
    client.post("/api/v1/sessions/" + eid + "/finish")
    m = client.get("/api/v1/mistakes").json()[0]
    assert m["id"] == qid and not m["mastered"] and m["count"] == 2


def test_invalid_import_rolls_back(client):
    s = new(client, count=1)
    client.post("/api/v1/sessions/" + s["id"] + "/finish")
    backup = client.get("/api/v1/export").json()
    backup["sessions"][0]["id"] = "foreign-record"
    backup["sessions"][0]["answers"] = {s["questions"][0]["id"]: ["invalid-answer"]}
    assert client.post("/api/v1/import", json=backup).status_code == 400
    assert client.get("/api/v1/stats").json()["total"] == 1
