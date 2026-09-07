import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  LoaderCircle,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Target,
  TrendingUp,
} from "lucide-react";
import { api, send } from "./api";
import type { Question, Session } from "./types";
import type {
  KnowledgePoint,
  ReviewFilters,
  ReviewItem,
  ReviewSummary,
} from "./review-types";
import {
  defaultReviewFilters,
  filterReviews,
  isDue,
  reviewSelection,
} from "./review-utils";
import "./review.css";

const typeNames: Record<Question["type"], string> = {
  single: "单选题",
  multiple: "多选题",
  matching: "匹配题",
  hotspot: "热点题",
  ordering: "排序题",
};

function dateLabel(value: number | null) {
  return value === null
    ? "尚未复习"
    : new Date(value * 1000).toLocaleString("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function ReviewTrend({ point }: { point: KnowledgePoint }) {
  const points = point.trend;
  if (points.length < 2)
    return <span className="review-trend-empty">再学一周，观察变化</span>;
  const coordinates = points
    .map((p, i) =>
      [
        4 + (i / (points.length - 1)) * 108,
        34 - Math.max(0, Math.min(100, p.accuracy)) * 0.3,
      ].join(","),
    )
    .join(" ");
  return (
    <svg
      className="review-sparkline"
      viewBox="0 0 116 38"
      role="img"
      aria-label={points
        .map(
          (p) =>
            p.week + "：" + Math.round(p.accuracy) + "%，" + p.count + "次作答",
        )
        .join("；")}
    >
      <path d="M4 34H112" fill="none" stroke="currentColor" opacity="0.13" />
      <polyline
        points={coordinates}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {points.map((p, i) => (
        <circle
          key={p.week}
          cx={4 + (i / (points.length - 1)) * 108}
          cy={34 - Math.max(0, Math.min(100, p.accuracy)) * 0.3}
          r="2.5"
          fill="currentColor"
        >
          <title>
            {p.week}：{Math.round(p.accuracy)}%，{p.count} 次作答
          </title>
        </circle>
      ))}
    </svg>
  );
}

function ReviewImage({
  questionId,
  filename,
  alt,
}: {
  questionId: string;
  filename: string;
  alt: string;
}) {
  const src =
    "/api/v1/mistakes/" +
    encodeURIComponent(questionId) +
    "/assets/" +
    encodeURIComponent(filename);
  return (
    <a
      className="review-image-link"
      href={src}
      target="_blank"
      rel="noreferrer"
    >
      <img src={src} alt={alt} loading="lazy" />
      <span>打开原图 ↗</span>
    </a>
  );
}

function QuestionReference({ question }: { question: Question }) {
  return (
    <div className="review-reference">
      {question.case_en || question.case_zh || question.case_assets?.length ? (
        <details className="review-case">
          <summary>查看案例背景</summary>
          <p>{question.case_zh || question.case_en}</p>
          {question.case_assets?.map((name) => (
            <ReviewImage
              key={name}
              questionId={question.id}
              filename={name}
              alt="原文案例附图"
            />
          ))}
        </details>
      ) : null}
      <p className="review-full-stem">{question.zh || question.en}</p>
      {question.assets.map((name) => (
        <ReviewImage
          key={name}
          questionId={question.id}
          filename={name}
          alt="原文题目附图"
        />
      ))}
      {question.translation_status === "machine" ? (
        <p className="review-source-note">
          机器翻译初稿，术语与细节请结合英文原文核对。
        </p>
      ) : null}
      {question.zh && question.en ? (
        <details className="review-case">
          <summary>对照英文原文</summary>
          <p lang="en">{question.en}</p>
        </details>
      ) : null}
      {question.slots.length ? (
        <dl className="review-slot-list">
          {question.slots.map((slot, index) => {
            const answer = slot.options.find(
              (option) => option.id === question.answer?.[index],
            );
            return (
              <div key={slot.id}>
                <dt>{slot.zh || slot.en || "答题项 " + (index + 1)}</dt>
                <dd>{answer ? answer.zh || answer.en : "参考答案尚未整理"}</dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <ul className="review-option-list">
          {question.options.map((option) => (
            <li
              key={option.id}
              className={
                question.answer?.includes(option.id) ? "is-answer" : ""
              }
            >
              <b>{option.id}</b>
              <span>{option.zh || option.en}</span>
              {question.answer?.includes(option.id) ? (
                <CheckCircle2 size={16} aria-label="参考答案" />
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <div className="review-explanation">
        <b>参考解析</b>
        {question.answer_assets?.map((name) => (
          <ReviewImage
            key={name}
            questionId={question.id}
            filename={name}
            alt="原文答案附图"
          />
        ))}
        <p>
          {question.explanation_zh ||
            question.explanation_en ||
            "原文未提供解析。请结合参考答案与产品文档复盘。"}
        </p>
        {question.reference
          ?.filter((link) =>
            /^https:\/\/(learn|docs)\.microsoft\.com\//.test(link),
          )
          .map((link, index) => (
            <a key={link + index} href={link} target="_blank" rel="noreferrer">
              Microsoft 参考资料 {index + 1} ↗
            </a>
          ))}
      </div>
      <p className="review-source-note">
        来源：PDF 第 {question.pages.join("、")} 页。参考答案沿用题库整理结果。
      </p>
    </div>
  );
}

export default function ReviewHub({
  owner,
  renderQuestionTools,
}: {
  owner?: string;
  renderQuestionTools?: (question: Question, owner?: string) => ReactNode;
}) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [filters, setFilters] = useState<ReviewFilters>(defaultReviewFilters);
  const [limit, setLimit] = useState(20);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [allKnowledge, setAllKnowledge] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      api<ReviewItem[]>("/mistakes", { signal: controller.signal }),
      api<ReviewSummary>("/review/summary", { signal: controller.signal }),
    ])
      .then(([items, review]) => {
        if (controller.signal.aborted) return;
        setRows(items);
        setSummary(review);
        setNow(Date.now() / 1000);
      })
      .catch((cause: Error) => {
        if (!controller.signal.aborted) setError(cause.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision, owner]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const visible = useMemo(
    () => filterReviews(rows, filters, now),
    [rows, filters, now],
  );
  const selectedIds = reviewSelection(visible, limit);
  const pageCount = Math.max(1, Math.ceil(visible.length / 10));
  const currentPage = Math.min(page, pageCount);
  const pageRows = visible.slice((currentPage - 1) * 10, currentPage * 10);
  const topics = [...new Set(rows.map((row) => row.question.topic))].sort(
    (a, b) => a - b,
  );
  const tags = [...new Set(rows.flatMap((row) => row.question.tags))].sort();
  const dueCount = rows.filter((row) => isDue(row, now)).length;
  const pendingCount = rows.filter((row) => !row.mastered).length;
  const statusCounts = {
    pending: pendingCount,
    due: dueCount,
    mastered: rows.length - pendingCount,
    all: rows.length,
  };
  const readyCount = visible.filter(
    (row) => row.question.status === "ready",
  ).length;
  const knowledge = allKnowledge
    ? summary?.knowledge
    : summary?.knowledge.slice(0, 6);
  const disabled = loading || busy;
  const hasExtraFilters =
    filters.days !== "all" ||
    filters.topic !== "all" ||
    filters.tag !== "all" ||
    filters.minimum !== 1 ||
    filters.search !== "";

  function updateFilter<K extends keyof ReviewFilters>(
    key: K,
    value: ReviewFilters[K],
  ) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  function changeFilters(value: ReviewFilters) {
    setFilters(value);
    setPage(1);
  }

  async function train(ids = selectedIds) {
    if (!ids.length || disabled) return;
    setBusy(true);
    setError("");
    try {
      const session = await send<Session>("/sessions", {
        mode: "wrong",
        count: ids.length,
        feedback: true,
        question_ids: ids,
      });
      navigate("/session/" + session.id);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function trainTopic(topic: number, count: number) {
    if (!count || disabled) return;
    setBusy(true);
    setError("");
    try {
      const session = await send<Session>("/sessions", {
        mode: "topic",
        topic,
        count: Math.min(10, count),
        feedback: true,
      });
      navigate("/session/" + session.id);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleMastery(row: ReviewItem) {
    if (disabled) return;
    setBusy(true);
    setError("");
    try {
      await send("/mistakes/" + row.id, { mastered: !row.mastered }, "PATCH");
      setRevision((value) => value + 1);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-hub">
      <div className="page-heading">
        <div>
          <div className="eyebrow">A LITTLE REVIEW, A LASTING MEMORY</div>
          <h1>把错题，变成真正掌握</h1>
          <p>按记忆节奏重温，也给反复出错的知识点多一点时间。</p>
        </div>
        <Link to="/practice" className="outline">
          <BookOpen size={16} />
          去学习中心
        </Link>
      </div>

      {error ? (
        <div className="error" role="alert">
          <span>{error}</span>
          <button
            className="text-button"
            disabled={disabled}
            onClick={() => setRevision((value) => value + 1)}
          >
            重新加载
          </button>
        </div>
      ) : null}
      {loading && !summary ? (
        <div className="loading" role="status">
          <LoaderCircle className="spin" size={20} />
          正在整理复习计划…
        </div>
      ) : null}
      {!loading && !summary ? (
        <div className="panel review-empty">
          <BookOpen size={30} />
          <h2>暂时无法读取复习记录</h2>
          <p>请重新加载，已保存的学习记录不会受到影响。</p>
        </div>
      ) : null}

      {summary ? (
        <>
          <section className="review-overview" aria-label="间隔复习概览">
            <div className="review-today">
              <div className="eyebrow light">YOUR NEXT SMALL STEP</div>
              <h2>
                <span>{dueCount}</span> 道题，到了复习时间
              </h2>
              <p>
                {dueCount
                  ? "现在回想一次，让下次解题更有把握。"
                  : pendingCount
                    ? "已安排的复习还未到期，也可以提前巩固。"
                    : "新的错题会自动加入计划，从下一次练习开始积累。"}
              </p>
              <button
                className="review-light-button"
                onClick={() =>
                  changeFilters({
                    ...defaultReviewFilters,
                    state: "due",
                    sort: "due",
                  })
                }
              >
                查看今日到期 <ArrowRight size={16} />
              </button>
            </div>
            <div className="review-stat">
              <Clock3 size={21} />
              <strong>{pendingCount - dueCount}</strong>
              <span>等待下次复习</span>
            </div>
            <div className="review-stat">
              <CheckCircle2 size={21} />
              <strong>{statusCounts.mastered}</strong>
              <span>已标记掌握</span>
            </div>
          </section>

          <section
            className="panel review-library"
            aria-label="错题筛选与重练"
            aria-busy={loading}
          >
            <div className="review-library-heading">
              <div>
                <h2>我的错题</h2>
                <p>答对后延后复习，答错后重新巩固。手动标记掌握后暂停提醒。</p>
              </div>
              <SlidersHorizontal size={19} aria-hidden="true" />
            </div>
            <div className="review-tabs" aria-label="掌握状态">
              {(
                [
                  ["pending", "待掌握"],
                  ["due", "今日到期"],
                  ["mastered", "已掌握"],
                  ["all", "全部"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={filters.state === value}
                  className={filters.state === value ? "selected" : ""}
                  onClick={() => updateFilter("state", value)}
                >
                  {label}
                  <span>{statusCounts[value]}</span>
                </button>
              ))}
            </div>
            <div className="review-filter-grid">
              <label className="review-search">
                <span className="review-sr-only">搜索题目</span>
                <Search size={17} aria-hidden="true" />
                <input
                  value={filters.search}
                  onChange={(event) =>
                    updateFilter("search", event.target.value)
                  }
                  placeholder="搜索题干、题号或知识点"
                />
              </label>
              <label>
                错误时间
                <select
                  value={filters.days}
                  onChange={(event) =>
                    updateFilter(
                      "days",
                      event.target.value as ReviewFilters["days"],
                    )
                  }
                >
                  <option value="all">全部时间</option>
                  <option value="7">最近 7 天</option>
                  <option value="30">最近 30 天</option>
                </select>
              </label>
              <label>
                章节
                <select
                  value={filters.topic}
                  onChange={(event) =>
                    updateFilter("topic", event.target.value)
                  }
                >
                  <option value="all">全部章节</option>
                  {topics.map((topic) => (
                    <option value={String(topic)} key={topic}>
                      Topic {topic}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                知识点
                <select
                  value={filters.tag}
                  onChange={(event) => updateFilter("tag", event.target.value)}
                >
                  <option value="all">全部知识点</option>
                  {tags.map((tag) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                错误次数
                <select
                  value={filters.minimum}
                  onChange={(event) =>
                    updateFilter("minimum", Number(event.target.value))
                  }
                >
                  <option value={1}>至少 1 次</option>
                  <option value={2}>至少 2 次</option>
                  <option value={3}>至少 3 次</option>
                </select>
              </label>
            </div>
            <div className="review-result-bar">
              <div className="review-result-count" aria-live="polite">
                筛选出 <b>{visible.length}</b> 道题
                {hasExtraFilters ? (
                  <button
                    className="text-button"
                    onClick={() =>
                      changeFilters({
                        ...defaultReviewFilters,
                        state: filters.state,
                        sort: filters.sort,
                      })
                    }
                  >
                    清除筛选
                  </button>
                ) : null}
              </div>
              <label className="review-sort">
                排序
                <select
                  value={filters.sort}
                  onChange={(event) =>
                    updateFilter(
                      "sort",
                      event.target.value as ReviewFilters["sort"],
                    )
                  }
                >
                  <option value="recent">最近答错</option>
                  <option value="count">错误最多</option>
                  <option value="due">复习时间最早</option>
                </select>
              </label>
            </div>
            <div className="review-start-bar">
              <div>
                <b>按当前筛选重练</b>
                <p>
                  {readyCount < visible.length
                    ? `${visible.length - readyCount} 道待核对题暂不参与重练。`
                    : "按当前排序取题，保留你选择的复习重点。"}
                </p>
              </div>
              <div className="review-start-controls">
                <label>
                  <span className="review-sr-only">重练题目数量</span>
                  <select
                    value={limit}
                    onChange={(event) => setLimit(Number(event.target.value))}
                  >
                    <option value={10}>最多 10 题</option>
                    <option value={20}>最多 20 题</option>
                    <option value={50}>最多 50 题</option>
                  </select>
                </label>
                <button
                  className="primary"
                  disabled={disabled || !selectedIds.length}
                  onClick={() => train()}
                >
                  {busy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <RotateCcw size={16} />
                  )}
                  重练 {selectedIds.length} 题
                </button>
              </div>
            </div>
            {visible.length ? (
              <div className="review-rows">
                {pageRows.map((row) => (
                  <article className="review-row" key={row.id}>
                    <div className="review-row-meta">
                      <span>
                        Topic {row.question.topic} · 第 {row.question.number} 题
                      </span>
                      <span>{typeNames[row.question.type]}</span>
                      <span className="review-error-count">
                        答错 {row.count} 次
                      </span>
                    </div>
                    <button
                      className="review-question-toggle"
                      aria-expanded={expanded === row.id}
                      aria-controls={"review-detail-" + row.id}
                      onClick={() =>
                        setExpanded(expanded === row.id ? null : row.id)
                      }
                    >
                      <span>{row.question.zh || row.question.en}</span>
                      <ChevronDown
                        size={19}
                        className={expanded === row.id ? "is-open" : ""}
                      />
                    </button>
                    <div className="review-row-tags">
                      {row.question.tags.map((tag) => (
                        <button
                          key={tag}
                          title={"筛选知识点：" + tag}
                          onClick={() => updateFilter("tag", tag)}
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                    <div className="review-row-footer">
                      <div className="review-schedule">
                        <span
                          className={
                            row.mastered
                              ? "is-mastered"
                              : isDue(row, now)
                                ? "is-due"
                                : ""
                          }
                        >
                          {row.mastered ? (
                            <Check size={13} />
                          ) : (
                            <Clock3 size={13} />
                          )}
                          {row.mastered
                            ? "已掌握 · 已暂停提醒"
                            : isDue(row, now)
                              ? "已到复习时间"
                              : "下次 " + dateLabel(row.due_at)}
                        </span>
                        <small>
                          {row.review_stage > 0
                            ? "第 " + row.review_stage + " 轮巩固"
                            : "待巩固"}{" "}
                          · 最近答错 {dateLabel(row.updated)}
                        </small>
                      </div>
                      <button
                        className="text-button"
                        disabled={disabled}
                        onClick={() => toggleMastery(row)}
                      >
                        {row.mastered ? "恢复复习" : "标记已掌握"}
                      </button>
                    </div>
                    {expanded === row.id ? (
                      <div
                        className="review-expanded"
                        id={"review-detail-" + row.id}
                      >
                        <div className="review-detail-top">
                          <span>参考答案与复盘</span>
                          <button
                            className="outline compact"
                            disabled={
                              disabled || row.question.status !== "ready"
                            }
                            onClick={() => train([row.id])}
                          >
                            <RotateCcw size={13} />
                            重练此题
                          </button>
                        </div>
                        <QuestionReference question={row.question} />
                        <p className="review-last-seen">
                          上次复习：{dateLabel(row.last_reviewed)}
                          {row.due_at !== null && !row.mastered
                            ? " · 安排时间：" + dateLabel(row.due_at)
                            : ""}
                        </p>
                        {renderQuestionTools?.(row.question, owner)}
                      </div>
                    ) : null}
                  </article>
                ))}
                {pageCount > 1 ? (
                  <nav className="review-pagination" aria-label="错题分页">
                    <span>
                      第 {currentPage} / {pageCount} 页 · 共 {visible.length} 道
                    </span>
                    <div>
                      <button
                        className="outline compact"
                        disabled={currentPage === 1}
                        onClick={() => setPage(currentPage - 1)}
                      >
                        上一页
                      </button>
                      <button
                        className="outline compact"
                        disabled={currentPage === pageCount}
                        onClick={() => setPage(currentPage + 1)}
                      >
                        下一页
                      </button>
                    </div>
                  </nav>
                ) : null}
              </div>
            ) : (
              <div className="review-empty">
                <CheckCircle2 size={32} />
                <h3>
                  {rows.length
                    ? "这个筛选下，暂时没有错题"
                    : "错题本还空着，先开始一次练习"}
                </h3>
                <p>
                  {rows.length
                    ? "可以调整章节、知识点或掌握状态，继续寻找要巩固的题目。"
                    : "答错的题会自动收录，后续复习时间也会一并安排。"}
                </p>
                {rows.length ? (
                  <button
                    className="outline compact"
                    onClick={() =>
                      changeFilters({ ...defaultReviewFilters, state: "all" })
                    }
                  >
                    查看全部错题
                  </button>
                ) : (
                  <Link className="outline compact" to="/practice">
                    开始练习 <ArrowRight size={14} />
                  </Link>
                )}
              </div>
            )}
          </section>

          <div className="review-insight-grid">
            <section className="panel review-recommendations">
              <div className="review-section-title">
                <Target size={20} />
                <div>
                  <h2>给薄弱章节，一次专项练习</h2>
                  <p>依据近 30 天、至少 3 次作答的章节表现。</p>
                </div>
              </div>
              {summary.recommendations.length ? (
                <div className="review-recommendation-list">
                  {summary.recommendations.map((item) => (
                    <div className="review-recommendation" key={item.topic}>
                      <div>
                        <strong>Topic {item.topic}</strong>
                        <span>
                          {item.attempts} 次作答 · 正确率{" "}
                          {Math.round(item.accuracy)}%
                        </span>
                      </div>
                      <button
                        className="text-button"
                        disabled={disabled || !item.ready_count}
                        onClick={() => trainTopic(item.topic, item.ready_count)}
                      >
                        练 {Math.min(10, item.ready_count)} 题{" "}
                        <ArrowRight size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="review-small-empty">
                  <p>再积累一些学习记录</p>
                  <span>完成更多章节练习后，这里会推荐需要巩固的章节。</span>
                </div>
              )}
            </section>
            <section className="panel review-knowledge">
              <div className="review-section-title">
                <TrendingUp size={20} />
                <div>
                  <h2>知识点掌握趋势</h2>
                  <p>
                    真实作答正确率；折线展示有学习记录的各周。变化值较上次记录周。
                  </p>
                </div>
              </div>
              {knowledge?.length ? (
                <>
                  <div className="review-knowledge-list">
                    {knowledge.map((point) => {
                      const currentWeek = point.trend.at(-1);
                      const delta =
                        currentWeek && point.previous_accuracy !== null
                          ? currentWeek.accuracy - point.previous_accuracy
                          : null;
                      return (
                        <div className="review-knowledge-row" key={point.tag}>
                          <div>
                            <strong>{point.tag}</strong>
                            <span>
                              {point.count} 次作答 · {point.correct} 次正确
                            </span>
                          </div>
                          <ReviewTrend point={point} />
                          <div className="review-knowledge-score">
                            <b>
                              {Math.round(point.accuracy)}
                              <small>%</small>
                            </b>
                            <span
                              className={
                                delta !== null && delta > 0
                                  ? "improved"
                                  : delta !== null && delta < 0
                                    ? "declined"
                                    : ""
                              }
                            >
                              {delta === null
                                ? "暂无周对比"
                                : `${delta > 0 ? "+" : ""}${Math.round(delta)} 个百分点`}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {summary.knowledge.length > 6 ? (
                    <button
                      className="text-button"
                      onClick={() => setAllKnowledge((value) => !value)}
                    >
                      {allKnowledge
                        ? "收起知识点"
                        : "查看全部 " + summary.knowledge.length + " 个知识点"}
                      <ChevronDown size={14} />
                    </button>
                  ) : null}
                </>
              ) : (
                <div className="review-small-empty">
                  <p>还没有知识点数据</p>
                  <span>练习后会显示各知识点的准确率和周变化。</span>
                </div>
              )}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
