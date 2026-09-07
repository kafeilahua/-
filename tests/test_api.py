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


def choose_question():
    return next(q for q in bank()["questions"] if q["status"] == "ready" and q["type"] == "single")


def favorite(client, qid, **changes):
    path = f"/api/v1/questions/{qid}/personal"
    current = client.get(path).json()
    response = client.patch(path, json={"version": current["version"], "favorite": True, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def fixed_attempt(client, q, correct=False):
    favorite(client, q["id"])
    s = new(client, mode="favorite", count=1, question_ids=[q["id"]])
    if correct:
        response = client.put(
            f"/api/v1/sessions/{s['id']}/answer",
            json={"question_id": q["id"], "answer": q["answer"], "version": s["version"], "submit": True},
        )
        assert response.status_code == 200, response.text
    response = client.post(f"/api/v1/sessions/{s['id']}/finish")
    assert response.status_code == 200, response.text
    return s


def test_review_intervals_early_practice_and_wrong_reset(client, monkeypatch):
    import backend.main as api

    clock = [100000.0]
    monkeypatch.setattr(api, "now", lambda: clock[0])
    q = choose_question()
    first = fixed_attempt(client, q)
    m = client.get("/api/v1/mistakes").json()[0]
    assert (m["due_at"], m["review_stage"], m["last_reviewed"]) == (clock[0], 0, None)
    assert client.get("/api/v1/review/summary").json()["due_count"] == 1
    for stage, days in enumerate([1, 3, 7, 14, 30, 30], start=1):
        clock[0] = m["due_at"] + 1
        fixed_attempt(client, q, correct=True)
        m = client.get("/api/v1/mistakes").json()[0]
        assert m["review_stage"] == min(stage, 5)
        assert m["due_at"] == clock[0] + days * 86400
        assert client.get("/api/v1/review/summary").json()["scheduled_count"] == 1
        # Correct practice before the due date updates last review, but never advances the schedule.
        due = m["due_at"]
        clock[0] += 20
        fixed_attempt(client, q, correct=True)
        m = client.get("/api/v1/mistakes").json()[0]
        assert m["due_at"] == due and m["review_stage"] == min(stage, 5)
        assert m["last_reviewed"] == clock[0]
    clock[0] += 1
    fixed_attempt(client, q)
    m = client.get("/api/v1/mistakes").json()[0]
    assert m["count"] == 2 and m["review_stage"] == 0 and m["due_at"] == clock[0]
    client.post(f"/api/v1/sessions/{first['id']}/finish")
    assert client.get("/api/v1/mistakes").json()[0]["count"] == 2


def test_mastery_resets_due_and_targeted_mastered_practice(client):
    q = choose_question()
    fixed_attempt(client, q)
    path = "/api/v1/mistakes/" + q["id"]
    assert client.patch(path, json={"mastered": True}).status_code == 200
    m = client.get("/api/v1/mistakes?state=mastered").json()[0]
    assert m["due_at"] is None
    assert client.get("/api/v1/review/summary").json()["due_count"] == 0
    assert client.post("/api/v1/sessions", json={"mode": "wrong", "count": 1}).status_code == 400
    assert (
        client.post(
            "/api/v1/sessions", json={"mode": "wrong", "count": 1, "question_ids": [q["id"]]}
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/sessions",
            json={"mode": "wrong", "count": 1, "question_ids": [q["id"]], "due_only": True},
        ).status_code
        == 400
    )
    assert client.patch(path, json={"mastered": False}).status_code == 200
    assert client.get("/api/v1/mistakes?state=due").json()[0]["review_stage"] == 0


def test_targeted_selection_deduplication_and_filters(client):
    q = choose_question()
    other = next(x for x in bank()["questions"] if x["status"] == "ready" and x["id"] != q["id"])
    fixed_attempt(client, q)
    fixed_attempt(client, q)
    favorite(client, other["id"])
    path = "/api/v1/sessions"
    request = {"mode": "wrong", "count": 1, "question_ids": [q["id"], q["id"]]}
    response = client.post(path, json=request)
    assert response.status_code == 201 and len(response.json()["questions"]) == 1
    assert client.post(path, json={**request, "count": 2}).status_code == 400
    assert client.post(path, json={**request, "question_ids": [other["id"]]}).status_code == 400
    assert client.post(path, json={**request, "mode": "random"}).status_code == 400
    assert client.post(path, json={**request, "mode": "favorite", "due_only": True}).status_code == 400
    results = client.get(
        "/api/v1/mistakes",
        params={
            "state": "due",
            "min_count": 2,
            "q": q["id"],
            "topic": q["topic"],
            "sort": "frequent",
            "last_days": 1,
        },
    ).json()
    assert len(results) == 1 and results[0]["count"] == 2
    assert client.get("/api/v1/mistakes?min_count=3").json() == []
    assert client.get("/api/v1/mistakes?tag=not-a-real-tag").json() == []
    assert client.get("/api/v1/mistakes?last_days=0").status_code == 422


def test_personal_notes_version_library_and_isolation(client):
    q = choose_question()
    path = f"/api/v1/questions/{q['id']}/personal"
    assert client.get(path).json() == {
        "question_id": q["id"],
        "favorite": False,
        "note": "",
        "updated": None,
        "version": 0,
    }
    saved = favorite(client, q["id"], note="记住事件响应流程")
    assert saved["version"] == 1
    assert client.patch(path, json={"version": 0, "note": "旧页面内容"}).status_code == 409
    assert client.patch(path, json={"version": 1, "favorite": False}).json()["note"] == saved["note"]
    row = client.get("/api/v1/library").json()[0]
    assert not row["favorite"] and row["note"] == saved["note"]
    assert "answer" not in row["question"] and "answer_assets" not in row["question"]
    assert client.patch(path, json={"version": 2, "note": "x" * 10001}).status_code == 422
    assert client.patch(path, json={"version": 2, "note": None}).status_code == 422
    with TestClient(app) as other:
        register = other.post(
            "/api/v1/auth/register",
            json={"username": "personal" + str(saved["updated"]).replace(".", ""), "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = register.json()["csrf"]
        assert other.get(path).json()["note"] == ""
        assert other.get("/api/v1/library").json() == []
        assert (
            other.post(
                "/api/v1/sessions", json={"mode": "favorite", "count": 1, "question_ids": [q["id"]]}
            ).status_code
            == 400
        )
    assert client.patch(path, json={"version": 2, "note": ""}).status_code == 200
    assert client.get("/api/v1/library").json() == []
    assert client.get("/api/v1/questions/not-found/personal").status_code == 404
    client.headers["X-CSRF-Token"] = "bad"
    assert client.patch(path, json={"version": 3, "favorite": True}).status_code == 403


def test_feedback_validation_ownership_and_withdrawal(client):
    qid = choose_question()["id"]
    path = f"/api/v1/questions/{qid}/reports"
    assert client.post(path, json={"category": "answer", "content": "     "}).status_code == 422
    response = client.post(
        path, json={"category": "translation", "content": "  产品名称翻译有误，请核对。  "}
    )
    assert response.status_code == 201
    item = response.json()
    assert item["status"] == "open" and item["content"] == "产品名称翻译有误，请核对。"
    assert client.get("/api/v1/reports").json() == [item]
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register", json={"username": "reports" + item["id"][:12], "password": "testing123!"}
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        assert other.get("/api/v1/reports").json() == []
        assert other.patch("/api/v1/reports/" + item["id"], json={"status": "withdrawn"}).status_code == 404
    assert (
        client.patch("/api/v1/reports/" + item["id"], json={"status": "withdrawn"}).json()["status"]
        == "withdrawn"
    )
    assert client.patch("/api/v1/reports/" + item["id"], json={"status": "open"}).status_code == 422


def test_review_summary_uses_real_recent_and_weekly_attempts(client, monkeypatch):
    import time

    import backend.main as api

    q = choose_question()
    clock = [time.time() - 8 * 86400]
    monkeypatch.setattr(api, "now", lambda: clock[0])
    fixed_attempt(client, q)
    clock[0] += 8 * 86400
    fixed_attempt(client, q, correct=True)
    fixed_attempt(client, q, correct=True)
    data = client.get("/api/v1/review/summary").json()
    assert data["recommendations"] == [
        {
            "topic": q["topic"],
            "attempts": 3,
            "accuracy": 66.7,
            "ready_count": sum(
                x["topic"] == q["topic"] and x["status"] == "ready" for x in bank()["questions"]
            ),
        }
    ]
    for knowledge in data["knowledge"]:
        assert knowledge["tag"] in q["tags"]
        assert knowledge["count"] == 3 and knowledge["correct"] == 2 and knowledge["accuracy"] == 66.7
        assert knowledge["previous_accuracy"] == 0
        assert [t["count"] for t in knowledge["trend"]] == [1, 2]
        assert [t["accuracy"] for t in knowledge["trend"]] == [0, 100]


def test_mistake_assets_only_accessible_to_owner(client):
    q = next(q for q in bank()["questions"] if q["id"] == "t1-q7")
    filename = q["answer_assets"][0]
    path = f"/api/v1/mistakes/{q['id']}/assets/{filename}"
    assert client.get(path).status_code == 404
    fixed_attempt(client, q)
    assert client.get(path).status_code == 200
    assert client.get(f"/api/v1/mistakes/{q['id']}/assets/unknown.webp").status_code == 404
    with TestClient(app) as other:
        import uuid

        r = other.post(
            "/api/v1/auth/register",
            json={"username": "image" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        assert other.get(path).status_code == 404


def test_backup_v2_round_trip_dedup_newer_notes_and_rollback(client, monkeypatch):
    import copy
    import time
    import uuid

    import backend.main as api

    q = choose_question()
    clock = [time.time() - 1000]
    monkeypatch.setattr(api, "now", lambda: clock[0])
    fixed_attempt(client, q)
    clock[0] += 10
    fixed_attempt(client, q, correct=True)
    favorite(client, q["id"], note="需要复习的个人笔记")
    client.post(
        f"/api/v1/questions/{q['id']}/reports",
        json={"category": "answer", "content": "此题答案需要进一步核对"},
    )
    backup = client.get("/api/v1/export").json()
    assert backup["schema_version"] == 2
    assert backup["review"][0]["review_stage"] == 1
    assert backup["personal"][0]["note"] == "需要复习的个人笔记"
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register",
            json={"username": "backup" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        imported = other.post("/api/v1/import", json=backup)
        assert imported.status_code == 200 and imported.json() == {"imported": 2, "skipped": 0}, imported.text
        assert other.get("/api/v1/stats").json()["total"] == 2
        row = other.get("/api/v1/mistakes").json()[0]
        assert row["review_stage"] == 1 and row["due_at"] == backup["review"][0]["due_at"]
        assert other.post("/api/v1/import", json=backup).json() == {"imported": 0, "skipped": 2}
        assert len(other.get("/api/v1/reports").json()) == 1
        clock[0] += 10
        current = favorite(other, q["id"], note="本地更新的笔记")
        other.patch(f"/api/v1/mistakes/{q['id']}", json={"mastered": True})
        assert other.post("/api/v1/import", json=backup).status_code == 200
        assert other.get(f"/api/v1/questions/{q['id']}/personal").json() == current
        assert other.get("/api/v1/mistakes").json()[0]["mastered"]
        malformed = copy.deepcopy(backup)
        malformed["personal"][0]["updated"] = clock[0] + 1
        malformed["personal"][0]["note"] = "不应该保存的内容"
        malformed["reports"][0]["question_id"] = "nonexistent"
        assert other.post("/api/v1/import", json=malformed).status_code == 400
        assert other.get(f"/api/v1/questions/{q['id']}/personal").json() == current


def test_old_backup_v1_is_compatible_and_review_becomes_due(client):
    import uuid

    q = choose_question()
    fixed_attempt(client, q)
    backup = client.get("/api/v1/export").json()
    old = {key: value for key, value in backup.items() if key not in ("personal", "reports", "review")}
    old["schema_version"] = 1
    old["sessions"][0].pop("submitted_at")
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register",
            json={"username": "legacy" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        imported = other.post("/api/v1/import", json=old)
        assert imported.status_code == 200 and imported.json()["imported"] == 1, imported.text
        row = other.get("/api/v1/mistakes?state=due").json()[0]
        assert row["review_stage"] == 0 and row["due_at"] == old["sessions"][0]["finished"]
        assert other.get("/api/v1/library").json() == []


def test_migration_from_real_001_preserves_user_and_old_mistakes(tmp_path):
    import subprocess
    import sys

    code = """
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from backend.db import engine
config = Config("alembic.ini")
command.upgrade(config, "001")
assert "due_at" not in {c["name"] for c in inspect(engine).get_columns("mistakes")}
with engine.begin() as conn:
    conn.execute(text("INSERT INTO users VALUES ('owner', '原用户', 'unchanged-password-hash', 'Asia/Shanghai')"))
    conn.execute(text("INSERT INTO mistakes VALUES ('m1', 'owner', 't1-q2', 4, 0, 1000)"))
    conn.execute(text("INSERT INTO mistakes VALUES ('m2', 'owner', 't1-q3', 2, 1, 2000)"))
command.upgrade(config, "head")
with engine.connect() as conn:
    assert conn.scalar(text("SELECT password FROM users WHERE id='owner'")) == "unchanged-password-hash"
    rows = conn.execute(text("SELECT count, mastered, due_at, review_stage, last_reviewed, schedule_updated FROM mistakes ORDER BY id")).all()
    assert tuple(rows[0]) == (4, 0, 1000, 0, None, 1000), rows
    assert tuple(rows[1]) == (2, 1, None, 0, None, 2000), rows
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "002"
assert {"personal_questions", "question_reports"} <= set(inspect(engine).get_table_names())
command.upgrade(config, "head")
"""
    env = {**os.environ, "SC200_DATABASE_URL": "sqlite:///" + str(tmp_path / "migration.db")}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_overlapping_backups_do_not_double_count_unfinished_wrong_answers(client):
    import uuid

    q = choose_question()
    favorite(client, q["id"])
    session = new(client, mode="favorite", count=1, question_ids=[q["id"]])
    submitted = client.put(
        f"/api/v1/sessions/{session['id']}/answer",
        json={"question_id": q["id"], "answer": [], "version": session["version"], "submit": True},
    )
    assert submitted.status_code == 200
    partial = client.get("/api/v1/export").json()
    assert partial["sessions"] == [] and partial["review"][0]["count"] == 1
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register",
            json={"username": "overlap" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        restored = other.post("/api/v1/import", json=partial)
        assert restored.status_code == 200, restored.text
        assert other.get("/api/v1/mistakes").json()[0]["count"] == 1
        assert other.get("/api/v1/stats").json()["total"] == 0
        # A local mistake between backups must be preserved as a separate failure.
        fixed_attempt(other, q)
        client.post(f"/api/v1/sessions/{session['id']}/finish")
        complete = client.get("/api/v1/export").json()
        assert other.post("/api/v1/import", json=complete).status_code == 200
        assert other.get("/api/v1/mistakes").json()[0]["count"] == 2
        assert other.get("/api/v1/stats").json()["total"] == 2
        assert other.post("/api/v1/import", json=partial).status_code == 200
        assert other.get("/api/v1/mistakes").json()[0]["count"] == 2


def test_backup_round_trip_preserves_source_ids_and_deduplicates(client):
    import uuid

    q = choose_question()
    fixed_attempt(client, q)
    report = client.post(
        f"/api/v1/questions/{q['id']}/reports", json={"category": "answer", "content": "核对当前题目的答案"}
    ).json()
    original = client.get("/api/v1/export").json()
    with TestClient(app) as other:
        r = other.post(
            "/api/v1/auth/register",
            json={"username": "roundtrip" + uuid.uuid4().hex[:12], "password": "testing123!"},
        )
        other.headers["X-CSRF-Token"] = r.json()["csrf"]
        assert other.post("/api/v1/import", json=original).status_code == 200
        restored = other.get("/api/v1/export").json()
        assert restored["sessions"][0]["id"] == original["sessions"][0]["id"]
        assert restored["reports"][0]["id"] == report["id"]
        result = client.post("/api/v1/import", json=restored)
        assert result.status_code == 200 and result.json() == {"imported": 0, "skipped": 1}, result.text
        assert client.get("/api/v1/stats").json()["total"] == 1
        assert client.get("/api/v1/mistakes").json()[0]["count"] == 1
        assert len(client.get("/api/v1/reports").json()) == 1
