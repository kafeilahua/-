import React, {
  useState,
  useEffect,
  useRef,
  lazy,
  Suspense,
  createContext,
  useContext,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  useNavigate,
  useParams,
  Link,
  useLocation,
} from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  LayoutDashboard,
  BookOpen,
  Target,
  Timer,
  Shuffle,
  BookmarkCheck,
  ChartNoAxesCombined,
  Settings2,
  ShieldCheck,
  ChevronRight,
  ChevronLeft,
  Check,
  Flag,
  LogOut,
  Download,
  Upload,
  Search,
  CheckCircle2,
  XCircle,
  Clock3,
  Layers3,
  PanelLeftClose,
  RotateCcw,
  LoaderCircle,
  Languages,
  TriangleAlert,
  Pause,
  Play,
  Flame,
  CalendarDays,
  GraduationCap,
} from "lucide-react";
import { api, send, setCsrf } from "./api";
import type { User, Bank, Stats, History, Session, Question } from "./types";
import "./style.css";
const Chart = lazy(() => import("./Chart"));
const AuthContext = createContext<{ user: User; logout: () => void }>(null!);
const modes: Record<string, string> = {
  exam: "模拟考试",
  random: "随机练习",
  topic: "专项训练",
  wrong: "错题重练",
};
const typeNames: Record<string, string> = {
  single: "单选题",
  multiple: "多选题",
  matching: "匹配题",
  hotspot: "热点题",
  ordering: "排序题",
};
const topicNames: Record<number, string> = {
  1: "Microsoft Defender",
  2: "Defender for Cloud",
  3: "Microsoft Sentinel",
  4: "综合能力 · 模块一",
  5: "综合能力 · 模块二",
  6: "综合能力 · 模块三",
  7: "综合能力 · 模块四",
  8: "案例研究 · 一",
  9: "案例研究 · 二",
  10: "案例研究 · 三",
  11: "案例研究 · 四",
  12: "案例研究 · 五",
  13: "案例研究 · 六",
};
const date = (n: number) =>
  new Date(n * 1000).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
  });
const duration = (s: number) =>
  s >= 3600 ? `${(s / 3600).toFixed(1)} 小时` : `${Math.floor(s / 60)} 分钟`;
function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" /> 正在加载学习空间…
    </div>
  );
}
function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div className="error" role="alert">
      <TriangleAlert size={17} />
      {message}
    </div>
  ) : null;
}
function Ring({ value, size = 64 }: { value: number; size?: number }) {
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="33" className="ring-track" />
        <circle
          cx="40"
          cy="40"
          r="33"
          className="ring-fill"
          strokeDasharray={`${value * 2.074} 207.4`}
        />
      </svg>
      <span>
        {Math.round(value)}
        <small>%</small>
      </span>
    </div>
  );
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    api<User>("/auth/me")
      .then((u) => {
        setUser(u);
        setCsrf(u.csrf);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  if (loading) return <Loading />;
  if (!user)
    return (
      <Auth
        onLogin={(u) => {
          setCsrf(u.csrf);
          setUser(u);
        }}
      />
    );
  return (
    <AuthContext.Provider
      value={{
        user,
        logout: () => {
          send("/auth/logout").then(() => {
            setUser(null);
            setCsrf("");
          });
        },
      }}
    >
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthContext.Provider>
  );
}
function Auth({ onLogin }: { onLogin: (u: User) => void }) {
  const [register, setRegister] = useState(false),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(
        await send<User>("/auth/" + (register ? "register" : "login"), {
          username,
          password,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth">
      <section className="auth-art">
        <div className="wordmark">
          <span className="brand-icon">
            <Layers3 size={26} />
          </span>
          知序 <small>SC-200 LAB</small>
        </div>
        <div className="auth-copy">
          <div className="eyebrow light">LEARN WITH INTENTION</div>
          <h1>
            每一次练习，
            <br />
            都离从容更近。
          </h1>
          <p>
            把零散的安全知识，变成有条理的能力。
            <br />
            你的 SC-200 学习，从这里开始。
          </p>
          <div className="orbit">
            <div className="orbit-ring one" />
            <div className="orbit-ring two" />
            <div className="orbit-ring three" />
            <ShieldCheck size={92} strokeWidth={1} />
            <span className="orbit-label label-one">Microsoft Sentinel</span>
            <span className="orbit-label label-two">Threat hunting</span>
            <span className="orbit-label label-three">Microsoft Defender</span>
          </div>
        </div>
        <small className="auth-footer">专注学习 · 记录成长 · 循序进阶</small>
      </section>
      <section className="auth-form">
        <div className="eyebrow">YOUR LEARNING SPACE</div>
        <h2>{register ? "创建你的学习空间" : "欢迎回到知序"}</h2>
        <p className="muted">
          {register
            ? "建立个人档案，让每一次努力都有迹可循。"
            : "继续上次的进度，让今天的学习更进一步。"}
        </p>
        <div className="segmented">
          <button
            className={!register ? "selected" : ""}
            onClick={() => setRegister(false)}
          >
            登录
          </button>
          <button
            className={register ? "selected" : ""}
            onClick={() => setRegister(true)}
          >
            注册账号
          </button>
        </div>
        <form onSubmit={submit}>
          <label>
            用户名
            <input
              autoComplete="username"
              placeholder="输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={2}
              maxLength={40}
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="至少 8 位字符"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </label>
          <ErrorBox message={error} />
          <button className="primary full" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <ArrowRight size={18} />
            )}{" "}
            {register ? "创建账号，开始学习" : "进入学习空间"}
          </button>
        </form>
        <p className="auth-note">
          <ShieldCheck size={15} />
          学习记录保存在你的 Python 服务中
        </p>
      </section>
    </div>
  );
}
function Shell() {
  const { user, logout } = useContext(AuthContext);
  const location = useLocation();
  const inSession = location.pathname.startsWith("/session/");
  const items = [
    ["/", "学习概览", LayoutDashboard],
    ["/practice", "开始练习", BookOpen],
    ["/mistakes", "我的错题", BookmarkCheck],
    ["/history", "学习记录", ChartNoAxesCombined],
  ] as const;
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to="/" className="wordmark">
          <span className="brand-icon">
            <Layers3 size={23} />
          </span>
          <span>
            知序<small>SC-200 LAB</small>
          </span>
        </Link>
        <div className="workspace-label">个人学习空间</div>
        <nav>
          {items.map(([path, label, Icon]) => (
            <NavLink
              to={path}
              key={path}
              end
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
            >
              <Icon size={20} />
              {label}
              {path === "/" ? <span className="nav-dot" /> : null}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-guide">
          <div className="mini-shield">
            <ShieldCheck size={21} />
          </div>
          <b>循序渐进，稳步掌握</b>
          <p>
            练习、复盘、再练习。
            <br />
            让知识真正属于你。
          </p>
          <Link to="/practice">
            开始今日练习 <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className="sidebar-bottom">
          <NavLink to="/settings" className="nav-link">
            <Settings2 size={19} />
            数据与题库
          </NavLink>
          <div className="profile">
            <span className="avatar">
              {user.username.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <b>{user.username}</b>
              <small>SC-200 学习者</small>
            </div>
            <button className="icon-button" title="退出登录" onClick={logout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb">
            学习空间 <ChevronRight size={13} />{" "}
            <b>
              {inSession
                ? "专注答题"
                : location.pathname === "/practice"
                  ? "开始练习"
                  : location.pathname === "/mistakes"
                    ? "我的错题"
                    : location.pathname === "/history"
                      ? "学习记录"
                      : location.pathname === "/settings"
                        ? "数据与题库"
                        : "学习概览"}
            </b>
          </span>
          <div className="topbar-right">
            <span className="status-dot" />
            个人版 <span className="divider" />
            <CalendarDays size={15} />
            <span>
              {new Date().toLocaleDateString("zh-CN", {
                month: "long",
                day: "numeric",
                weekday: "short",
              })}
            </span>
          </div>
        </header>
        <main className={inSession ? "content session-content" : "content"}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/practice" element={<Practice />} />
            <Route path="/session/:id" element={<Study />} />
            <Route path="/mistakes" element={<Mistakes />} />
            <Route path="/history" element={<Records />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </main>
        <footer className="page-footer">
          知序 SC-200 LAB <span>每一次积累，都算数。</span>
        </footer>
      </div>
      <nav className="mobile-nav">
        {items.map(([p, l, Icon]) => (
          <NavLink to={p} key={p} end>
            <Icon size={19} />
            <span>{l}</span>
          </NavLink>
        ))}
        <NavLink to="/settings">
          <Settings2 size={19} />
          <span>设置</span>
        </NavLink>
      </nav>
    </div>
  );
}
function Heatmap({ stats }: { stats: Stats }) {
  const days = Array.from({ length: 140 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 133 + i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  return (
    <div className="heatmap-wrap">
      <div className="heatmap-labels">
        <span>一</span>
        <span>三</span>
        <span>五</span>
        <span>日</span>
      </div>
      <div
        className="heatmap"
        role="img"
        aria-label="最近 140 天每日学习热力图"
      >
        {days.map((day) => {
          const x = stats.daily[day];
          const n = x?.count || 0;
          return (
            <div
              key={day}
              className={
                "heat-cell level-" +
                (n === 0 ? 0 : n < 10 ? 1 : n < 20 ? 2 : n < 40 ? 3 : 4)
              }
              title={`${day} · ${n} 题 · ${duration(x?.seconds || 0)}`}
            />
          );
        })}
      </div>
    </div>
  );
}
function Dashboard() {
  const { user } = useContext(AuthContext),
    [data, setData] = useState<{
      stats: Stats;
      bank: Bank;
      history: History[];
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<Stats>("/stats"),
      api<Bank>("/bank"),
      api<History[]>("/sessions"),
    ])
      .then(([stats, bank, history]) => setData({ stats, bank, history }))
      .catch((e) => setError(e.message));
  }, []);
  if (!data) return error ? <ErrorBox message={error} /> : <Loading />;
  const { stats, bank, history } = data;
  const active = history.find((x) => !x.finished);
  const completed = history.filter((x) => x.finished).slice(0, 4);
  const studiedDays = Object.values(stats.daily).filter(
    (x) => x.count > 0,
  ).length;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">A LITTLE PROGRESS, EVERY DAY</div>
          <h1>
            {user.username}，今天也向前一步
            <span className="greeting-dot">。</span>
          </h1>
          <p>从一次练习开始，把知识积累成你的底气。</p>
        </div>
        <Link className="outline" to="/history">
          <CalendarDays size={16} />
          学习记录
        </Link>
      </div>
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-badge">
            <span /> MICROSOFT CERTIFIED · SC-200
          </span>
          <h2>
            让每一次练习，
            <br />
            都有明确的方向。
          </h2>
          <p>
            模拟真实节奏，找到知识盲点。
            <br />
            建立属于你的安全运营知识体系。
          </p>
          <Link
            className="hero-button"
            to={active ? "/session/" + active.id : "/practice"}
          >
            {active ? "继续上次训练" : "开始今日练习"}
            <ArrowRight size={17} />
          </Link>
          <span className="hero-meta">
            {bank.ready} 道可练题目<span>·</span>13 个原文模块<span>·</span>3
            种学习模式
          </span>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="visual-grid" />
          <div className="visual-orbit" />
          <div className="shield-card">
            <ShieldCheck size={74} strokeWidth={1.3} />
            <span>SECURITY OPERATIONS</span>
            <b>SC–200</b>
          </div>
          <div className="floating-tag tag-a">
            <Target size={18} />
            <span>专注掌握</span>
            <span className="tag-line" />
          </div>
          <div className="floating-tag tag-b">
            <CheckCircle2 size={19} />
            <span>积累，从今天开始</span>
          </div>
          <span className="visual-cross">+</span>
        </div>
      </section>
      <div className="metric-grid">
        <article className="metric">
          <span className="metric-icon mint">
            <Target size={20} />
          </span>
          <div>
            <p>累计正确率</p>
            <strong>
              {stats.accuracy}
              <small>%</small>
            </strong>
            <span className="metric-caption">
              答对 {stats.correct} / {stats.total} 题
            </span>
          </div>
          <Ring value={stats.accuracy} size={52} />
        </article>
        <article className="metric">
          <span className="metric-icon blue">
            <BookOpen size={20} />
          </span>
          <div>
            <p>累计练习</p>
            <strong>
              {stats.total}
              <small>题</small>
            </strong>
            <span className="metric-caption">每道题，都是一次积累</span>
          </div>
        </article>
        <article className="metric">
          <span className="metric-icon amber">
            <ChartNoAxesCombined size={20} />
          </span>
          <div>
            <p>模拟考平均分</p>
            <strong>
              {stats.exam_average}
              <small>%</small>
            </strong>
            <span className="metric-caption">
              已完成 {stats.exam_count} 次模拟考试
            </span>
          </div>
        </article>
        <article className="metric">
          <span className="metric-icon rose">
            <Clock3 size={20} />
          </span>
          <div>
            <p>累计学习时长</p>
            <strong>
              {Math.floor(stats.seconds / 60)}
              <small>分钟</small>
            </strong>
            <span className="metric-caption">已学习 {studiedDays} 天</span>
          </div>
        </article>
      </div>
      <div className="section-title">
        <h2>找到适合你的学习节奏</h2>
        <Link to="/practice">
          全部练习 <ArrowRight size={15} />
        </Link>
      </div>
      <div className="mode-grid">
        <ModeCard
          mode="exam"
          icon={<Timer />}
          title="全真模拟考试"
          text="按照考试节奏，检验你的知识掌握。"
          meta="50 题 · 100 分钟"
          color="mint"
        />
        <ModeCard
          mode="random"
          icon={<Shuffle />}
          title="随机抽题练习"
          text="自由选择题量，把碎片时间变成进步。"
          meta="自定义题量 · 不限时"
          color="blue"
        />
        <ModeCard
          mode="topic"
          icon={<Layers3 />}
          title="章节专项训练"
          text="聚焦一个知识模块，让薄弱项更扎实。"
          meta="13 个模块 · 针对性强化"
          color="amber"
        />
      </div>
      <div className="dashboard-bottom">
        <section className="panel trend-panel">
          <div className="panel-heading">
            <div>
              <h2>看见你的进步</h2>
              <p>每次模拟考试的成绩变化</p>
            </div>
            <span className="subtle-tag">模拟成绩</span>
          </div>
          {stats.trend.length ? (
            <Suspense fallback={<Loading />}>
              <Chart data={stats.trend} />
            </Suspense>
          ) : (
            <div className="empty-chart">
              <div className="chart-grid" />
              <ChartNoAxesCombined size={34} />
              <b>你的成长曲线，等待第一笔</b>
              <span>完成一次模拟考试后，成绩会显示在这里。</span>
              <Link to="/practice?mode=exam">
                开始首次模拟 <ArrowRight size={14} />
              </Link>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>把学习变成习惯</h2>
              <p>最近 140 天的学习足迹</p>
            </div>
            <Flame size={21} className="orange" />
          </div>
          <Heatmap stats={stats} />
          <div className="heatmap-footer">
            <span>
              累计学习 <b>{studiedDays}</b> 天
            </span>
            <span className="heat-legend">
              少{" "}
              {[0, 1, 2, 3, 4].map((n) => (
                <i key={n} className={"heat-cell level-" + n} />
              ))}{" "}
              多
            </span>
          </div>
          <div className="wrong-callout">
            <div className="metric-icon amber">
              <BookmarkCheck size={22} />
            </div>
            <div>
              <b>
                {stats.wrong
                  ? `${stats.wrong} 道错题，等你重新掌握`
                  : "及时复盘，让掌握更牢固"}
              </b>
              <p>把每一次出错，变成下次的把握。</p>
            </div>
            <Link to="/mistakes" aria-label="前往错题本">
              <ArrowUpRight size={21} />
            </Link>
          </div>
        </section>
      </div>
      <section className="panel recent-panel">
        <div className="panel-heading">
          <h2>最近练习</h2>
          <Link to="/history">
            查看全部 <ArrowRight size={14} />
          </Link>
        </div>
        {completed.length ? (
          <HistoryTable rows={completed} />
        ) : (
          <div className="inline-empty">
            <BookOpen size={21} />
            还没有已完成的练习。今天，开始你的第一道题。
          </div>
        )}
      </section>
      <p className="source-note">
        题库来源：用户提供的 PDF · 已收录 {bank.total} 题，其中 {bank.review}{" "}
        题待核对 · <Link to="/settings">查看题库状态</Link>
      </p>
    </>
  );
}
function ModeCard({
  mode,
  icon,
  title,
  text,
  meta,
  color,
}: {
  mode: string;
  icon: React.ReactNode;
  title: string;
  text: string;
  meta: string;
  color: string;
}) {
  return (
    <Link className="mode-card" to={"/practice?mode=" + mode}>
      <div className={"mode-icon " + color}>{icon}</div>
      <ArrowUpRight size={19} className="mode-arrow" />
      <h3>{title}</h3>
      <p>{text}</p>
      <span>{meta}</span>
    </Link>
  );
}
function Practice() {
  const nav = useNavigate(),
    location = useLocation(),
    [bank, setBank] = useState<Bank | null>(null),
    [mode, setMode] = useState(
      new URLSearchParams(location.search).get("mode") || "random",
    ),
    [count, setCount] = useState(10),
    [topic, setTopic] = useState(""),
    [tag, setTag] = useState(""),
    [feedback, setFeedback] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Bank>("/bank")
      .then(setBank)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (mode === "exam") {
      setCount(50);
      setTopic("");
      setTag("");
    } else setCount(10);
  }, [mode]);
  async function start() {
    setBusy(true);
    setError("");
    try {
      const s = await send<Session>("/sessions", {
        mode,
        count,
        topic: topic ? Number(topic) : null,
        tag: tag || null,
        feedback,
      });
      nav("/session/" + s.id);
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
          <div className="eyebrow">MAKE ROOM FOR PROGRESS</div>
          <h1>选择今天的学习方式</h1>
          <p>无论十分钟还是一场模拟，都能让你更进一步。</p>
        </div>
      </div>
      <div className="practice-layout">
        <section className="panel setup-panel">
          <div className="section-kicker">
            01 <span>选择练习模式</span>
          </div>
          <div className="mode-select">
            {[
              ["exam", "模拟考试", Timer],
              ["random", "随机练习", Shuffle],
              ["topic", "专项训练", Layers3],
            ].map(([id, label, Icon]) => {
              const I = Icon as typeof Timer;
              return (
                <button
                  key={id as string}
                  className={mode === id ? "selected" : ""}
                  onClick={() => setMode(id as string)}
                >
                  <I size={23} />
                  <b>{label as string}</b>
                  {mode === id ? <CheckCircle2 size={16} /> : null}
                </button>
              );
            })}
          </div>
          <div className="section-kicker">
            02 <span>设置你的练习</span>
          </div>
          {mode === "topic" ? (
            <div className="field-row">
              <label>
                知识模块
                <select
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                >
                  <option value="">全部模块</option>
                  {bank?.topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      Topic {t.id} · {topicNames[t.id]}（{t.ready} 题）
                    </option>
                  ))}
                </select>
              </label>
              <label>
                知识标签
                <select value={tag} onChange={(e) => setTag(e.target.value)}>
                  <option value="">全部标签</option>
                  {bank?.tags.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}
          <label>本次题量</label>
          <div className="count-select">
            {(mode === "exam" ? [40, 50, 60] : [10, 20, 50]).map((n) => (
              <button
                key={n}
                className={count === n ? "selected" : ""}
                onClick={() => setCount(n)}
              >
                {n}
                <small>题</small>
              </button>
            ))}
            {mode !== "exam" ? (
              <label className="custom-count">
                <input
                  aria-label="自定义题量"
                  type="number"
                  min={1}
                  max={100}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
                <span>自定义</span>
              </label>
            ) : null}
          </div>
          <div className="setting-row">
            <div>
              <b>
                <Clock3 size={17} />
                练习时间
              </b>
              <p>
                {mode === "exam"
                  ? "100 分钟 · 到时自动交卷，离开页面仍继续计时"
                  : "不限时 · 按自己的节奏练习"}
              </p>
            </div>
            <span className="subtle-tag">
              {mode === "exam" ? "考试节奏" : "自由节奏"}
            </span>
          </div>
          <div className="setting-row">
            <div>
              <b>即时答案反馈</b>
              <p>
                {mode === "exam"
                  ? "模拟考试交卷后统一显示答案与评分"
                  : "提交本题后显示对错；关闭则在交卷后查看"}
              </p>
            </div>
            <button
              role="switch"
              aria-checked={mode === "exam" ? false : feedback}
              aria-label="即时反馈"
              className={"switch " + (feedback && mode !== "exam" ? "on" : "")}
              disabled={mode === "exam"}
              onClick={() => setFeedback(!feedback)}
            >
              <span />
            </button>
          </div>
          <ErrorBox message={error} />
          <button
            className="primary full start-button"
            disabled={busy || !bank}
            onClick={start}
          >
            {busy ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <Play size={17} />
            )}
            开始{modes[mode] || "练习"} <ArrowRight size={17} />
          </button>
        </section>
        <aside className="practice-side">
          <div className="exam-note">
            <ShieldCheck size={33} />
            <h3>有节奏，更有把握</h3>
            <p>
              {mode === "exam"
                ? "模拟考使用服务器计时，并按能力领域抽题。请预留完整时间，减少中途打断。"
                : "不用追求一次做很多。选一个舒适的题量，认真理解每一道题。"}
            </p>
            <ul>
              <li>
                <Check size={16} />
                进度自动保存
              </li>
              <li>
                <Check size={16} />
                错题自动收录
              </li>
              <li>
                <Check size={16} />
                学习数据持续积累
              </li>
            </ul>
          </div>
          <div className="panel source-card">
            <h3>关于这份题库</h3>
            <p>来自你提供的 612 页 PDF。</p>
            <div>
              <b>{bank?.ready ?? "—"}</b> 可练习 <span />
              <b>{bank?.review ?? "—"}</b> 待核对
            </div>
            <small>
              仅已解析并通过结构检查的题目参与评分。题目领域标签不代表官方审核。
            </small>
            {mode === "exam" ? (
              <small>
                默认 100 分钟。40% / 36% / 24%
                为平台抽题配额；模拟成绩为练习得分率，不换算微软官方分数。
              </small>
            ) : null}
          </div>
        </aside>
      </div>
    </>
  );
}
function QuestionBody({
  q,
  lang,
  sessionId,
  assetBase,
}: {
  q: Question;
  lang: string;
  sessionId?: string;
  assetBase?: string;
}) {
  const base =
    assetBase || (sessionId ? `/api/v1/sessions/${sessionId}/assets/` : "");
  const images = (names: string[]) =>
    base
      ? names.map((name) => (
          <a
            key={name}
            href={`${base}${name}`}
            target="_blank"
            rel="noreferrer"
          >
            <img
              className="question-image"
              src={`${base}${name}`}
              alt="题目附图，点击查看原图"
              loading="lazy"
            />
          </a>
        ))
      : null;
  return (
    <>
      {q.case_en ? (
        <details className="case-block">
          <summary>
            <BookOpen size={17} />
            案例共享材料 · 点击展开
          </summary>
          <p className="question-text">
            {lang === "zh" && q.case_zh ? q.case_zh : q.case_en}
          </p>
          {images(q.case_assets || [])}
        </details>
      ) : null}
      <div className="question-text">{lang === "zh" && q.zh ? q.zh : q.en}</div>
      {lang === "zh" && q.translation_status === "machine" ? (
        <p className="translation-note">
          <Languages size={14} />
          离线机器翻译初稿，技术细节请对照英文原文。
        </p>
      ) : null}
      {lang === "zh" && !q.zh ? (
        <p className="translation-note">
          <Languages size={14} />
          本题中文翻译待整理，当前展示英文原文。
        </p>
      ) : null}
      {images(q.assets || [])}
    </>
  );
}
function Study() {
  const { id } = useParams(),
    nav = useNavigate();
  const [s, setS] = useState<Session | null>(null),
    [index, setIndex] = useState(0),
    [lang, setLang] = useState("zh"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [finishDialog, setFinishDialog] = useState(false),
    [remaining, setRemaining] = useState(0),
    [onlyWrong, setOnlyWrong] = useState(false),
    [paused, setPaused] = useState(false);
  const ref = useRef<Session | null>(null),
    lastActive = useRef(Date.now());
  const save = (v: Session) => {
    ref.current = v;
    setS(v);
  };
  useEffect(() => {
    api<Session>("/sessions/" + id)
      .then(save)
      .catch((e) => setError(e.message));
  }, [id]);
  useEffect(() => {
    const activity = () => {
      lastActive.current = Date.now();
    };
    window.addEventListener("pointerdown", activity);
    window.addEventListener("keydown", activity);
    return () => {
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
    };
  }, []);
  useEffect(() => {
    if (!s || s.finished) return;
    const heartbeat = setInterval(() => {
      if (
        !document.hidden &&
        !paused &&
        Date.now() - lastActive.current < 60000
      )
        send<{ finished: boolean }>("/sessions/" + id + "/heartbeat")
          .then((r) => {
            if (r.finished) api<Session>("/sessions/" + id).then(save);
          })
          .catch(() => {});
    }, 15000);
    return () => clearInterval(heartbeat);
  }, [id, s?.finished, paused]);
  useEffect(() => {
    if (!s?.deadline || s.finished) return;
    const end = s.deadline,
      offset = s.server_time * 1000 - Date.now();
    let fetching = false;
    const tick = () => {
      const left = Math.max(0, Math.ceil(end - (Date.now() + offset) / 1000));
      setRemaining(left);
      if (left === 0 && !fetching) {
        fetching = true;
        api<Session>("/sessions/" + id)
          .then(save)
          .catch((e) => {
            setError(e.message);
            fetching = false;
          });
      }
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [id, s?.deadline, s?.finished]);
  if (!s) return error ? <ErrorBox message={error} /> : <Loading />;
  const visible = onlyWrong
    ? s.questions.filter((q) => !s.results[q.id]?.correct)
    : s.questions;
  const q = visible[Math.min(index, visible.length - 1)];
  const answered = Object.values(s.answers).filter((a) =>
    a.some(Boolean),
  ).length;
  async function change(answer: string[], submit = false, flagged?: boolean) {
    const current = ref.current;
    if (!current || !q) return;
    setBusy(true);
    setError("");
    try {
      save(
        await send<Session>(
          "/sessions/" + id + "/answer",
          {
            question_id: q.id,
            answer,
            submit,
            flagged,
            version: current.version,
          },
          "PUT",
        ),
      );
    } catch (e) {
      setError((e as Error).message + "；修改未保存，请重试。");
      api<Session>("/sessions/" + id)
        .then(save)
        .catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  async function finish() {
    setBusy(true);
    setError("");
    try {
      save(await send<Session>("/sessions/" + id + "/finish"));
      setFinishDialog(false);
      setIndex(0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selected = q ? s.answers[q.id] || [] : [];
  const result = q ? s.results[q.id] : null;
  const locked = !!s.finished || !!result;
  return (
    <>
      <div className="session-heading">
        <Link className="text-button" to="/practice">
          <ArrowLeft size={17} />
          {s.finished ? "返回练习" : "保存进度并返回"}
        </Link>
        <div className="session-tools">
          <span className="subtle-tag">{modes[s.mode]}</span>
          {s.deadline && !s.finished ? (
            <span className={"timer " + (remaining < 600 ? "urgent" : "")}>
              <Clock3 size={18} />
              {String(Math.floor(remaining / 60)).padStart(2, "0")}:
              {String(remaining % 60).padStart(2, "0")}
            </span>
          ) : !s.finished ? (
            <button className="text-button" onClick={() => setPaused(!paused)}>
              {paused ? <Play size={16} /> : <Pause size={16} />}{" "}
              {paused ? "继续练习" : "暂停练习"}
            </button>
          ) : null}
          <button
            className="outline compact"
            onClick={() => setLang(lang === "zh" ? "en" : "zh")}
          >
            <Languages size={16} />
            {lang === "zh" ? "English" : "中文"}
          </button>
        </div>
      </div>
      {s.finished ? (
        <section className="result-banner">
          <div>
            <span className="eyebrow">PRACTICE COMPLETE</span>
            <h1>又向前迈出了一步。</h1>
            <p>
              答对 {Object.values(s.results).filter((r) => r.correct).length} /{" "}
              {s.questions.length} 题 · 学习 {duration(s.seconds)} ·
              错题已自动收录
            </p>
            <div className="result-actions">
              <button
                className={"outline compact " + (onlyWrong ? "selected" : "")}
                onClick={() => {
                  setOnlyWrong(!onlyWrong);
                  setIndex(0);
                }}
              >
                {onlyWrong ? "查看全部题目" : "只看错题"}
              </button>
              <Link className="outline compact" to="/mistakes">
                前往错题本 <ArrowRight size={15} />
              </Link>
            </div>
          </div>
          <div className="result-score">
            <Ring value={s.score || 0} size={104} />
            <span>本次得分率</span>
          </div>
        </section>
      ) : null}
      <ErrorBox message={error} />
      {paused && !s.finished ? (
        <div className="panel pause-screen">
          <Pause size={36} />
          <h2>休息一下，再继续</h2>
          <p>进度已保存，当前不累计学习时间。</p>
          <button
            className="primary"
            onClick={() => {
              lastActive.current = Date.now();
              setPaused(false);
            }}
          >
            继续练习 <Play size={16} />
          </button>
        </div>
      ) : (
        <div className="study-layout">
          <section className="panel question-panel">
            {q ? (
              <>
                <div className="question-meta">
                  <span className="pill">{typeNames[q.type]}</span>
                  <span>
                    Topic {q.topic} · 第 {q.number} 题
                  </span>
                  <span className="question-counter">
                    {index + 1} <small>/ {visible.length}</small>
                  </span>
                </div>
                <QuestionBody q={q} lang={lang} sessionId={s.id} />
                <div className="answers">
                  {q.type === "single" || q.type === "multiple"
                    ? q.options.map((o) => {
                        const checked = selected.includes(o.id);
                        const correct = locked && q.answer?.includes(o.id);
                        const incorrect = locked && checked && !correct;
                        return (
                          <button
                            key={o.id}
                            disabled={locked || busy}
                            className={
                              "answer-option " +
                              (checked ? "chosen " : "") +
                              (correct ? "correct " : "") +
                              (incorrect ? "incorrect" : "")
                            }
                            onClick={() =>
                              change(
                                q.type === "single"
                                  ? [o.id]
                                  : checked
                                    ? selected.filter((x) => x !== o.id)
                                    : [...selected, o.id],
                              )
                            }
                          >
                            <span className="option-letter">{o.id}</span>
                            <span>{lang === "zh" && o.zh ? o.zh : o.en}</span>
                            {correct ? (
                              <CheckCircle2 size={18} />
                            ) : incorrect ? (
                              <XCircle size={18} />
                            ) : checked ? (
                              <Check size={18} />
                            ) : null}
                          </button>
                        );
                      })
                    : q.slots?.map((slot, i) => (
                        <label key={slot.id} className="slot-answer">
                          {lang === "zh" && slot.zh ? slot.zh : slot.en}
                          <select
                            value={selected[i] || ""}
                            disabled={locked || busy}
                            onChange={(e) => {
                              const arr = [...selected];
                              while (arr.length < q.slots.length) arr.push("");
                              arr[i] = e.target.value;
                              change(arr);
                            }}
                          >
                            <option value="">请选择…</option>
                            {slot.options.map((o) => (
                              <option key={o.id} value={o.id}>
                                {lang === "zh" && o.zh ? o.zh : o.en}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                </div>
                {result ? (
                  <div
                    className={
                      "feedback " + (result.correct ? "right" : "wrong")
                    }
                  >
                    <div>
                      <span>
                        {result.correct ? (
                          <CheckCircle2 size={22} />
                        ) : (
                          <XCircle size={22} />
                        )}
                        <b>
                          {result.correct
                            ? "回答正确，继续保持"
                            : "这道题，再理解一下"}
                        </b>
                      </span>
                      <small>
                        得分 {result.earned} / {result.possible}
                      </small>
                    </div>
                    <p>参考答案：{q.answer?.join("、")}</p>
                    <p>
                      {lang === "zh"
                        ? q.explanation_zh ||
                          "原文未提供解析。可结合原始答案和参考资料复盘。"
                        : q.explanation_en ||
                          "No explanation was provided in the source PDF."}
                    </p>
                    {q.answer_assets?.map((name) => (
                      <img
                        key={name}
                        className="question-image"
                        src={`/api/v1/sessions/${s.id}/assets/${name}`}
                        alt="原文答案附图"
                      />
                    ))}
                    {q.reference
                      ?.filter((r) =>
                        /^https:\/\/(learn|docs)\.microsoft\.com\//.test(r),
                      )
                      .map((r, i) => (
                        <a key={i} href={r} target="_blank" rel="noreferrer">
                          Microsoft 参考资料 {i + 1} <ArrowUpRight size={12} />
                        </a>
                      ))}
                  </div>
                ) : null}
                <div className="question-footer">
                  <span>PDF 第 {q.pages.join("、")} 页</span>
                  {!locked ? (
                    <button
                      className={
                        "text-button " +
                        (s.flags.includes(q.id) ? "flagged" : "")
                      }
                      disabled={busy}
                      onClick={() =>
                        change(selected, false, !s.flags.includes(q.id))
                      }
                    >
                      <Flag size={16} />
                      {s.flags.includes(q.id) ? "已标记复查" : "标记复查"}
                    </button>
                  ) : null}
                  <span className="save-state">
                    {busy ? (
                      <>
                        <LoaderCircle size={13} className="spin" />
                        保存中…
                      </>
                    ) : (
                      <>
                        <Check size={13} />
                        已同步
                      </>
                    )}
                  </span>
                </div>
                <div className="question-navigation">
                  <button
                    className="outline"
                    disabled={index === 0 || busy}
                    onClick={() => setIndex(index - 1)}
                  >
                    <ChevronLeft size={16} />
                    上一题
                  </button>
                  <div>
                    {s.feedback && !locked ? (
                      <button
                        className="primary"
                        disabled={busy || !selected.some(Boolean)}
                        onClick={() => change(selected, true)}
                      >
                        确认答案 <Check size={16} />
                      </button>
                    ) : index < visible.length - 1 ? (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => setIndex(index + 1)}
                      >
                        下一题
                        <ChevronRight size={16} />
                      </button>
                    ) : !s.finished ? (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => setFinishDialog(true)}
                      >
                        交卷并查看结果 <ArrowRight size={16} />
                      </button>
                    ) : (
                      <Link className="primary" to="/practice">
                        再来一次 <RotateCcw size={16} />
                      </Link>
                    )}
                    {s.feedback && !locked && index < visible.length - 1 ? (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => setIndex(index + 1)}
                      >
                        稍后作答
                      </button>
                    ) : null}
                  </div>
                </div>
              </>
            ) : (
              <div className="empty">
                <CheckCircle2 />
                <h2>本次没有错题</h2>
                <p>所有题目都回答正确。</p>
              </div>
            )}
          </section>
          <aside className="answer-sheet panel">
            <h3>
              答题卡{" "}
              <small>
                {s.finished ? "已完成" : `${answered} / ${s.questions.length}`}
              </small>
            </h3>
            <div className="progress-track">
              <span
                style={{ width: `${(answered / s.questions.length) * 100}%` }}
              />
            </div>
            <div className="question-grid">
              {visible.map((x, i) => (
                <button
                  key={x.id}
                  className={
                    (i === index ? "current " : "") +
                    (s.results[x.id]
                      ? s.results[x.id].correct
                        ? "right "
                        : "wrong "
                      : s.answers[x.id]?.some(Boolean)
                        ? "answered "
                        : "") +
                    (s.flags.includes(x.id) ? "marked" : "")
                  }
                  onClick={() => {
                    setIndex(i);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  disabled={busy}
                >
                  {i + 1}
                </button>
              ))}
            </div>
            <div className="sheet-legend">
              <span>
                <i className="legend-current" />
                当前
              </span>
              <span>
                <i className="legend-answered" />
                已答
              </span>
              <span>
                <Flag size={12} />
                复查
              </span>
            </div>
            {!s.finished ? (
              <>
                <div className="sheet-note">
                  <ShieldCheck size={16} />
                  <p>
                    {s.feedback
                      ? "提交答案后即时显示反馈，错题自动保存。"
                      : "交卷前可自由修改答案，交卷后统一查看解析。"}
                  </p>
                </div>
                <button
                  className="outline full"
                  disabled={busy}
                  onClick={() => setFinishDialog(true)}
                >
                  结束并交卷
                </button>
              </>
            ) : null}
          </aside>
        </div>
      )}
      {finishDialog ? (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="submit-heading"
          >
            <CheckCircle2 size={35} />
            <h2 id="submit-heading">准备交卷了吗？</h2>
            <p>
              {answered < s.questions.length
                ? `还有 ${s.questions.length - answered} 道题未作答，未答题将计为 0 分。`
                : "全部题目已作答，可以查看本次成绩了。"}
              交卷后答案不能修改。
            </p>
            <div className="modal-actions">
              <button
                className="outline"
                disabled={busy}
                onClick={() => setFinishDialog(false)}
              >
                继续答题
              </button>
              <button className="primary" disabled={busy} onClick={finish}>
                确认交卷
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
function HistoryTable({ rows }: { rows: History[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>练习类型</th>
            <th>日期</th>
            <th>题量</th>
            <th>得分率</th>
            <th>状态</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <span className="table-mode">
                  <span className="table-icon">
                    {r.mode === "exam" ? (
                      <Timer size={16} />
                    ) : (
                      <BookOpen size={16} />
                    )}
                  </span>
                  {modes[r.mode]}
                </span>
              </td>
              <td>{date(r.started)}</td>
              <td>{r.count} 题</td>
              <td>
                <b>{r.score === null ? "—" : r.score + "%"}</b>
              </td>
              <td>
                <span
                  className={r.finished ? "state-complete" : "state-active"}
                >
                  {r.finished ? "已完成" : "进行中"}
                </span>
              </td>
              <td>
                <Link to={"/session/" + r.id}>
                  {r.finished ? "复盘" : "继续"}
                  <ChevronRight size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Records() {
  const [rows, setRows] = useState<History[]>([]),
    [stats, setStats] = useState<Stats | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api<History[]>("/sessions"), api<Stats>("/stats")])
      .then(([r, s]) => {
        setRows(r);
        setStats(s);
      })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR PROGRESS, OVER TIME</div>
          <h1>努力的轨迹，看得见</h1>
          <p>回顾每次练习，发现你的成长与薄弱环节。</p>
        </div>
      </div>
      <ErrorBox message={error} />
      {stats ? (
        <>
          <div className="dashboard-bottom">
            <section className="panel">
              <div className="panel-heading">
                <h2>章节正确率</h2>
                <span className="subtle-tag">按提交次数统计</span>
              </div>
              {Object.keys(stats.topics).length ? (
                <div className="topic-progress">
                  {Object.entries(stats.topics).map(([t, v]) => (
                    <div key={t}>
                      <div>
                        <span>
                          Topic {t} · {topicNames[Number(t)]}
                        </span>
                        <b>{Math.round((v.correct / v.count) * 100)}%</b>
                      </div>
                      <div className="progress-track">
                        <span
                          style={{ width: `${(v.correct / v.count) * 100}%` }}
                        />
                      </div>
                      <small>
                        {v.correct} / {v.count} 题正确
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty">完成练习后，查看各章节的掌握情况。</div>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>模拟成绩趋势</h2>
              </div>
              {stats.trend.length ? (
                <Suspense fallback={<Loading />}>
                  <Chart data={stats.trend} />
                </Suspense>
              ) : (
                <div className="empty">还没有模拟考试成绩。</div>
              )}
            </section>
          </div>
          <section className="panel recent-panel">
            <div className="panel-heading">
              <h2>练习记录</h2>
              <span>{rows.length} 次练习</span>
            </div>
            {rows.length ? (
              <HistoryTable rows={rows} />
            ) : (
              <div className="empty">
                <BookOpen />
                <p>还没有练习记录。</p>
                <Link className="primary" to="/practice">
                  开始练习
                </Link>
              </div>
            )}
          </section>
        </>
      ) : !error ? (
        <Loading />
      ) : null}
    </>
  );
}
function Mistakes() {
  const nav = useNavigate();
  type Item = {
    id: string;
    count: number;
    mastered: boolean;
    updated: number;
    question: Question;
  };
  const [rows, setRows] = useState<Item[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [search, setSearch] = useState(""),
    [tab, setTab] = useState("pending"),
    [expanded, setExpanded] = useState(""),
    [busy, setBusy] = useState(false);
  const load = () =>
    api<Item[]>("/mistakes")
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  useEffect(() => {
    load();
  }, []);
  const visible = rows.filter(
    (r) =>
      (tab === "all" || (tab === "mastered" ? r.mastered : !r.mastered)) &&
      `${r.question.zh} ${r.question.en} ${r.question.tags.join(" ")}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  async function train() {
    setBusy(true);
    try {
      const s = await send<Session>("/sessions", {
        mode: "wrong",
        count: Math.min(20, rows.filter((x) => !x.mastered).length),
        feedback: true,
      });
      nav("/session/" + s.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(row: Item) {
    setBusy(true);
    try {
      await send("/mistakes/" + row.id, { mastered: !row.mastered }, "PATCH");
      await load();
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
          <div className="eyebrow">TURN MISTAKES INTO MASTERY</div>
          <h1>每道错题，都是一个机会</h1>
          <p>重新理解，再次练习，把盲点变成你的强项。</p>
        </div>
        <button
          className="primary"
          disabled={busy || !rows.some((x) => !x.mastered)}
          onClick={train}
        >
          <RotateCcw size={16} />
          重练未掌握题目
        </button>
      </div>
      <ErrorBox message={error} />
      <section className="panel">
        <div className="list-toolbar">
          <div className="tabs">
            {[
              ["pending", "待掌握"],
              ["mastered", "已掌握"],
              ["all", "全部"],
            ].map(([v, l]) => (
              <button
                key={v}
                className={tab === v ? "selected" : ""}
                onClick={() => setTab(v)}
              >
                {l}{" "}
                <small>
                  {
                    rows.filter(
                      (r) =>
                        v === "all" ||
                        (v === "mastered" ? r.mastered : !r.mastered),
                    ).length
                  }
                </small>
              </button>
            ))}
          </div>
          <label className="search">
            <Search size={17} />
            <input
              placeholder="搜索题目或知识点"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        {loading ? (
          <Loading />
        ) : visible.length ? (
          visible.map((r) => (
            <article className="mistake" key={r.id}>
              <div className="mistake-top">
                <span className="pill">{typeNames[r.question.type]}</span>
                <span>
                  Topic {r.question.topic} · 第 {r.question.number} 题
                </span>
                <span className="mistake-count">答错 {r.count} 次</span>
              </div>
              <button
                className="mistake-title"
                onClick={() => setExpanded(expanded === r.id ? "" : r.id)}
              >
                {r.question.zh || r.question.en}
                <ChevronRight size={20} />
              </button>
              <div className="mistake-bottom">
                <div>
                  {r.question.tags.map((t) => (
                    <span className="subtle-tag" key={t}>
                      {t}
                    </span>
                  ))}
                </div>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => toggle(r)}
                >
                  <BookmarkCheck size={16} />
                  {r.mastered ? "移回待掌握" : "标记为已掌握"}
                </button>
              </div>
              {expanded === r.id ? (
                <div className="feedback right">
                  <p>参考答案：{r.question.answer?.join("、")}</p>
                  {r.question.options.map((o) => (
                    <p key={o.id}>
                      {o.id}. {o.zh || o.en}
                    </p>
                  ))}
                  <p>
                    {r.question.explanation_zh ||
                      "原文未提供解析；完整附图请在学习记录中打开对应练习复盘。"}
                  </p>
                </div>
              ) : null}
            </article>
          ))
        ) : (
          <div className="empty">
            <BookmarkCheck size={40} />
            <h3>
              {search
                ? "没有找到匹配题目"
                : tab === "pending"
                  ? "目前没有待掌握的错题"
                  : "这里还没有题目"}
            </h3>
            <p>练习中的错误会自动收录，方便你随时复盘。</p>
            <Link className="primary" to="/practice">
              去练习 <ArrowRight size={16} />
            </Link>
          </div>
        )}
      </section>
    </>
  );
}
function Settings() {
  const { user } = useContext(AuthContext),
    [bank, setBank] = useState<Bank | null>(null),
    [review, setReview] = useState<Partial<Question>[]>([]),
    [detail, setDetail] = useState<Question | null>(null),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([api<Bank>("/bank"), api<Partial<Question>[]>("/bank/review")])
      .then(([b, r]) => {
        setBank(b);
        setReview(r);
      })
      .catch((e) => setError(e.message));
  }, []);
  async function restore(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (file.size > 12 * 1024 * 1024) throw new Error("文件不能超过 12 MB");
      const data = JSON.parse(await file.text());
      const result = await send<{ imported: number; skipped: number }>(
        "/import",
        data,
      );
      setMessage(
        `已导入 ${result.imported} 次练习，跳过 ${result.skipped} 条已有记录。`,
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
          <div className="eyebrow">YOUR DATA, YOUR SPACE</div>
          <h1>管理你的学习空间</h1>
          <p>保存学习成果，了解题库的来源与整理进度。</p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>学习数据备份</h2>
            <ShieldCheck size={20} />
          </div>
          <p className="muted">
            当前账号：{user.username} · 时区：{user.timezone}
          </p>
          <p className="body-copy">
            记录存储在 Python 后端的 SQLite
            数据库中。导出已完成的练习以留存备份；导入时自动跳过重复记录。
          </p>
          <div className="backup-actions">
            <a className="primary" href="/api/v1/export" download>
              <Download size={17} />
              导出学习记录
            </a>
            <label className="outline file-input">
              <Upload size={17} />
              {busy ? "导入中…" : "导入备份"}
              <input
                type="file"
                accept="application/json,.json"
                disabled={busy}
                onChange={(e) => {
                  restore(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          {message ? (
            <p className="success" role="status">
              {message}
            </p>
          ) : null}
          <ErrorBox message={error} />
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>题库整理状态</h2>
            <Layers3 size={20} />
          </div>
          <div className="bank-counts">
            <div>
              <b>{bank?.total ?? "—"}</b>
              <span>已收录</span>
            </div>
            <div>
              <b>{bank?.ready ?? "—"}</b>
              <span>可练习</span>
            </div>
            <div>
              <b>{bank?.review ?? "—"}</b>
              <span>待核对</span>
            </div>
            <div>
              <b>{bank?.translated ?? "—"}</b>
              <span>中文初稿</span>
            </div>
          </div>
          <p className="body-copy">
            来源：SC-200_问题+答案.pdf，612
            页。图片题和答案疑点在核对完成前不会进入评分题库。
          </p>
          <small className="muted">
            题库版本 {bank?.version} · 仅供个人学习
          </small>
        </section>
      </div>
      <section className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <h2>待核对清单</h2>
            <p>保留所有题号和来源，避免静默遗漏。</p>
          </div>
          <span className="subtle-tag">{review.length} 道题</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>题目</th>
                <th>题型</th>
                <th>PDF 页码</th>
                <th>待处理原因</th>
              </tr>
            </thead>
            <tbody>
              {review.map((q) => (
                <tr key={q.id}>
                  <td>
                    <button
                      className="text-button"
                      onClick={() =>
                        api<Question>("/bank/review/" + q.id)
                          .then(setDetail)
                          .catch((e) => setError(e.message))
                      }
                    >
                      {q.id} <ArrowUpRight size={13} />
                    </button>
                  </td>
                  <td>{typeNames[q.type || ""]}</td>
                  <td>{q.pages?.join("、")}</td>
                  <td>{q.issues?.join("；")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {detail ? (
        <div className="modal-backdrop">
          <div
            className="modal review-modal"
            role="dialog"
            aria-modal="true"
            aria-label="题目核对"
          >
            <div className="panel-heading">
              <h2>{detail.id} · 待核对题目</h2>
              <button
                className="outline compact"
                onClick={() => setDetail(null)}
              >
                关闭
              </button>
            </div>
            <ErrorBox
              message={detail.issues?.join("；") || "此题尚未加入评分题库"}
            />
            <QuestionBody
              q={detail}
              lang="zh"
              assetBase={`/api/v1/bank/review/${detail.id}/assets/`}
            />
            <details className="case-block">
              <summary>英文原文</summary>
              <p className="question-text">{detail.en}</p>
            </details>
            {detail.options.map((o) => (
              <p className="body-copy" key={o.id}>
                {o.id}. {o.zh || o.en}
              </p>
            ))}
            <h3>原文参考答案（待核对）</h3>
            <p className="body-copy">
              {detail.answer?.join("、") || "见答案附图"}
            </p>
            {detail.answer_assets?.map((name) => (
              <img
                className="question-image"
                key={name}
                src={`/api/v1/bank/review/${detail.id}/assets/${name}`}
                alt="待核对的原文答案"
              />
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
