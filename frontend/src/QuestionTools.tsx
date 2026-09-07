import { useEffect, useId, useRef, useState } from "react";
import {
  Bookmark,
  Check,
  Flag,
  LoaderCircle,
  NotebookPen,
  Save,
  X,
} from "lucide-react";
import { api, send } from "./api";
import type {
  Personal,
  QuestionReport,
  ReportCategory,
} from "./personal-types";
import { reportLabels } from "./personal-types";
import "./personal.css";

type Draft = { note: string; version: number };
function readDraft(key: string): Draft | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return value &&
      typeof value.note === "string" &&
      Number.isInteger(value.version)
      ? value
      : null;
  } catch {
    return null;
  }
}

export default function QuestionTools({
  questionId,
  owner,
  initial,
  onChange,
  onReport,
}: {
  questionId: string;
  owner: string;
  initial?: Personal;
  onChange?: (value: Personal) => void;
  onReport?: (report: QuestionReport) => void;
}) {
  const key = `sc200.note.v1.${encodeURIComponent(owner)}.${questionId}`;
  const formId = useId();
  const [personal, setPersonal] = useState<Personal | null>(initial || null);
  const [note, setNote] = useState("");
  const [baseVersion, setBaseVersion] = useState(0);
  const [panel, setPanel] = useState<"note" | "report" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState<ReportCategory>("translation");
  const [content, setContent] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [retry, setRetry] = useState(0);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    let cancelled = false;
    (initial
      ? Promise.resolve(initial)
      : api<Personal>(`/questions/${questionId}/personal`)
    )
      .then((value) => {
        if (cancelled) return;
        const draft = readDraft(key);
        setPersonal(value);
        setNote(draft?.note ?? value.note);
        setBaseVersion(draft?.version ?? value.version);
        if (draft && draft.note !== value.note) {
          setMessage("已恢复这台设备上未保存的笔记草稿。");
          setPanel("note");
        }
        setLoaded(true);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
      active.current = false;
    };
  }, [questionId, key, retry]);

  const dirty = loaded && !!personal && note !== personal.note;
  function storeDraft(value: string, version = baseVersion) {
    setNote(value);
    try {
      if (value === personal?.note) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify({ note: value, version }));
    } catch {
      setError("浏览器无法保存草稿，请使用“保存笔记”同步到账号后再离开。");
    }
  }
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function update(patch: { favorite?: boolean; note?: string }) {
    if (!personal || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await send<Personal>(
        `/questions/${questionId}/personal`,
        {
          ...patch,
          version: patch.note !== undefined ? baseVersion : personal.version,
        },
        "PATCH",
      );
      if (!active.current) return;
      setPersonal(saved);
      // A favorite-only change cannot silently resolve an existing note version conflict.
      if (patch.note !== undefined || baseVersion === personal.version) {
        setBaseVersion(saved.version);
        if (patch.note === undefined && dirty) {
          try {
            localStorage.setItem(
              key,
              JSON.stringify({ note, version: saved.version }),
            );
          } catch {
            /* Explicit save remains available. */
          }
        }
      }
      if (patch.note !== undefined) {
        setNote(saved.note);
        try {
          localStorage.removeItem(key);
        } catch {
          /* Remote save succeeded. */
        }
      }
      onChange?.(saved);
      setMessage(
        patch.note !== undefined
          ? "笔记已保存到账号。"
          : saved.favorite
            ? "已加入收藏。"
            : "已取消收藏。",
      );
    } catch (e) {
      if (active.current) setError((e as Error).message);
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function reloadVersion() {
    setBusy(true);
    setError("");
    try {
      const latest = await api<Personal>(`/questions/${questionId}/personal`);
      if (!active.current) return;
      setPersonal(latest);
      setBaseVersion(latest.version);
      onChange?.(latest);
      try {
        localStorage.setItem(
          key,
          JSON.stringify({ note, version: latest.version }),
        );
      } catch {
        /* Keep draft in memory. */
      }
      setMessage(
        "已读取最新版本，你的草稿仍保留。再次保存将用此草稿替换账号中的笔记。",
      );
    } catch (e) {
      if (active.current) setError((e as Error).message);
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function report(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await send<QuestionReport>(
        `/questions/${questionId}/reports`,
        { category, content: content.trim() },
      );
      if (!active.current) return;
      setContent("");
      setPanel(null);
      onReport?.(result);
      setMessage("纠错反馈已保存，可在“收藏与笔记”的反馈记录中查看或撤回。");
    } catch (e) {
      if (active.current) setError((e as Error).message);
    } finally {
      if (active.current) setBusy(false);
    }
  }
  return (
    <section className="question-tools" aria-label="题目学习工具">
      <div className="personal-toolbar">
        <button
          type="button"
          className={"text-button " + (personal?.favorite ? "is-favorite" : "")}
          disabled={!loaded || busy}
          aria-pressed={personal?.favorite ?? false}
          onClick={() => update({ favorite: !personal?.favorite })}
        >
          <Bookmark
            size={16}
            fill={personal?.favorite ? "currentColor" : "none"}
          />
          {personal?.favorite ? "已收藏" : "收藏题目"}
        </button>
        <button
          type="button"
          className="text-button"
          disabled={!loaded}
          aria-expanded={panel === "note"}
          aria-controls={`${formId}-note-panel`}
          onClick={() => setPanel(panel === "note" ? null : "note")}
        >
          <NotebookPen size={16} />
          {dirty ? "笔记有草稿" : personal?.note ? "查看笔记" : "记笔记"}
        </button>
        <button
          type="button"
          className="text-button"
          aria-expanded={panel === "report"}
          aria-controls={`${formId}-report-panel`}
          onClick={() => setPanel(panel === "report" ? null : "report")}
        >
          <Flag size={15} />
          反馈题目问题
        </button>
      </div>
      {error ? (
        <div className="personal-error" role="alert">
          {error}
          {!loaded ? (
            <button
              className="text-button"
              onClick={() => {
                setError("");
                setRetry((value) => value + 1);
              }}
            >
              重新加载学习工具
            </button>
          ) : panel === "note" ? (
            <button
              className="text-button"
              disabled={busy}
              onClick={reloadVersion}
            >
              读取最新版本，保留草稿
            </button>
          ) : null}
        </div>
      ) : null}
      {message ? (
        <p className="personal-message" role="status">
          <Check size={14} />
          {message}
        </p>
      ) : null}
      {panel === "note" ? (
        <div id={`${formId}-note-panel`} className="personal-editor">
          <div className="personal-editor-heading">
            <label htmlFor={`${formId}-note`}>我的学习笔记</label>
            <small>仅自己可见</small>
          </div>
          <textarea
            id={`${formId}-note`}
            value={note}
            disabled={busy}
            maxLength={10000}
            rows={5}
            placeholder="记下解题思路、容易混淆的概念，或需要回顾的 KQL…"
            onChange={(e) => {
              storeDraft(e.target.value);
              setMessage("");
            }}
          />
          <div className="personal-editor-footer">
            <span>
              {note.length} / 10000 ·{" "}
              {dirty ? "草稿保存在当前设备，尚未同步" : "已与账号同步"}
            </span>
            <button
              type="button"
              className="primary compact"
              disabled={busy || !dirty}
              onClick={() => update({ note })}
            >
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Save size={15} />
              )}
              保存笔记
            </button>
          </div>
        </div>
      ) : null}
      {panel === "report" ? (
        <form
          id={`${formId}-report-panel`}
          className="personal-editor"
          onSubmit={report}
        >
          <div className="personal-editor-heading">
            <b>记录题目问题</b>
            <button
              type="button"
              className="icon-button"
              aria-label="关闭反馈表单"
              onClick={() => setPanel(null)}
            >
              <X size={16} />
            </button>
          </div>
          <p className="muted">
            反馈保存在当前平台，等待题库维护时核对，不会自动改写参考答案。
          </p>
          <label htmlFor={`${formId}-category`}>问题类型</label>
          <select
            id={`${formId}-category`}
            value={category}
            disabled={busy}
            onChange={(e) => setCategory(e.target.value as ReportCategory)}
          >
            {Object.entries(reportLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <label htmlFor={`${formId}-report`}>问题说明</label>
          <textarea
            id={`${formId}-report`}
            value={content}
            disabled={busy}
            minLength={5}
            maxLength={3000}
            required
            rows={4}
            placeholder="请说明具体问题；如有依据，可附上微软文档链接。"
            onChange={(e) => setContent(e.target.value)}
          />
          <div className="personal-editor-footer">
            <span>{content.trim().length} / 3000 · 至少 5 字</span>
            <button
              className="primary compact"
              disabled={busy || content.trim().length < 5}
            >
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Flag size={15} />
              )}
              保存反馈
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
