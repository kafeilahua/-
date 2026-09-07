import asyncio
import copy
import hashlib
import json
import math
import os
import random
import secrets
import time
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from alembic.config import Config
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text

from alembic import command

from .bank import bank, grade, public_question, question_map
from .db import DATA, ROOT, Activity, Attempt, Exam, Login, Mistake, SessionLocal, User

hasher = PasswordHasher()


def uid():
    return uuid.uuid4().hex


now = time.time


def transaction():
    with SessionLocal() as db:
        # Serialize writers before the first read; prevents duplicate cross-tab submissions on SQLite.
        db.execute(text("BEGIN IMMEDIATE"))
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def error(message, status=400):
    raise HTTPException(status, message)


def viewer(request: Request, db=Depends(transaction)):
    token = request.cookies.get("sc200_session", "")
    login = db.get(Login, hashlib.sha256(token.encode()).hexdigest())
    if not login or login.expires < now():
        error("请先登录", 401)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not secrets.compare_digest(
        request.headers.get("X-CSRF-Token", ""), login.csrf
    ):
        error("会话校验失败，请刷新后重试", 403)
    return db.get(User, login.user_id)


def owned(db, user, exam_id):
    exam = db.get(Exam, exam_id)
    if not exam or exam.user_id != user.id:
        error("记录不存在", 404)
    if exam.finished is None and exam.deadline and exam.deadline <= now():
        finish(db, exam, exam.deadline)
    return exam


def record(db, e, q, at=None):
    existing = db.scalar(select(Attempt).where(Attempt.exam_id == e.id, Attempt.question_id == q["id"]))
    if existing:
        return existing
    answer = e.state["answers"].get(q["id"], [])
    earned, possible = grade(q, answer)
    a = Attempt(
        id=uid(),
        user_id=e.user_id,
        exam_id=e.id,
        question_id=q["id"],
        topic=q["topic"],
        created=at or now(),
        correct=int(earned == possible),
        earned=earned,
        possible=possible,
        answer=answer,
    )
    db.add(a)
    if not a.correct:
        m = db.scalar(select(Mistake).where(Mistake.user_id == e.user_id, Mistake.question_id == q["id"]))
        if m:
            m.count += 1
            m.mastered = 0
            m.updated = a.created
        else:
            db.add(
                Mistake(
                    id=uid(), user_id=e.user_id, question_id=q["id"], count=1, mastered=0, updated=a.created
                )
            )
    db.flush()
    return a


def finish(db, e, at=None):
    if e.finished is not None:
        return
    e.finished = at or now()
    for q in e.state["questions"]:
        record(db, e, q, e.finished)
    e.version += 1


def exam_out(db, e):
    attempts = {a.question_id: a for a in db.scalars(select(Attempt).where(Attempt.exam_id == e.id))}
    earned = sum(x.earned for x in attempts.values())
    possible = sum(grade(q, [])[1] for q in e.state["questions"])
    return dict(
        id=e.id,
        mode=e.mode,
        started=e.started,
        deadline=e.deadline,
        server_time=now(),
        finished=e.finished,
        version=e.version,
        feedback=e.state["feedback"],
        answers=e.state["answers"],
        flags=e.state.get("flags", []),
        questions=[public_question(q, bool(e.finished) or q["id"] in attempts) for q in e.state["questions"]],
        results={
            k: dict(correct=bool(v.correct), earned=v.earned, possible=v.possible)
            for k, v in attempts.items()
        },
        score=round(earned / possible * 100, 1) if e.finished and possible else None,
        seconds=e.state.get("seconds", 0),
    )


async def expire_loop():
    while True:
        await asyncio.sleep(10)
        try:
            await asyncio.to_thread(expire_once)
        except Exception:
            import logging

            logging.exception("Expiration sweep failed")


def expire_once():
    with SessionLocal() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        for e in db.scalars(select(Exam).where(Exam.finished.is_(None), Exam.deadline <= now())):
            finish(db, e, e.deadline)
        db.commit()


@asynccontextmanager
async def lifespan(app):
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    expire_once()
    task = asyncio.create_task(expire_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="知序 SC-200 学习 API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def guard(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = {
            str(request.base_url).rstrip("/"),
            *os.getenv("SC200_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
        }
        if origin and origin not in allowed:
            return JSONResponse({"detail": "请求来源不受信任"}, status_code=403)
        if int(request.headers.get("content-length", "0")) > 12 * 1024 * 1024:
            return JSONResponse({"detail": "导入文件过大，最多 12 MB"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[\w\-\u4e00-\u9fff]+$")
    password: str = Field(min_length=8, max_length=128)


def login_response(db, user, response):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(
        Login(
            token=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            csrf=csrf,
            expires=now() + 30 * 86400,
        )
    )
    response.set_cookie(
        "sc200_session",
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("SC200_SECURE_COOKIE") == "1",
        max_age=30 * 86400,
    )
    return {"username": user.username, "timezone": user.timezone, "csrf": csrf}


@app.post("/api/v1/auth/register", status_code=201)
def register(body: Credentials, response: Response, db=Depends(transaction)):
    if db.scalar(select(User).where(User.username == body.username)):
        error("用户名已被使用", 409)
    u = User(id=uid(), username=body.username, password=hasher.hash(body.password))
    db.add(u)
    db.flush()
    return login_response(db, u, response)


@app.post("/api/v1/auth/login")
def login(body: Credentials, response: Response, db=Depends(transaction)):
    u = db.scalar(select(User).where(User.username == body.username))
    try:
        if not u:
            error("用户名或密码错误", 401)
        hasher.verify(u.password, body.password)
    except VerificationError:
        error("用户名或密码错误", 401)
    return login_response(db, u, response)


@app.get("/api/v1/auth/me")
def me(request: Request, u=Depends(viewer), db=Depends(transaction)):
    token = hashlib.sha256(request.cookies["sc200_session"].encode()).hexdigest()
    return {"username": u.username, "timezone": u.timezone, "csrf": db.get(Login, token).csrf}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, u=Depends(viewer), db=Depends(transaction)):
    db.execute(
        delete(Login).where(
            Login.token == hashlib.sha256(request.cookies["sc200_session"].encode()).hexdigest()
        )
    )
    response.delete_cookie("sc200_session")
    return {"ok": True}


@app.get("/api/v1/bank")
def bank_info():
    qs = bank()["questions"]
    ready = [q for q in qs if q["status"] == "ready"]
    return dict(
        version=bank()["version"],
        total=len(qs),
        ready=len(ready),
        review=len(qs) - len(ready),
        translated=sum(bool(q["zh"]) for q in qs),
        topics=[
            dict(id=t, total=sum(q["topic"] == t for q in qs), ready=sum(q["topic"] == t for q in ready))
            for t in sorted({q["topic"] for q in qs})
        ],
        tags=sorted({t for q in ready for t in q["tags"]}),
        domains=dict(Counter(q["domain"] for q in ready)),
        domain_note="能力领域由题目内容分类，题库来源为用户 PDF，非微软官方题库。",
    )


@app.get("/api/v1/bank/review")
def bank_review(u=Depends(viewer)):
    return [
        dict(
            id=q["id"],
            topic=q["topic"],
            pages=q["pages"],
            type=q["type"],
            issues=q["issues"],
            en=q["en"],
            zh=q["zh"],
            translation_status=q["translation_status"],
        )
        for q in bank()["questions"]
        if q["status"] != "ready"
    ]


@app.get("/api/v1/bank/review/{question_id}")
def review_question(question_id: str, u=Depends(viewer)):
    q = question_map().get(question_id)
    if not q or q["status"] == "ready":
        error("待核对题目不存在", 404)
    return public_question(q, True)


@app.get("/api/v1/bank/review/{question_id}/assets/{filename}")
def review_asset(question_id: str, filename: str, u=Depends(viewer)):
    q = question_map().get(question_id)
    if not q or q["status"] == "ready":
        error("待核对题目不存在", 404)
    allowed = set(q.get("assets", []) + q.get("answer_assets", []) + q.get("case_assets", []))
    if filename not in allowed or Path(filename).name != filename:
        error("图片不存在", 404)
    path = DATA / "assets" / filename
    if not path.is_file():
        path = ROOT / "data/assets" / filename
    if not path.is_file():
        error("图片不存在", 404)
    return FileResponse(path)


class NewExam(BaseModel):
    mode: Literal["exam", "random", "topic", "wrong"] = "random"
    count: int = Field(default=10, ge=1, le=100)
    topic: int | None = None
    tag: str | None = None
    feedback: bool = True


@app.post("/api/v1/sessions", status_code=201)
def create_exam(body: NewExam, u=Depends(viewer), db=Depends(transaction)):
    qs = [q for q in bank()["questions"] if q["status"] == "ready"]
    if body.mode == "topic" and body.topic is None and not body.tag:
        error("请选择章节或标签")
    if body.topic is not None:
        qs = [q for q in qs if q["topic"] == body.topic]
    if body.tag:
        qs = [q for q in qs if body.tag in q["tags"]]
    if body.mode == "wrong":
        wrong = set(
            db.scalars(select(Mistake.question_id).where(Mistake.user_id == u.id, Mistake.mastered == 0))
        )
        qs = [q for q in qs if q["id"] in wrong]
    if len(qs) < body.count:
        error(f"当前可用题目 {len(qs)} 道，请调整题量或筛选条件")
    rng = random.SystemRandom()
    if body.mode == "exam":
        if body.count not in (40, 50, 60):
            error("模拟考试支持 40、50 或 60 题")
        weights = [("operations", 0.4), ("response", 0.36), ("hunting", 0.24)]
        quotas = {k: math.floor(body.count * w) for k, w in weights}
        for k, _ in sorted(weights, key=lambda x: body.count * x[1] - quotas[x[0]], reverse=True)[
            : body.count - sum(quotas.values())
        ]:
            quotas[k] += 1
        selected = []
        for domain, count in quotas.items():
            group = [q for q in qs if q["domain"] == domain]
            if len(group) < count:
                error(f"{domain} 领域需要 {count} 题，当前仅 {len(group)} 题，请减少题量")
            selected.extend(rng.sample(group, count))
        rng.shuffle(selected)
    else:
        selected = rng.sample(qs, body.count)
    # Keep shared-case questions adjacent and ordered; other selected questions keep their randomized order.
    ordered = []
    seen = set()
    for q in selected:
        if q["id"] in seen:
            continue
        group = (
            sorted(
                [
                    x
                    for x in selected
                    if x["topic"] == q["topic"] and x.get("case_en") == q["case_en"] and x["id"] not in seen
                ],
                key=lambda x: x["number"],
            )
            if q.get("case_en")
            else [q]
        )
        ordered.extend(group)
        seen.update(x["id"] for x in group)
    e = Exam(
        id=uid(),
        user_id=u.id,
        mode=body.mode,
        started=now(),
        deadline=now() + 6000 if body.mode == "exam" else None,
        state=dict(
            questions=copy.deepcopy(ordered),
            answers={},
            flags=[],
            feedback=body.feedback and body.mode != "exam",
            seconds=0,
            heartbeat=now(),
            bank_version=bank()["version"],
        ),
    )
    db.add(e)
    db.flush()
    return exam_out(db, e)


@app.get("/api/v1/sessions")
def sessions(u=Depends(viewer), db=Depends(transaction)):
    rows = list(db.scalars(select(Exam).where(Exam.user_id == u.id).order_by(Exam.started.desc()).limit(100)))
    for e in rows:
        if e.finished is None and e.deadline and e.deadline <= now():
            finish(db, e, e.deadline)
    return [
        dict(
            id=e.id,
            mode=e.mode,
            started=e.started,
            finished=e.finished,
            count=len(e.state["questions"]),
            score=exam_out(db, e)["score"],
            seconds=e.state.get("seconds", 0),
        )
        for e in rows
    ]


@app.get("/api/v1/sessions/{exam_id}")
def get_exam(exam_id: str, u=Depends(viewer), db=Depends(transaction)):
    return exam_out(db, owned(db, u, exam_id))


class AnswerIn(BaseModel):
    question_id: str
    answer: list[str] = Field(max_length=30)
    version: int
    submit: bool = False
    flagged: bool | None = None


def validate_answer(q, answer):
    if q["type"] in ("single", "multiple"):
        if len(answer) != len(set(answer)) or not set(answer).issubset({o["id"] for o in q["options"]}):
            error("答案选项不合法")
        if q["type"] == "single" and len(answer) > 1:
            error("单选题只能选择一个选项")
    else:
        if len(answer) > len(q["slots"]):
            error("答案数量不合法")
        for i, a in enumerate(answer):
            if a and a not in [o["id"] for o in q["slots"][i]["options"]]:
                error("答题槽选项不合法")


@app.put("/api/v1/sessions/{exam_id}/answer")
def answer(exam_id: str, body: AnswerIn, u=Depends(viewer), db=Depends(transaction)):
    e = owned(db, u, exam_id)
    if e.finished:
        return exam_out(db, e)
    if body.version != e.version:
        error("记录已在其他页面更新，请刷新后重试", 409)
    q = next((q for q in e.state["questions"] if q["id"] == body.question_id), None)
    if not q:
        error("题目不属于本次训练", 404)
    if db.scalar(select(Attempt).where(Attempt.exam_id == e.id, Attempt.question_id == q["id"])):
        error("此题已提交，不能修改", 409)
    validate_answer(q, body.answer)
    state = copy.deepcopy(e.state)
    state["answers"][q["id"]] = body.answer
    if body.flagged is not None:
        flags = set(state["flags"])
        flags.add(q["id"]) if body.flagged else flags.discard(q["id"])
        state["flags"] = list(flags)
    e.state = state
    e.version += 1
    if body.submit:
        if not state["feedback"]:
            error("本次训练在交卷后显示答案")
        record(db, e, q)
    db.flush()
    return exam_out(db, e)


@app.post("/api/v1/sessions/{exam_id}/finish")
def submit_exam(exam_id: str, u=Depends(viewer), db=Depends(transaction)):
    e = owned(db, u, exam_id)
    finish(db, e)
    db.flush()
    return exam_out(db, e)


@app.post("/api/v1/sessions/{exam_id}/heartbeat")
def heartbeat(exam_id: str, u=Depends(viewer), db=Depends(transaction)):
    e = owned(db, u, exam_id)
    if e.finished:
        return {"finished": True}
    state = copy.deepcopy(e.state)
    elapsed = min(20, max(0, int(now() - state.get("heartbeat", now()))))
    state["heartbeat"] = now()
    state["seconds"] += elapsed
    e.state = state
    day = datetime.fromtimestamp(now(), ZoneInfo(u.timezone)).date().isoformat()
    a = db.scalar(select(Activity).where(Activity.user_id == u.id, Activity.day == day))
    if a:
        a.seconds += elapsed
    else:
        db.add(Activity(id=uid(), user_id=u.id, day=day, seconds=elapsed))
    return {"finished": False, "seconds": state["seconds"]}


@app.get("/api/v1/stats")
def stats(u=Depends(viewer), db=Depends(transaction)):
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == u.id)))
    exams = list(
        db.scalars(
            select(Exam)
            .where(Exam.user_id == u.id, Exam.finished.is_not(None), Exam.mode == "exam")
            .order_by(Exam.finished)
        )
    )
    scores = [
        dict(
            id=e.id,
            date=datetime.fromtimestamp(e.finished, ZoneInfo(u.timezone)).isoformat(),
            score=exam_out(db, e)["score"],
        )
        for e in exams
    ]
    daily = defaultdict(lambda: dict(count=0, correct=0, seconds=0))
    topics = defaultdict(lambda: dict(count=0, correct=0))
    for a in attempts:
        day = datetime.fromtimestamp(a.created, ZoneInfo(u.timezone)).date().isoformat()
        daily[day]["count"] += 1
        daily[day]["correct"] += a.correct
        topics[a.topic]["count"] += 1
        topics[a.topic]["correct"] += a.correct
    for activity in db.scalars(select(Activity).where(Activity.user_id == u.id)):
        daily[activity.day]["seconds"] = activity.seconds
    total = len(attempts)
    correct = sum(a.correct for a in attempts)
    return dict(
        total=total,
        correct=correct,
        accuracy=round(correct / total * 100, 1) if total else 0,
        exam_average=round(sum(s["score"] for s in scores) / len(scores), 1) if scores else 0,
        exam_count=len(scores),
        trend=scores,
        daily=dict(sorted(daily.items())),
        topics=topics,
        seconds=sum(d["seconds"] for d in daily.values()),
        wrong=db.scalar(
            select(__import__("sqlalchemy").func.count())
            .select_from(Mistake)
            .where(Mistake.user_id == u.id, Mistake.mastered == 0)
        ),
    )


@app.get("/api/v1/mistakes")
def mistakes(u=Depends(viewer), db=Depends(transaction)):
    qs = question_map()
    return [
        dict(
            id=m.question_id,
            count=m.count,
            mastered=bool(m.mastered),
            updated=m.updated,
            question=public_question(qs[m.question_id], True),
        )
        for m in db.scalars(select(Mistake).where(Mistake.user_id == u.id).order_by(Mistake.updated.desc()))
        if m.question_id in qs
    ]


class Mastery(BaseModel):
    mastered: bool


@app.patch("/api/v1/mistakes/{question_id}")
def mastery(question_id: str, body: Mastery, u=Depends(viewer), db=Depends(transaction)):
    m = db.scalar(select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == question_id))
    if not m:
        error("错题不存在", 404)
    m.mastered = int(body.mastered)
    return {"ok": True}


@app.get("/api/v1/sessions/{exam_id}/assets/{filename}")
def asset(exam_id: str, filename: str, u=Depends(viewer), db=Depends(transaction)):
    e = owned(db, u, exam_id)
    permitted = set()
    for q in e.state["questions"]:
        permitted.update(q.get("assets", []))
        permitted.update(q.get("case_assets", []))
        if e.finished or db.scalar(
            select(Attempt).where(Attempt.exam_id == e.id, Attempt.question_id == q["id"])
        ):
            permitted.update(q.get("answer_assets", []))
    if filename not in permitted or Path(filename).name != filename:
        error("图片不可访问", 404)
    path = DATA / "assets" / filename
    if not path.is_file():
        path = ROOT / "data/assets" / filename
    if not path.is_file():
        error("图片不存在", 404)
    return FileResponse(path)


@app.get("/api/v1/export")
def export(u=Depends(viewer), db=Depends(transaction)):
    rows = list(db.scalars(select(Exam).where(Exam.user_id == u.id, Exam.finished.is_not(None))))
    payload = dict(
        schema_version=1,
        bank_version=bank()["version"],
        exported_at=now(),
        sessions=[
            dict(
                id=e.id,
                mode=e.mode,
                started=e.started,
                finished=e.finished,
                question_ids=[q["id"] for q in e.state["questions"]],
                answers=e.state["answers"],
                seconds=e.state.get("seconds", 0),
            )
            for e in rows
        ],
        mastered=list(
            db.scalars(select(Mistake.question_id).where(Mistake.user_id == u.id, Mistake.mastered == 1))
        ),
    )
    return Response(
        json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="sc200-progress.json"'},
    )


class ImportedSession(BaseModel):
    id: str = Field(max_length=80)
    mode: Literal["exam", "random", "topic", "wrong"]
    started: float = Field(gt=0)
    finished: float = Field(gt=0)
    question_ids: list[str] = Field(min_length=1, max_length=100)
    answers: dict[str, list[str]]
    seconds: int = Field(default=0, ge=0, le=86400)


class ImportIn(BaseModel):
    schema_version: Literal[1]
    bank_version: str
    sessions: list[ImportedSession] = Field(max_length=1000)
    mastered: list[str] = Field(default_factory=list, max_length=2000)


@app.post("/api/v1/import")
def import_data(body: ImportIn, u=Depends(viewer), db=Depends(transaction)):
    qs = question_map()
    added = 0
    if body.bank_version != bank()["version"]:
        error("题库版本不同，请先使用匹配的题库再导入")
    for item in body.sessions:
        # Stable per-user import identity plus original identity for same-account backups.
        eid = uuid.uuid5(uuid.NAMESPACE_URL, u.id + ":" + item.id).hex
        original = db.get(Exam, item.id)
        if (original and original.user_id == u.id) or db.get(Exam, eid):
            continue
        if len(item.question_ids) != len(set(item.question_ids)) or any(
            q not in qs or qs[q]["status"] != "ready" for q in item.question_ids
        ):
            error("备份包含无效题目")
        if item.finished < item.started or item.finished > now() + 60:
            error("备份时间不合法")
        selected = [qs[q] for q in item.question_ids]
        for q in selected:
            validate_answer(q, item.answers.get(q["id"], []))
        e = Exam(
            id=eid,
            user_id=u.id,
            mode=item.mode,
            started=item.started,
            deadline=None,
            state=dict(
                questions=copy.deepcopy(selected),
                answers={q["id"]: item.answers.get(q["id"], []) for q in selected},
                flags=[],
                feedback=False,
                seconds=item.seconds,
                bank_version=bank()["version"],
            ),
        )
        db.add(e)
        db.flush()
        finish(db, e, item.finished)
        day = datetime.fromtimestamp(item.finished, ZoneInfo(u.timezone)).date().isoformat()
        activity = db.scalar(select(Activity).where(Activity.user_id == u.id, Activity.day == day))
        if activity:
            activity.seconds += item.seconds
        else:
            db.add(Activity(id=uid(), user_id=u.id, day=day, seconds=item.seconds))
        added += 1
    for qid in body.mastered:
        m = db.scalar(select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == qid))
        if m:
            m.mastered = 1
    return {"imported": added, "skipped": len(body.sessions) - added}


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "questions": len(bank()["questions"])}


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/"):
        error("接口不存在", 404)
    root = (ROOT / "frontend/dist").resolve()
    candidate = (root / path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return FileResponse(candidate)
    if (root / "index.html").exists():
        return FileResponse(root / "index.html")
    return {"message": "请运行前端开发服务，或先执行 npm run build", "docs": "/docs"}
