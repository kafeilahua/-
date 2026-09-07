import os
from pathlib import Path

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("SC200_DATA_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    os.getenv("SC200_DATABASE_URL", f"sqlite:///{DATA}/study.db"),
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Shanghai")


class Login(Base):
    __tablename__ = "logins"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf: Mapped[str] = mapped_column(String)
    expires: Mapped[float] = mapped_column(Float)


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String)
    started: Mapped[float] = mapped_column(Float)
    deadline: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("exam_id", "question_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(String)
    topic: Mapped[int] = mapped_column(Integer)
    created: Mapped[float] = mapped_column(Float)
    correct: Mapped[int] = mapped_column(Integer)
    earned: Mapped[int] = mapped_column(Integer)
    possible: Mapped[int] = mapped_column(Integer)
    answer: Mapped[list] = mapped_column(JSON)


class Mistake(Base):
    __tablename__ = "mistakes"
    __table_args__ = (UniqueConstraint("user_id", "question_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String)
    count: Mapped[int] = mapped_column(Integer, default=1)
    mastered: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[float] = mapped_column(Float)


class Activity(Base):
    __tablename__ = "activity"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[str] = mapped_column(String)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
