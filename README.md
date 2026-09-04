# System Agent · AI 自律成长系统

> 将个人状态、成长目标和每天的真实行动连接起来，让 AI 不只给建议，还能在授权范围内执行任务管理、记录与追踪。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=061A23)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-F4C430)](LICENSE)

## 项目简介

System Agent 是一个面向个人成长场景的全栈 Agent 应用。系统通过结构化问卷建立可复现的四维状态基线，结合成长目标、动态用户画像、近期执行反馈和 Face++ 肤质观察，由 Qwen 生成每日行动计划；用户还可以直接在对话中查询、创建、修改并完成任务或目标。

与普通聊天助手不同，系统中的状态变更必须经过 Schema 校验工具并真实写入数据库，模型回复不能代替执行结果。前端会实时展示 Planner、Tool、Observation、确认检查点和耗时，便于验证 Agent 到底做了什么。

### 核心闭环

```mermaid
flowchart LR
    A[注册与结构化评估] --> B[状态基线与动态画像]
    B --> C[成长目标 + 今日 Check-in]
    C --> D[AI 生成每日任务]
    D --> E[对话或任务页执行]
    E --> F[完成率、目标进度与趋势]
    F --> C
```

### 核心理念

- **数据说话**：用客观数据评估用户状态
- **鼓励驱动**：用正向反馈激励用户坚持
- **关注趋势**：单次失败不代表失败，关注长期进步
- **主动关怀**：检测到异常时主动询问
- **可控执行**：写操作经过意图校验，负向操作要求显式确认
- **过程可见**：前端实时展示 Plan、Tool、Observation、护栏和耗时

## Agent 架构

```mermaid
flowchart LR
    U[用户请求] --> P[Planner]
    P -->|需要数据或动作| T[Schema-validated Tools]
    T --> O[Observation]
    O --> P
    P -->|信息充分| C[Safe Context Builder]
    C --> R[流式回复]
    P -.trace.-> UI[Agent Trace UI]
    T -.trace.-> UI
    O -.trace.-> UI
```

- 单次请求可在最多 4 步内连续规划和调用多个工具，并阻止无意义的重复调用；当前采用单 Agent 受控工作流，不依赖多 Agent 编排。
- 工具参数由 Pydantic schema 校验；完成任务、记录体重、创建目标都有明确意图护栏，跳过任务必须二次确认。
- 记忆、工具结果和用户资料以“不可信数据区”进入上下文，不能覆盖系统指令，降低持久化 Prompt Injection 风险。
- SSE 同时传输执行 trace、回复 token 和运行指标；对话记录保存 `run_id`、trace 与 metrics，便于复盘。
- 数据查询和状态写入由确定性工具完成；护理建议与每日任务等生成式内容仍由模型生成，模型不可用时会明确提示失败，不以静态模板伪装 AI 结果。

## 产品预览

### 仪表盘

四维基线、今日完成度、行为成长动量与 30 秒 Check-in 汇聚在同一入口。

<p align="center">
  <img src="docs/screenshots/dashboard-overview.png" width="100%" alt="System Agent 主仪表盘" />
</p>

### 注册建档与结构化评估

基础资料只用于建档和追踪；头像用于界面展示，正面肖像仅用于 Face++ 日常肤质观察；行为评分来自结构化问卷和固定版本规则。

| 基础资料 | 可选照片 | 四维问卷 |
| --- | --- | --- |
| <img src="docs/screenshots/onboarding-basic.png" alt="基础资料录入" /> | <img src="docs/screenshots/onboarding-photo.png" alt="头像与正面肖像上传" /> | <img src="docs/screenshots/onboarding-questionnaire.png" alt="结构化状态问卷" /> |

### 可执行 Agent 对话

Agent 能发布每日任务、识别用户意图并调用工具；执行轨迹清晰展示规划、参数、Observation 和后端耗时。

<p align="center">
  <img src="docs/screenshots/chat-daily-missions.png" width="100%" alt="Agent 发布每日任务并完成打卡" />
</p>

<p align="center">
  <img src="docs/screenshots/chat-agent-trace.png" width="100%" alt="可展开的 Agent 工具执行轨迹" />
</p>

### 任务—目标—趋势闭环

任务支持完成、撤销完成、难度反馈、暂缓、改期、跳过和替换；成长目标会参与后续任务生成，执行结果同步到目标进度与趋势分析。

<p align="center">
  <img src="docs/screenshots/tasks-adaptive-schedule.png" width="100%" alt="带自适应依据的任务列表" />
</p>

<p align="center">
  <img src="docs/screenshots/growth-goals.png" width="100%" alt="成长目标与周期执行进度" />
</p>

<p align="center">
  <img src="docs/screenshots/trends-and-weight.png" width="100%" alt="状态基线、行为趋势与体重记录" />
</p>

### 画像、约束与隐私控制

用户可以维护身体数据、护理安全限制和任务可执行条件，并控制长期记忆、提醒方式、免打扰时段和个人数据。

<p align="center">
  <img src="docs/screenshots/profile-and-constraints.png" width="100%" alt="个人画像、护理安全限制与任务约束" />
</p>

<p align="center">
  <img src="docs/screenshots/settings-and-privacy.png" width="100%" alt="计划偏好、提醒、长期记忆与隐私设置" />
</p>

## 功能全景

### 四大成长维度

| 维度 | 说明 | 评估方式 |
|------|------|----------|
| 🏃 运动 | 运动频率、时长、久坐情况 | 结构化问卷 + 固定规则 |
| 🥗 饮食 | 进餐规律、蔬果与含糖饮料习惯 | 结构化问卷 + 固定规则 |
| 😴 睡眠 | 睡眠时长、规律性、醒后状态 | 结构化问卷 + 固定规则 |
| ✨ 形象管理 | 清洁护肤、防晒、仪容整理 | 结构化问卷 + Face++ 独立观察 |

### 🤖 AI 对话与上下文工程

- **Agent Runtime**：Plan → Tool → Observation 的迭代执行循环
- **受控多工具工作流**：同一请求内可组合任务、评分、体重、目标进度、资源约束与记忆工具
- **安全护栏**：危险操作确认、参数校验、最大步数和重复调用阻断
- **可观测流式响应**：SSE 实时输出 trace、正文与运行指标
- **短期上下文**：保留近期多轮对话，并通过滚动摘要压缩过长会话
- **长期记忆**：远程 Embedding + pgvector 召回，结合重要性衰减、语义重排、缓存隔离与可删除能力
- **按需上下文组装**：只注入与当前问题相关的动态画像、活跃目标、未完成事项和长期记忆，控制 Token 消耗
- **事实优先回复**：模型根据工具 Observation 组织自然语言，不直接复制内部存储文本，也不会把疑问句误存为用户事实

### 📋 任务系统

- **个性化任务**：根据目标、画像基线、近期完成率和今日 Check-in 生成每日任务
- **难度自适应**：结合精力、可用时间与历史反馈调整难度和数量
- **任务预算**：每天 1–4 个任务，可在设置中调整，低精力时自动降载
- **肤质针对性**：根据肤质分析结果生成护肤任务
- **生命周期审计**：创建、完成、暂缓、改期、跳过和替换均保存不可变事件

### 🎯 成长目标闭环

- **结构化计划**：支持执行频率、星期、具体时间、时长和提前提醒
- **量化指标**：支持单位、增加/降低方向、初始值、目标值和阈值里程碑
- **自动累计**：完成关联任务后幂等更新目标次数与数值进度
- **周期达成率**：展示本周应执行、已完成、剩余次数和到期达成率
- **执行时间线**：可查看每次任务完成或手动进度调整的来源与日期
- **周报联动**：上周复盘汇总各目标计划次数与实际完成次数
- **AI 续接**：下一轮任务生成会读取本周和累计目标进度，避免只看目标文本

### 👤 动态用户画像与记录

- **结构化画像**：汇总身体数据、偏好、可用资源、禁忌和任务约束，并记录来源与更新时间
- **体重闭环**：支持在对话或趋势页记录体重，自动同步个人画像、趋势统计与体重类目标
- **用户可控**：头像、身体数据、护理限制和任务条件均可在个人画像页查看或修改
- **记忆分层**：普通聊天记录、滚动摘要、结构化画像和长期语义记忆分别存储，避免概念混用

### 📊 评分系统

- **多维度评分**：四个维度独立评分（0-100分）
- **可复现基线**：同一份资料、同一规则版本始终得到相同分数
- **证据可解释**：保存每个答案、分项权重、置信度和规则版本
- **照片与行为解耦**：照片不用于推断运动、饮食或睡眠
- **行为闭环**：画像基线、7/28 天完成率和成长动量分别展示
- **无惩罚调整**：延后或未完成不会改变画像基线，任务会根据反馈自适应
- **评估复用**：按输入哈希复用评估记录，避免重复和漂移

### 🔍 肤质分析

- **face++ API集成**：使用旷视科技专业肤质分析API
- **单一视觉来源**：肤质观察只使用 Face++，不可用时明确返回不可用状态
- **质量前检**：上传时检查尺寸、亮度、对比度和清晰度，并清除 EXIF/GPS
- **分析来源显示**：明确标注当前使用的分析方式
- **聊天界面分析**：支持在对话中上传照片进行肤质分析
- **明确不可用状态**：Face++ 失败时不再伪造默认分数，也不会切换随机视觉模型
- **多维度检测**：黑眼圈、痘痘、毛孔、皱纹等14项指标

### 🛡️ 并发、安全与可观测性

- **同用户串行**：同一用户的 Agent 请求互斥执行，避免并发写入造成任务或目标状态错乱
- **AI 并发闸门**：Redis 分布式并发控制、过载快速失败和受控 Worker 并发
- **双层限流**：同时支持用户级和可信代理后的真实 IP 限流
- **成本保护**：单用户与全站每日 Token 预算、模型超时和失败降级策略
- **应用安全**：Argon2 密码哈希、HttpOnly Refresh Cookie、会话轮换、安全响应头和图片 EXIF 清理
- **运行观测**：健康/就绪探针、Agent Run/Step 审计、HTTP 延迟、限流、AI 并发、Token 与队列积压指标

## 🛠️ 技术栈

### 前端

- **React 19** + **TypeScript**
- **Vite 8** 构建工具
- **TailwindCSS 4** 样式框架
- **Framer Motion** 动画库
- **TanStack Query** 数据获取
- **Zustand** 状态管理
- **React Markdown** Markdown渲染

### 后端

- **FastAPI** Web框架
- **SQLAlchemy 2.0** 异步ORM
- **PostgreSQL** 数据库
- **Redis** 缓存
- **Redis Stream Worker** 持久化处理对话记忆提取
- **pgvector** 向量存储（只保存向量，不运行模型）
- **Alembic** 数据库迁移
- **APScheduler** 定时任务
- **httpx** 异步HTTP客户端
- **OpenTelemetry** Agent/LLM 调用指标标准
- **Argon2 + HttpOnly Cookie** 密码和会话安全

### AI模型（远程 API）

- **Qwen-Plus**：聊天、Agent 规划和文本分析
- **百炼 text-embedding-v4**：远程生成 1536 维文本向量，本地不下载模型

### 外部API

- **face++ 旷视**：专业肤质分析API

## 📁 项目结构

```
Self-discipline-system/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── agent/             # Planner、运行时、工具注册表、执行 trace
│   │   ├── core/              # 核心配置（数据库、安全、配置）
│   │   ├── models/            # SQLAlchemy数据模型
│   │   ├── modules/           # 功能模块（auth、chat、task等）
│   │   ├── schemas/           # Pydantic验证模型
│   │   └── services/          # 业务逻辑服务
│   │       ├── ai_service.py      # AI服务（聊天、评分）
│   │       ├── faceplus_service.py # face++肤质分析服务
│   │       ├── scheduler_service.py # 定时任务服务
│   │       └── ...
│   ├── alembic/               # 数据库迁移脚本
│   └── uploads/               # 用户上传文件
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── components/        # 可复用组件
│   │   ├── pages/             # 页面组件
│   │   ├── services/          # API服务
│   │   ├── stores/            # Zustand状态管理
│   │   └── types/             # TypeScript类型定义
│   └── public/                # 静态资源
├── docs/                       # 项目文档
├── backend/pyproject.toml      # Python 项目与 uv 锁定依赖
└── README.md                   # 项目说明
```

## 📦 安装配置

### 环境要求

- **Python** 3.11+
- **Node.js** 18+
- **PostgreSQL** 14+
- **Redis** 7+

聊天与 Embedding 均通过阿里云百炼远程 API 调用，不会在本地下载或运行向量模型。PostgreSQL 需要启用 `vector` 扩展；Alembic 首次迁移会执行 `CREATE EXTENSION IF NOT EXISTS vector`，HNSW 不可用时自动继续使用精确向量检索。

Redis 与 PostgreSQL 可以直接安装在本机，也可以使用仓库中的 `docker-compose.yml` 启动。前后端既支持本机开发模式，也支持完整 Docker Compose 编排。

### 快速开始

#### 1. 克隆项目

```bash
git clone https://github.com/amazzfanfan/Self-discipline-system.git
cd Self-discipline-system
```

#### 2. 准备 PostgreSQL 与 Redis

任选一种方式：

```bash
# 方式 A：使用 Docker 只启动基础设施
docker compose up -d postgres redis

# 方式 B：直接使用本机 PostgreSQL 14+ 和 Redis 7+
# 请确保二者已启动，并按实际账号修改 backend/.env
```

#### 3. 后端配置

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装并锁定依赖
python -m pip install uv
python -m uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填写数据库、Qwen 与 Face++ 配置
# FACEPLUSPLUS_API_KEY=...
# FACEPLUSPLUS_API_SECRET=...

# 数据库迁移
alembic upgrade head

# 启动后端服务
uvicorn app.main:app --reload --port 8000

# 另开一个终端启动持久化后台任务 Worker
python -m scripts.worker
```

开发环境默认由 API 进程内置调度器；定时任务存储在 Redis，短暂重启后会按 misfire 策略补跑。多进程生产部署应只启动一个独立调度进程，并在所有 API 实例设置 `SCHEDULER_IN_API=false`：

```bash
python -m scripts.scheduler
```

#### 4. 前端配置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

#### 5. 访问应用

- 前端：http://localhost:5174
- 后端API文档：http://localhost:8000/docs

如需完全使用 Docker，可在根目录配置环境变量后运行 `docker compose up --build`，前端访问地址为 http://localhost:3000。

### 环境变量说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DATABASE_URL` | PostgreSQL连接字符串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent` |
| `REDIS_URL` | Redis连接字符串 | `redis://localhost:6379/0` |
| `REDIS_CONNECT_TIMEOUT_SECONDS` / `REDIS_SOCKET_TIMEOUT_SECONDS` | Redis 建连与读取超时 | `2` / `5` |
| `RATE_LIMIT_STORAGE_URI` | 多实例共享限流存储；生产环境必填 | `redis://localhost:6379/0` |
| `SCHEDULER_PERSIST_JOBS` | 将调度任务持久化到 Redis | `true` |
| `SCHEDULER_IN_API` | 是否在 API 进程内运行调度器 | `true` |
| `SCHEDULER_REDIS_URL` | 可选：调度器专用 Redis；留空复用 `REDIS_URL` | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT密钥（请更换） | `your-secret-key-change-in-production` |
| `AI_API_KEY` | AI模型API密钥 | `your-ai-api-key` |
| `AI_BASE_URL` | 聊天模型API地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `AI_MODEL` | 默认 Qwen 模型 | `qwen-plus` |
| `AI_CHAT_MODEL` | 可选：单独指定聊天模型；留空时复用 `AI_MODEL` | `qwen-plus` |
| `AI_ANALYSIS_MODEL` | 可选：单独指定文本分析模型；留空时复用 `AI_MODEL` | `qwen-plus` |
| `EMBEDDING_API_KEY` | 百炼向量模型密钥；留空时复用 `AI_API_KEY` | `sk-...` |
| `EMBEDDING_BASE_URL` | 百炼 Embedding API 地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_MODEL` | 远程向量模型 | `text-embedding-v4` |
| `EMBEDDING_DIMENSION` | 输出维度，必须与 pgvector 字段一致 | `1536` |
| `FACEPLUSPLUS_API_KEY` | Face++ 肤质检测 API Key | `...` |
| `FACEPLUSPLUS_API_SECRET` | Face++ 肤质检测 API Secret | `...` |
| `TRUSTED_PROXY_CIDRS` | 允许提供真实客户端 IP 的反向代理网段 | `["127.0.0.1/32"]` |
| `CHAT_RATE_LIMIT` / `CHAT_IP_RATE_LIMIT` | Agent 用户级/IP级限流 | `20/minute` / `60/minute` |
| `AI_MAX_CONCURRENCY` | 跨进程 Qwen 同时调用上限 | `8` |
| `AI_USER_DAILY_TOKEN_LIMIT` | 单用户每日 AI Token 保护额度 | `300000` |
| `AI_GLOBAL_DAILY_TOKEN_LIMIT` | 全站每日 AI Token 保护额度 | `5000000` |
| `WORKER_CONCURRENCY` | 单个后台 Worker 总并发数 | `4` |
| `WORKER_AI_CONCURRENCY` | 单个后台 Worker AI 任务并发数 | `2` |
| `OPS_METRICS_TOKEN` | 生产环境内部指标接口凭证 | 随机 24 位以上字符串 |
| `TEMP_UPLOAD_RETENTION_HOURS` | 未被引用临时图片的保留小时数 | `24` |
| `NOTIFICATION_RETENTION_DAYS` | 站内通知保留天数 | `90` |
| `WEB_PUSH_VAPID_PUBLIC_KEY` | 可选：浏览器后台推送的 applicationServerKey | `...` |
| `WEB_PUSH_VAPID_PRIVATE_KEY` | 可选：VAPID 私钥内容或 PEM 路径 | `private_key.pem` |
| `WEB_PUSH_VAPID_EMAIL` | 可选：Web Push 联系地址 | `mailto:you@example.com` |

Web Push 未配置时，站内提醒和页面打开期间的浏览器通知仍可工作。需要关闭页面后也接收提醒时，可在 `backend` 目录生成 VAPID 密钥，并把私钥文件加入本地忽略列表：

```bash
python -m py_vapid --gen
python -m py_vapid --applicationServerKey
```

将第二条命令输出写入 `WEB_PUSH_VAPID_PUBLIC_KEY`，私钥使用 `WEB_PUSH_VAPID_PRIVATE_KEY=private_key.pem`；不要提交私钥文件。

从其他 Embedding 模型切换到 v4 后，需要重建已有数据，避免不同模型的向量混用：

```bash
cd backend
python -m scripts.reindex_embeddings
```

## ✅ 质量与验证

```bash
# 后端
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app tests
python -m scripts.evaluate_agent
python -m scripts.evaluate_agent_quality

# 前端
cd frontend
npm ci
npm run lint
npm run test
npm run build
npm run test:e2e
```

GitHub Actions 会在每次 PR 上执行同样的编译、测试、lint 和生产构建。后端还提供 `/health` 存活探针与 `/health/ready` 数据库/Redis 就绪探针。

Agent 的工具路由、危险写入、受控多工具工作流和按需上下文选择都有可复现的离线门禁；指标口径与当前基线见 [Agent 量化评测与展示指标](docs/AGENT_EVALUATION.md)。

### 本地并发基线（不调用付费模型）

先启动 OpenAI 兼容的 Mock 上游，并将测试后端的 `AI_BASE_URL`、`EMBEDDING_BASE_URL` 指向 `http://127.0.0.1:9001/v1`：

```bash
cd backend
python -m uvicorn scripts.mock_ai_server:app --port 9001
python -m scripts.load_test --scenario health --requests 100 --concurrency 20
```

还可以在另一个终端直接验证 Redis 分布式 AI 闸门，不需要账号、不会写入业务数据库：

```powershell
$env:AI_BASE_URL='http://127.0.0.1:9001/v1'
$env:AI_API_KEY='mock'
$env:AI_MAX_CONCURRENCY='3'
$env:AI_BUDGET_ENFORCEMENT='false'
python -m scripts.ai_gate_probe --requests 12 --concurrency 12
```

探针会拒绝任何非回环地址，避免误用真实百炼额度；Mock `/health` 返回的 `peak_active` 应不超过 `AI_MAX_CONCURRENCY`。

聊天压测必须显式传入测试账号 Access Token，并通过 `--allow-model-calls` 确认已指向 Mock 或愿意承担外部调用。多用户场景可通过 `--tokens-file` 传入每行一个 Token；`agent-serial` 场景会把同一 Token 的 `200` 与预期的 `409 Agent busy` 都视为保护成功。

内部观测数据位于 `GET /internal/metrics`。生产环境必须携带 `X-Ops-Token`；开发环境未配置 Token 时只允许本机回环地址访问。指标包括 HTTP 延迟桶、限流命中、AI 并发、Token 预算、Worker 数量和 Redis Stream 积压。

## 📖 使用说明

### 1. 注册账号

访问 http://localhost:5174，点击"注册"创建新账号

### 2. 完成初始评估

登录后，系统会引导你完成初始评估：
- 输入身高、体重、年龄、性别
- 所有用户都完成四组结构化状态问题
- 上传头像和正面肖像（可选；头像仅用于展示，正面肖像仅用于 Face++ 肤质观察）

### 3. 查看每日任务

系统会根据你的评分自动生成每日任务：
- 每个维度一个任务
- 难度根据评分自动调整
- 外貌任务根据肤质分析结果生成

### 4. 通过对话完成任务

在"系统对话"页面，你可以：
- 报告任务完成：`快走30分钟已完成`
- 请求跳过：`今天不想运动`（系统会要求确认）
- 确认跳过：`确认跳过运动任务`
- 记录体重：`体重70公斤`
- **肤质分析**：点击"肤质分析"按钮上传照片
- 日常对话：与AI助手交流

### 5. 查看评分趋势

在"趋势"页面查看：
- 各维度评分变化
- 历史趋势图表
- 任务完成情况

## 🔌 API文档

启动后端后，访问以下地址查看API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送到分支：`git push origin feature/your-feature`
5. 提交 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- GitHub Issues: https://github.com/amazzfanfan/Self-discipline-system/issues

## 🙏 致谢

- 感谢所有贡献者的支持
- 灵感来源于网络小说中的"系统"设定
- 感谢 [face++ 旷视](https://www.faceplusplus.com/) 提供的肤质分析API

---

<p align="center">用数据驱动成长，用AI辅助自律</p>
