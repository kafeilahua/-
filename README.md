# 知序 · SC-200 中文学习平台

基于提供的 `SC-200_问题+答案.pdf` 构建。React 前端，Python / FastAPI 后端，uv 管理 Python 项目，SQLite 持久化学习记录。

## 本地运行

需要 Python 3.11+、uv、Node.js 22+。题库 JSON 和附图已随项目提供，日常运行不依赖 OCR 或翻译模型。

```bash
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开 http://localhost:8000，自行注册账号。账号数据保存在服务端，默认启动命令仅允许本机访问。接口文档在 `/docs`。

开发时在两个终端分别运行：

```bash
uv run uvicorn backend.main:app --reload --port 8000
npm --prefix frontend run dev
```

前端开发地址为 http://localhost:5173，Vite 将 `/api` 转发给本地后端。若通过其他域名访问 Vite，把该完整 Origin 加入 `SC200_ALLOWED_ORIGINS`（逗号分隔）。生产构建同源部署不需配置此项。

## 功能

- 模拟考试：40 / 50 / 60 题，默认 50 题、100 分钟；服务器计时，超时自动交卷，刷新不重置计时。
- 随机练习：10 / 20 / 50 题及 1–100 题自定义题量，不重复抽题，即时反馈可开关。
- 专项训练：按 PDF Topic 或知识标签筛选；案例题携带共享材料。
- 单选、多选、排序及下拉式复合题；触控、键盘可操作。
- 错题自动收录、重练、手动标记掌握；再次答错后恢复待复习。
- 错题按到期状态、章节、知识点、最近答错时间、错误次数筛选，支持排序、分页和按当前筛选重练。
- 间隔复习计划、薄弱章节推荐、知识点正确率及有学习记录周的变化趋势。
- 收藏题目并定向练习、账号私有笔记、题目纠错反馈与撤回。
- 正确率、章节统计、模拟成绩趋势、每日题量与用时热力图。
- 中文与英文原文切换，区分人工校对与离线机器翻译初稿。
- 学习记录 JSON 导出、导入去重；题库核对页面可阅读待核对题目和原始答案附图。

## 题库质量与适用边界

源 PDF 共 **612 页、410 个唯一题号、13 个 Topic**。完整 OCR 已由用户的本地 PaddleOCR 服务执行。当前精确的可评分数量、翻译状态与待核对题号记录在 `data/import-report.json`，应用的“数据与题库”页会显示相同状态。

全题库已生成中文初稿；机器翻译并不等同于人工校对。部分拖拽题、图片热点题、含重复选项编号或有答案争议的题保留为待核对状态，只能查阅，不参与自动评分。所有题号都有明确状态，未用演示题代替源文档。

原文中的产品名称、功能和答案可能对应旧版本。标准答案来自 PDF，社区投票不会覆盖原文答案；明显冲突会列入待核对。没有原文解析时明确显示“原文未提供解析”。

[微软当前 SC-200 考试说明](https://learn.microsoft.com/en-us/credentials/certifications/security-operations-analyst/)标注 100 分钟；题型比例不公开。本平台模拟考采用 40% / 36% / 24% 的能力领域配额，题目领域按内容推断，题型依可用题库抽取；题量不足时拒绝生成并提示调整。练习百分比不换算为微软官方分数，也不保证通过考试。

## 数据与评分

- 默认数据库：`data/study.db`；可用 `SC200_DATA_DIR` 修改存储目录。首次启动自动应用 Alembic 迁移。
- 密码使用 Argon2id；登录采用 HttpOnly / SameSite Cookie。修改接口校验 CSRF 和请求 Origin，记录按账号隔离。
- 生产 HTTPS 部署设置 `SC200_SECURE_COOKIE=1`。本地 HTTP 开发保持为 0。
- 每次训练固定题目快照、题目版本与顺序，题库更新不会改变既有训练。
- 单选、多选整题全对才得分；复合题按答题槽计分。正确率的分母是已提交的题目次数，未答交卷计错误；同题复练形成新事件。
- 模拟平均分只统计已交卷模拟考试。前台且近期有操作时通过心跳累计用时，暂停/后台不持续累计；模拟倒计时独立运行。
- SQLite 写事务串行化，并使用唯一约束与版本检查处理重复交卷和多标签页修改。
- JSON 备份包含已完成训练、错题复习计划、收藏、已保存笔记和纠错记录，不包含密码和登录凭据。要求题库版本匹配，重新校验答案并评分；不导入不可信的分数或标准答案。v2 支持重复、重叠以及跨账号往返导入去重，同时保留较新的本地笔记；仍兼容旧 v1 备份。

## 错题复习与个人资料

在“我的错题”中组合筛选条件，再选择最多 10 / 20 / 50 题开始重练。实际题目来自当前筛选结果，按列表排序取前 N 道可评分题；不会从其他题目补足数量。已掌握的错题也可切换到对应分类再次练习。展开题目即可查看原题、案例材料、参考答案与附图，并记录笔记或反馈。

复习安排采用简单的 **1 / 3 / 7 / 14 / 30 天**间隔：

- 新错题或再次答错的题立即进入待复习，间隔重置。
- 到期后答对，推进到下一轮间隔；提前答对不额外推进，重复提交不重复计数。
- 手动标记“已掌握”暂停提醒；移回待掌握后立即可复习。提醒显示在平台内。
- 推荐章节依据最近 30 天、至少 3 次作答的表现；知识点折线展示有记录的各周，变化值与上一次有记录周比较。正确率反映实际作答表现，不等同于认证能力判定。

答题页和错题展开区均提供收藏、笔记、反馈入口。“收藏与笔记”页集中管理这些资料，并可练习当前筛选范围内的收藏题。

笔记保存到账号，支持多页面版本冲突检查；未保存草稿仅保存在当前浏览器，按账号与题号区分，不包含在服务端备份中。冲突时保留草稿，读取最新版本后可明确选择再次保存。收藏、笔记和反馈均按账号隔离。

纠错反馈记录问题类型与说明，可以撤回；当前尚未提供管理员审核工作台，不会自动修改题库答案。待核对题目仍不参加评分。

已有数据库在启动时自动从 Alembic 001 升级到 002，保留原有账号与学习记录。

数据库完整备份（包含 WAL 中尚未归并的数据）：

```bash
uv run python -m scripts.backup /tmp/sc200-backup.db
```

恢复完整数据库时先停止服务，将备份放回配置的数据库位置，勿在运行中直接覆盖 SQLite 文件。首次迁移可单独执行 `uv run alembic upgrade head`。

## 重新提取与整理题库

源 PDF 文件放在项目根目录。只需修改译文或修正题目时，编辑 `data/overrides.json`，再运行富化与验证命令；无需重新 OCR。

```bash
# 上传至用户提供的本地 OCR API，返回任务 ID
uv run python -m scripts.ocr submit SC-200_问题+答案.pdf
uv run python -m scripts.ocr status TASK_ID
uv run python -m scripts.ocr download TASK_ID
# 已完成的原始 OCR JSON 默认保存为 data/ocr-result.json

uv run python -m scripts.import_pdf --assets
uv run python -m scripts.enrich_bank
uv run python -m scripts.validate_bank
```

OCR 默认地址 `http://192.168.1.10:8000`，可使用 `--url` 或 `SC200_OCR_URL` 修改。客户端也支持 `retry`、`cancel`。8501 是 OCR 的网页入口，不是业务后端。题库发生更改后重启应用加载新版本。

离线中文初稿使用 Argos Translate 的英译中模型。只需重新生成译文时安装可选依赖：

```bash
uv sync --group translation
uv run --group translation python -m scripts.translate_bank --model /path/to/translate-en_zh-1_9
uv run python -m scripts.enrich_bank
```

模型来自 [Argos Translate](https://github.com/argosopentech/argos-translate)，下载后本机推理，题库正文不发送到外部翻译服务。模型和下载缓存不提交到 Git。

`structure_hotspots` 可从 OCR 坐标与答案图颜色/标记生成候选结构；候选不自动发布。核对选项、分项数量、代码字符与答案后，将确认内容加入 overrides。每次富化都会更新内容版本及质量报告。

## 测试

```bash
uv run pytest -q
uv run python -m scripts.validate_bank
npm --prefix frontend test
npm --prefix frontend run build
```

测试覆盖认证与账号隔离、CSRF、答案资源访问、评分、抽题配额、超时、并发版本冲突、幂等交卷、错题状态、间隔时序、定向训练、笔记草稿与版本冲突、备份往返去重以及真实旧库迁移。2026-09-07 验收通过 29 项后端测试、14 项前端测试和生产构建；浏览器验证了筛选重练、答对后的复习时间更新、收藏练习、笔记保存、反馈与撤回、桌面和 390px 手机布局。

## Docker 部署

```bash
docker compose up --build
```

访问 http://localhost:8000。数据库保存在 `study-data` 卷中；镜像包含构建后的 React 页面、题库 JSON 与附图。Compose 默认不设置系统开机自启。本次已验证 Compose 配置；本机 Docker 引擎未运行，镜像构建尚未验证。本地构建和启动已通过验收。

源资料原始链接保留于项目历史 README；本项目处理的是根目录本地 PDF，不自动获取远程文档。
