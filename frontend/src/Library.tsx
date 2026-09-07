import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bookmark,
  ChevronDown,
  Flag,
  LoaderCircle,
  NotebookPen,
  Search,
} from "lucide-react";
import { api, send } from "./api";
import type { Session } from "./types";
import type { LibraryItem, Personal, QuestionReport } from "./personal-types";
import { reportLabels } from "./personal-types";
import QuestionTools from "./QuestionTools";
import "./personal.css";

export default function Library({ owner }: { owner: string }) {
  const navigate = useNavigate();
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [reports, setReports] = useState<QuestionReport[]>([]);
  const [tab, setTab] = useState("favorites");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [count, setCount] = useState(10);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<LibraryItem[]>("/library"),
      api<QuestionReport[]>("/reports"),
    ])
      .then(([library, feedback]) => {
        if (active) {
          setItems(library);
          setReports(feedback);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items
      .filter(
        (item) =>
          (tab === "notes" ? !!item.note.trim() : item.favorite) &&
          `${item.question_id} ${item.question.zh} ${item.question.en} ${item.note} ${item.question.tags.join(" ")}`
            .toLowerCase()
            .includes(term),
      )
      .sort((a, b) => (b.updated || 0) - (a.updated || 0));
  }, [items, tab, search]);
  const eligible = filtered.filter(
    (item) => item.favorite && item.question.status === "ready",
  );
  const visibleReports = reports.filter((r) =>
    `${r.question_id} ${r.content} ${reportLabels[r.category]}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );
  async function train() {
    const selected = eligible.slice(0, count);
    if (!selected.length || busy) return;
    setBusy(true);
    setError("");
    try {
      const session = await send<Session>("/sessions", {
        mode: "favorite",
        count: selected.length,
        question_ids: selected.map((x) => x.question_id),
        feedback: true,
      });
      navigate(`/session/${session.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function changed(personal: Personal) {
    setItems((current) =>
      current.map((item) =>
        item.question_id === personal.question_id
          ? { ...item, ...personal }
          : item,
      ),
    );
  }
  async function withdraw(id: string) {
    setBusy(true);
    setError("");
    try {
      await send(`/reports/${id}`, { status: "withdrawn" }, "PATCH");
      setReports((rows) =>
        rows.map((row) =>
          row.id === id ? { ...row, status: "withdrawn" } : row,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">KEEP WHAT HELPS YOU LEARN</div>
          <h1>把理解，留在这里</h1>
          <p>收藏值得回看的题，把解题思路写成自己的笔记。</p>
        </div>
        <Link className="outline" to="/practice">
          继续练习 <ArrowRight size={16} />
        </Link>
      </div>
      <div className="library-summary">
        <div>
          <Bookmark size={22} />
          <strong>{items.filter((x) => x.favorite).length}</strong>
          <span>我的收藏</span>
        </div>
        <div>
          <NotebookPen size={22} />
          <strong>{items.filter((x) => x.note.trim()).length}</strong>
          <span>学习笔记</span>
        </div>
        <div>
          <Flag size={22} />
          <strong>{reports.filter((x) => x.status === "open").length}</strong>
          <span>待核对反馈</span>
        </div>
      </div>
      {error ? (
        <div className="error" role="alert">
          {error}
        </div>
      ) : null}
      <section className="panel library-panel">
        <div className="list-toolbar">
          <div className="tabs" aria-label="学习资料分类">
            {[
              ["favorites", "收藏题目"],
              ["notes", "学习笔记"],
              ["reports", "纠错反馈"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={tab === value ? "selected" : ""}
                aria-pressed={tab === value}
                onClick={() => {
                  setTab(value);
                  setExpanded("");
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="search">
            <Search size={17} />
            <input
              aria-label="搜索收藏、笔记或反馈"
              placeholder="搜索题目、笔记或反馈"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        {tab !== "reports" ? (
          <div className="library-training">
            <span>
              当前 {filtered.length} 道 · {eligible.length} 道已收藏且可练习
            </span>
            <div>
              <label htmlFor="library-count">重练题量</label>
              <select
                id="library-count"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              >
                {[10, 20, 50].map((n) => (
                  <option key={n} value={n}>
                    最多 {n} 题
                  </option>
                ))}
              </select>
              <button
                className="primary compact"
                disabled={busy || !eligible.length}
                onClick={train}
              >
                练习当前收藏（{Math.min(count, eligible.length)}）
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        ) : (
          <p className="library-report-note">
            反馈仅记录在当前平台，尚未接入自动审核。你可以撤回已不需要处理的反馈。
          </p>
        )}
        {loading ? (
          <div className="loading">
            <LoaderCircle className="spin" />
            正在读取学习资料…
          </div>
        ) : tab === "reports" ? (
          visibleReports.length ? (
            <div className="report-list">
              {visibleReports.map((r) => (
                <article key={r.id}>
                  <div className="report-meta">
                    <b>{r.question_id}</b>
                    <span className="subtle-tag">
                      {reportLabels[r.category]}
                    </span>
                    <span
                      className={
                        r.status === "open" ? "state-active" : "state-complete"
                      }
                    >
                      {r.status === "open" ? "待核对" : "已撤回"}
                    </span>
                  </div>
                  <p>{r.content}</p>
                  <div className="personal-editor-footer">
                    <small>
                      {new Date(r.created * 1000).toLocaleString("zh-CN")}
                    </small>
                    {r.status === "open" ? (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => withdraw(r.id)}
                      >
                        撤回反馈
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty">
              <Flag size={36} />
              <h3>{search ? "没有匹配的反馈" : "还没有纠错反馈"}</h3>
              <p>发现翻译、答案或附图问题时，可在题目下方记录反馈。</p>
            </div>
          )
        ) : filtered.length ? (
          filtered.map((item) => (
            <article className="library-item" key={item.question_id}>
              <div className="library-item-meta">
                <span className="pill">
                  Topic {item.question.topic} · 第 {item.question.number} 题
                </span>
                <span>
                  {item.question.status === "ready"
                    ? "可练习"
                    : "待核对 · 暂不评分"}
                </span>
                <small>
                  {item.updated
                    ? new Date(item.updated * 1000).toLocaleDateString("zh-CN")
                    : ""}
                </small>
              </div>
              <button
                className="library-item-title"
                aria-expanded={expanded === item.question_id}
                onClick={() =>
                  setExpanded(
                    expanded === item.question_id ? "" : item.question_id,
                  )
                }
              >
                <span>{item.question.zh || item.question.en}</span>
                <ChevronDown size={19} />
              </button>
              {item.note && expanded !== item.question_id ? (
                <p className="note-preview">
                  <NotebookPen size={15} />
                  <span>{item.note}</span>
                </p>
              ) : null}
              {expanded === item.question_id ? (
                <div className="library-item-detail">
                  <details>
                    <summary>英文原文</summary>
                    <p className="question-text">{item.question.en}</p>
                  </details>
                  <QuestionTools
                    key={item.question_id}
                    owner={owner}
                    questionId={item.question_id}
                    initial={item}
                    onChange={changed}
                    onReport={(r) => setReports((rows) => [r, ...rows])}
                  />
                </div>
              ) : null}
            </article>
          ))
        ) : (
          <div className="empty">
            {tab === "notes" ? (
              <NotebookPen size={38} />
            ) : (
              <Bookmark size={38} />
            )}
            <h3>
              {search
                ? "没有找到匹配内容"
                : tab === "notes"
                  ? "从记下一次理解开始"
                  : "还没有收藏题目"}
            </h3>
            <p>
              {tab === "notes"
                ? "在答题页或错题页记录笔记，保存后会出现在这里。"
                : "在题目下方点击“收藏题目”，便可集中回顾与重练。"}
            </p>
            <Link className="primary" to="/practice">
              去练习 <ArrowRight size={16} />
            </Link>
          </div>
        )}
      </section>
    </>
  );
}
