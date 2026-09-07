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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from alembic.config import Config
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, or_, select, text

from alembic import command

from .bank import bank, grade, public_question, question_map
from .db import (
    DATA,
    ROOT,
    Activity,
    Attempt,
    Exam,
    Login,
    Mistake,
    PersonalQuestion,
    QuestionReport,
    SessionLocal,
    User,
)

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
    m = db.scalar(select(Mistake).where(Mistake.user_id == e.user_id, Mistake.question_id == q["id"]))
    if not a.correct:
        if m:
            source = f"{e.state.get('source_id', e.id)}:{q['id']}"
            if source in m.imported_wrong_sources:
                m.imported_wrong_sources = [value for value in m.imported_wrong_sources if value != source]
            else:
                m.count += 1
            m.updated = max(m.updated, a.created)
            # Importing older attempts must not undo more recent review progress.
            if a.created >= m.schedule_updated:
                m.mastered = 0
                m.review_stage = 0
                m.due_at = a.created
                m.last_reviewed = a.created
                m.schedule_updated = a.created
        else:
            db.add(
                Mistake(
                    id=uid(),
                    user_id=e.user_id,
                    question_id=q["id"],
                    count=1,
                    mastered=0,
                    updated=a.created,
                    due_at=a.created,
                    review_stage=0,
                    last_reviewed=None,
                    schedule_updated=a.created,
                )
            )
    elif m and not m.mastered and a.created >= m.schedule_updated:
        m.last_reviewed = a.created
        m.schedule_updated = a.created
        if m.due_at is None or m.due_at <= a.created:
            intervals = (1, 3, 7, 14, 30)
            m.review_stage = min(m.review_stage + 1, len(intervals))
            m.due_at = a.created + intervals[m.review_stage - 1] * 86400
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
    mode: Literal["exam", "random", "topic", "wrong", "favorite"] = "random"
    count: int = Field(default=10, ge=1, le=100)
    topic: int | None = None
    tag: str | None = None
    feedback: bool = True
    question_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    due_only: bool = False


@app.post("/api/v1/sessions", status_code=201)
def create_exam(body: NewExam, u=Depends(viewer), db=Depends(transaction)):
    qs = [q for q in bank()["questions"] if q["status"] == "ready"]
    if body.mode == "topic" and body.topic is None and not body.tag:
        error("请选择章节或标签")
    if body.topic is not None:
        qs = [q for q in qs if q["topic"] == body.topic]
    if body.tag:
        qs = [q for q in qs if body.tag in q["tags"]]
    if body.question_ids is not None and body.mode not in ("wrong", "favorite"):
        error("只有错题和收藏练习支持指定题目")
    if body.due_only and body.mode != "wrong":
        error("到期筛选仅支持错题练习")
    if body.mode == "wrong":
        conditions = [Mistake.user_id == u.id]
        if body.question_ids is None or body.due_only:
            conditions.append(Mistake.mastered == 0)
        if body.due_only:
            conditions.append(or_(Mistake.due_at.is_(None), Mistake.due_at <= now()))
        permitted = set(db.scalars(select(Mistake.question_id).where(*conditions)))
        qs = [q for q in qs if q["id"] in permitted]
    elif body.mode == "favorite":
        permitted = set(
            db.scalars(
                select(PersonalQuestion.question_id).where(
                    PersonalQuestion.user_id == u.id, PersonalQuestion.favorite == 1
                )
            )
        )
        qs = [q for q in qs if q["id"] in permitted]
    if body.question_ids is not None:
        requested = list(dict.fromkeys(body.question_ids))
        available = {q["id"]: q for q in qs}
        if any(qid not in available for qid in requested):
            error("所选题目不可用，或不属于你的错题/收藏范围")
        if body.count > len(requested):
            error(f"已选 {len(requested)} 道题，请调整题量；不会自动补充其他题目")
        qs = [available[qid] for qid in requested]
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
def mistakes(
    state: Literal["pending", "mastered", "all", "due"] = "all",
    topic: int | None = None,
    tag: str | None = None,
    min_count: int = Query(default=1, ge=1),
    sort: Literal["recent", "frequent", "due"] = "recent",
    q: str = Query(default="", max_length=200),
    last_days: int | None = Query(default=None, ge=1, le=3650),
    u=Depends(viewer),
    db=Depends(transaction),
):
    qs = question_map()
    conditions = [Mistake.user_id == u.id, Mistake.count >= min_count]
    if state in ("pending", "due"):
        conditions.append(Mistake.mastered == 0)
    elif state == "mastered":
        conditions.append(Mistake.mastered == 1)
    if state == "due":
        conditions.append(or_(Mistake.due_at.is_(None), Mistake.due_at <= now()))
    if last_days is not None:
        conditions.append(Mistake.updated >= now() - last_days * 86400)
    ordering = {
        "recent": [Mistake.updated.desc(), Mistake.question_id],
        "frequent": [Mistake.count.desc(), Mistake.updated.desc(), Mistake.question_id],
        "due": [Mistake.mastered, Mistake.due_at.asc(), Mistake.updated.desc(), Mistake.question_id],
    }[sort]
    result = []
    for m in db.scalars(select(Mistake).where(*conditions).order_by(*ordering)):
        question = qs.get(m.question_id)
        if not question or (topic is not None and question["topic"] != topic):
            continue
        if tag and tag not in question.get("tags", []):
            continue
        if (
            q.strip()
            and q.strip().casefold()
            not in " ".join(
                [
                    question["id"],
                    question.get("en") or "",
                    question.get("zh") or "",
                    *question.get("tags", []),
                ]
            ).casefold()
        ):
            continue
        result.append(
            dict(
                id=m.question_id,
                count=m.count,
                mastered=bool(m.mastered),
                updated=m.updated,
                due_at=m.due_at,
                review_stage=m.review_stage,
                last_reviewed=m.last_reviewed,
                question=public_question(question, True),
            )
        )
    return result


@app.get("/api/v1/mistakes/{question_id}/assets/{filename}")
def mistake_asset(question_id: str, filename: str, u=Depends(viewer), db=Depends(transaction)):
    item = db.scalar(select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == question_id))
    question = question_map().get(question_id)
    if not item or not question:
        error("错题图片不存在", 404)
    permitted = set(
        question.get("assets", []) + question.get("case_assets", []) + question.get("answer_assets", [])
    )
    if filename not in permitted or Path(filename).name != filename:
        error("错题图片不存在", 404)
    path = DATA / "assets" / filename
    if not path.is_file():
        path = ROOT / "data/assets" / filename
    if not path.is_file():
        error("图片不存在", 404)
    return FileResponse(path)


class Mastery(BaseModel):
    mastered: bool


@app.patch("/api/v1/mistakes/{question_id}")
def mastery(question_id: str, body: Mastery, u=Depends(viewer), db=Depends(transaction)):
    m = db.scalar(select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == question_id))
    if not m:
        error("错题不存在", 404)
    if bool(m.mastered) != body.mastered:
        m.mastered = int(body.mastered)
        m.schedule_updated = now()
        m.due_at = None if body.mastered else m.schedule_updated
        if not body.mastered:
            m.review_stage = 0
    return {"ok": True}


@app.get("/api/v1/review/summary")
def review_summary(u=Depends(viewer), db=Depends(transaction)):
    rows = list(db.scalars(select(Mistake).where(Mistake.user_id == u.id)))
    due = sum(not m.mastered and (m.due_at is None or m.due_at <= now()) for m in rows)
    pending = sum(not m.mastered for m in rows)
    qs = question_map()
    recent = defaultdict(list)
    tags = defaultdict(lambda: defaultdict(list))
    for a in db.scalars(select(Attempt).where(Attempt.user_id == u.id).order_by(Attempt.created)):
        if a.created >= now() - 30 * 86400:
            recent[a.topic].append(a.correct)
        local_date = datetime.fromtimestamp(a.created, ZoneInfo(u.timezone)).date()
        week = (local_date - timedelta(days=local_date.weekday())).isoformat()
        for tag in qs.get(a.question_id, {}).get("tags", []):
            tags[tag][week].append(a.correct)
    recommendations = [
        dict(
            topic=topic,
            attempts=len(results),
            accuracy=round(sum(results) / len(results) * 100, 1),
            ready_count=sum(q["topic"] == topic and q["status"] == "ready" for q in qs.values()),
        )
        for topic, results in recent.items()
        if len(results) >= 3
    ]
    recommendations.sort(key=lambda r: (r["accuracy"], -r["attempts"], r["topic"]))
    knowledge = []
    for tag, weeks in sorted(tags.items()):
        trend = [
            dict(week=week, accuracy=round(sum(results) / len(results) * 100, 1), count=len(results))
            for week, results in sorted(weeks.items())
        ]
        correct = sum(sum(results) for results in weeks.values())
        count = sum(len(results) for results in weeks.values())
        knowledge.append(
            dict(
                tag=tag,
                count=count,
                correct=correct,
                accuracy=round(correct / count * 100, 1),
                previous_accuracy=trend[-2]["accuracy"] if len(trend) > 1 else None,
                trend=trend,
            )
        )
    return dict(
        due_count=due,
        pending_count=pending,
        scheduled_count=pending - due,
        mastered_count=len(rows) - pending,
        recommendations=recommendations,
        knowledge=knowledge,
    )


def checked_question(question_id):
    question = question_map().get(question_id)
    if not question:
        error("题目不存在", 404)
    return question


def personal_out(question_id, item):
    return dict(
        question_id=question_id,
        favorite=bool(item.favorite) if item else False,
        note=item.note if item else "",
        updated=item.updated if item else None,
        version=item.version if item else 0,
    )


@app.get("/api/v1/questions/{question_id}/personal")
def personal(question_id: str, u=Depends(viewer), db=Depends(transaction)):
    checked_question(question_id)
    item = db.scalar(
        select(PersonalQuestion).where(
            PersonalQuestion.user_id == u.id, PersonalQuestion.question_id == question_id
        )
    )
    return personal_out(question_id, item)


class PersonalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool | None = None
    note: str | None = Field(default=None, max_length=10000)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_patch(self):
        updates = self.model_fields_set - {"version"}
        if not updates or any(getattr(self, key) is None for key in updates):
            raise ValueError("请提供收藏状态或笔记内容")
        return self


@app.patch("/api/v1/questions/{question_id}/personal")
def update_personal(question_id: str, body: PersonalIn, u=Depends(viewer), db=Depends(transaction)):
    checked_question(question_id)
    item = db.scalar(
        select(PersonalQuestion).where(
            PersonalQuestion.user_id == u.id, PersonalQuestion.question_id == question_id
        )
    )
    if body.version != (item.version if item else 0):
        error("笔记或收藏已在其他页面更新，请重新读取后保存", 409)
    if item is None:
        item = PersonalQuestion(
            id=uid(), user_id=u.id, question_id=question_id, favorite=0, note="", updated=now(), version=0
        )
        db.add(item)
    if body.favorite is not None:
        item.favorite = int(body.favorite)
    if body.note is not None:
        item.note = body.note
    item.updated = now()
    item.version += 1
    db.flush()
    return personal_out(question_id, item)


@app.get("/api/v1/library")
def library(u=Depends(viewer), db=Depends(transaction)):
    qs = question_map()
    return [
        dict(question=public_question(qs[item.question_id]), **personal_out(item.question_id, item))
        for item in db.scalars(
            select(PersonalQuestion)
            .where(
                PersonalQuestion.user_id == u.id,
                or_(PersonalQuestion.favorite == 1, PersonalQuestion.note != ""),
            )
            .order_by(PersonalQuestion.updated.desc(), PersonalQuestion.question_id)
        )
        if item.question_id in qs
    ]


def report_out(item):
    return dict(
        id=item.id,
        question_id=item.question_id,
        category=item.category,
        content=item.content,
        status=item.status,
        created=item.created,
    )


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Literal["translation", "answer", "image", "other"]
    content: str = Field(min_length=5, max_length=3000)


@app.post("/api/v1/questions/{question_id}/reports", status_code=201)
def create_report(question_id: str, body: ReportIn, u=Depends(viewer), db=Depends(transaction)):
    checked_question(question_id)
    item = QuestionReport(
        id=uid(),
        user_id=u.id,
        question_id=question_id,
        category=body.category,
        content=body.content,
        status="open",
        created=now(),
        updated=now(),
    )
    db.add(item)
    db.flush()
    return report_out(item)


@app.get("/api/v1/reports")
def reports(u=Depends(viewer), db=Depends(transaction)):
    return [
        report_out(item)
        for item in db.scalars(
            select(QuestionReport)
            .where(QuestionReport.user_id == u.id)
            .order_by(QuestionReport.created.desc(), QuestionReport.id)
        )
    ]


class ReportStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["withdrawn"]


@app.patch("/api/v1/reports/{report_id}")
def withdraw_report(report_id: str, body: ReportStatus, u=Depends(viewer), db=Depends(transaction)):
    item = db.get(QuestionReport, report_id)
    if not item or item.user_id != u.id:
        error("反馈不存在", 404)
    if item.status != body.status:
        item.status = body.status
        item.updated = now()
    return report_out(item)


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


def recorded_wrong_sources(db, user_id):
    exams = {e.id: e for e in db.scalars(select(Exam).where(Exam.user_id == user_id))}
    sources = defaultdict(set)
    for a in db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.correct == 0)):
        e = exams[a.exam_id]
        sources[a.question_id].add(f"{e.state.get('source_id', e.id)}:{a.question_id}")
    return sources


@app.get("/api/v1/export")
def export(u=Depends(viewer), db=Depends(transaction)):
    rows = list(db.scalars(select(Exam).where(Exam.user_id == u.id, Exam.finished.is_not(None))))
    submissions = defaultdict(dict)
    for a in db.scalars(select(Attempt).where(Attempt.user_id == u.id)):
        submissions[a.exam_id][a.question_id] = a.created
    wrong_sources = recorded_wrong_sources(db, u.id)
    payload = dict(
        schema_version=2,
        bank_version=bank()["version"],
        exported_at=now(),
        sessions=[
            dict(
                id=e.state.get("source_id", e.id),
                mode=e.mode,
                started=e.started,
                finished=e.finished,
                question_ids=[q["id"] for q in e.state["questions"]],
                answers=e.state["answers"],
                submitted_at=submissions[e.id],
                seconds=e.state.get("seconds", 0),
            )
            for e in rows
        ],
        mastered=list(
            db.scalars(select(Mistake.question_id).where(Mistake.user_id == u.id, Mistake.mastered == 1))
        ),
        review=[
            dict(
                question_id=m.question_id,
                count=m.count,
                mastered=bool(m.mastered),
                updated=m.updated,
                due_at=m.due_at,
                review_stage=m.review_stage,
                last_reviewed=m.last_reviewed,
                schedule_updated=m.schedule_updated,
                wrong_sources=sorted(wrong_sources[m.question_id] | set(m.imported_wrong_sources)),
            )
            for m in db.scalars(select(Mistake).where(Mistake.user_id == u.id))
        ],
        personal=[
            personal_out(item.question_id, item)
            for item in db.scalars(select(PersonalQuestion).where(PersonalQuestion.user_id == u.id))
        ],
        reports=[
            dict(report_out(item), id=item.source_id or item.id, updated=item.updated)
            for item in db.scalars(select(QuestionReport).where(QuestionReport.user_id == u.id))
        ],
    )
    return Response(
        json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="sc200-progress.json"'},
    )


class BackupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ImportedSession(BackupModel):
    id: str = Field(min_length=1, max_length=80)
    mode: Literal["exam", "random", "topic", "wrong", "favorite"]
    started: float = Field(gt=0)
    finished: float = Field(gt=0)
    question_ids: list[str] = Field(min_length=1, max_length=100)
    answers: dict[str, list[str]] = Field(max_length=100)
    submitted_at: dict[str, float] = Field(default_factory=dict, max_length=100)
    seconds: int = Field(default=0, ge=0, le=86400)


class ImportedPersonal(BackupModel):
    question_id: str
    favorite: bool
    note: str = Field(max_length=10000)
    updated: float = Field(gt=0)
    version: int = Field(ge=1)


class ImportedReview(BackupModel):
    question_id: str
    count: int = Field(ge=1, le=1000000)
    mastered: bool
    updated: float = Field(gt=0)
    due_at: float | None = Field(default=None, gt=0)
    review_stage: int = Field(ge=0, le=5)
    last_reviewed: float | None = Field(default=None, gt=0)
    schedule_updated: float = Field(gt=0)

    wrong_sources: list[str] = Field(min_length=1, max_length=100000)


class ImportedReport(BackupModel):
    id: str = Field(min_length=1, max_length=80)
    question_id: str
    category: Literal["translation", "answer", "image", "other"]
    content: str = Field(min_length=5, max_length=3000)
    status: Literal["open", "withdrawn"]
    created: float = Field(gt=0)
    updated: float = Field(gt=0)


class ImportIn(BackupModel):
    schema_version: Literal[1, 2]
    bank_version: str
    exported_at: float | None = Field(default=None, gt=0)
    sessions: list[ImportedSession] = Field(max_length=1000)
    mastered: list[str] = Field(default_factory=list, max_length=2000)
    review: list[ImportedReview] = Field(default_factory=list, max_length=2000)
    personal: list[ImportedPersonal] = Field(default_factory=list, max_length=2000)
    reports: list[ImportedReport] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def valid_version(self):
        if self.schema_version == 1 and (self.review or self.personal or self.reports):
            raise ValueError("旧版备份不支持新增的个人资料字段")
        return self


def validate_backup(body, qs):
    cutoff = now() + 60
    if body.bank_version != bank()["version"]:
        error("题库版本不同，请先使用匹配的题库再导入")
    if body.exported_at is not None and body.exported_at > cutoff:
        error("备份时间不合法")
    # Validate every entry before deduplication so malformed backups never partially succeed.
    for entries, key in (
        (body.sessions, "id"),
        (body.review, "question_id"),
        (body.personal, "question_id"),
        (body.reports, "id"),
    ):
        identifiers = [getattr(item, key) for item in entries]
        if len(set(identifiers)) != len(identifiers):
            error("备份包含重复记录")
    for item in body.sessions:
        ids = set(item.question_ids)
        if len(ids) != len(item.question_ids) or any(q not in qs or qs[q]["status"] != "ready" for q in ids):
            error("备份包含无效题目")
        if set(item.answers) - ids or set(item.submitted_at) - ids:
            error("备份包含不属于训练的答案记录")
        if item.finished < item.started or item.finished > cutoff:
            error("备份时间不合法")
        for qid, value in item.submitted_at.items():
            if not math.isfinite(value) or not item.started <= value <= item.finished:
                error("备份提交时间不合法")
        for qid in ids:
            validate_answer(qs[qid], item.answers.get(qid, []))
    if any(qid not in qs for qid in body.mastered):
        error("备份包含无效题目")
    for item in [*body.review, *body.personal, *body.reports]:
        if item.question_id not in qs:
            error("备份包含无效题目")
        if item.updated > cutoff:
            error("备份时间不合法")
    for item in body.review:
        if len(item.wrong_sources) != len(set(item.wrong_sources)) or item.count != len(item.wrong_sources):
            error("错题次数与作答来源不一致")
        if any(
            len(source) > 200
            or not source.endswith(":" + item.question_id)
            or len(source) <= len(item.question_id) + 1
            for source in item.wrong_sources
        ):
            error("错题作答来源不合法")
        if qs[item.question_id]["status"] != "ready":
            error("错题备份包含不可评分题目")
        if item.schedule_updated > cutoff or (
            item.last_reviewed is not None and item.last_reviewed > item.schedule_updated
        ):
            error("复习计划时间不合法")
        if item.mastered and item.due_at is not None:
            error("已掌握题目不能设置复习到期时间")
        if not item.mastered and (
            item.due_at is None or item.due_at > item.schedule_updated + 30 * 86400 + 60
        ):
            error("复习到期时间不合法")
    for item in body.reports:
        if item.created > item.updated or len(item.content.strip()) < 5:
            error("反馈备份不合法")


@app.post("/api/v1/import")
def import_data(body: ImportIn, u=Depends(viewer), db=Depends(transaction)):
    qs = question_map()
    validate_backup(body, qs)
    added = 0
    local_schedules = {
        m.question_id: m.schedule_updated for m in db.scalars(select(Mistake).where(Mistake.user_id == u.id))
    }
    for item in sorted(body.sessions, key=lambda item: item.finished):
        eid = uuid.uuid5(uuid.NAMESPACE_URL, u.id + ":" + item.id).hex
        original = db.get(Exam, item.id)
        if (original and original.user_id == u.id) or db.get(Exam, eid):
            continue
        selected = [qs[q] for q in item.question_ids]
        e = Exam(
            id=eid,
            user_id=u.id,
            mode=item.mode,
            started=item.started,
            deadline=None,
            state=dict(
                source_id=item.id,
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
        for q in sorted(selected, key=lambda q: item.submitted_at.get(q["id"], item.finished)):
            record(db, e, q, item.submitted_at.get(q["id"], item.finished))
        finish(db, e, item.finished)
        day = datetime.fromtimestamp(item.finished, ZoneInfo(u.timezone)).date().isoformat()
        activity = db.scalar(select(Activity).where(Activity.user_id == u.id, Activity.day == day))
        if activity:
            activity.seconds += item.seconds
        else:
            db.add(Activity(id=uid(), user_id=u.id, day=day, seconds=item.seconds))
        added += 1
    if body.schema_version == 1:
        for qid in body.mastered:
            m = db.scalar(select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == qid))
            if m and qid not in local_schedules:
                m.mastered = 1
                m.due_at = None
    else:
        sources = recorded_wrong_sources(db, u.id)
        for item in body.review:
            m = db.scalar(
                select(Mistake).where(Mistake.user_id == u.id, Mistake.question_id == item.question_id)
            )
            if m is None:
                m = Mistake(
                    id=uid(),
                    user_id=u.id,
                    question_id=item.question_id,
                    count=0,
                    updated=item.updated,
                    imported_wrong_sources=[],
                )
                db.add(m)
            # A backup can contain wrong answers submitted in an unfinished session.
            # Preserve those sources without duplicating their count when that session is later imported.
            missing = (set(item.wrong_sources) | set(m.imported_wrong_sources)) - sources[item.question_id]
            m.imported_wrong_sources = sorted(missing)
            m.count = len(sources[item.question_id]) + len(missing)
            m.updated = max(m.updated, item.updated)
            if (
                item.question_id in local_schedules
                and local_schedules[item.question_id] >= item.schedule_updated
            ):
                continue
            m.mastered = int(item.mastered)
            m.due_at = item.due_at
            m.review_stage = item.review_stage
            m.last_reviewed = item.last_reviewed
            m.schedule_updated = item.schedule_updated
        for item in body.personal:
            current = db.scalar(
                select(PersonalQuestion).where(
                    PersonalQuestion.user_id == u.id, PersonalQuestion.question_id == item.question_id
                )
            )
            if current and current.updated >= item.updated:
                continue
            if current is None:
                current = PersonalQuestion(id=uid(), user_id=u.id, question_id=item.question_id, version=0)
                db.add(current)
            current.favorite = int(item.favorite)
            current.note = item.note
            current.updated = item.updated
            current.version = max(current.version + 1, item.version)
        for item in body.reports:
            original = db.get(QuestionReport, item.id)
            rid = uuid.uuid5(uuid.NAMESPACE_URL, u.id + ":report:" + item.id).hex
            current = original if original and original.user_id == u.id else db.get(QuestionReport, rid)
            if current:
                if current.updated < item.updated and item.status == "withdrawn":
                    current.status = item.status
                    current.updated = item.updated
                continue
            db.add(
                QuestionReport(
                    id=rid,
                    source_id=item.id,
                    user_id=u.id,
                    question_id=item.question_id,
                    category=item.category,
                    content=item.content,
                    status=item.status,
                    created=item.created,
                    updated=item.updated,
                )
            )
    db.flush()
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
