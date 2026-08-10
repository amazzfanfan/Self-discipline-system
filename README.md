# 系统 (System Agent)

> AI驱动的自律成长系统，灵感来源于小说中的成长系统

[![Version](https://img.shields.io/badge/version-v9.0-blue.svg)](https://github.com/amazzfanfan/Self-discipline-system/releases)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## ✨ 项目介绍

**系统**是一个帮助用户提升自律能力的 Agent 应用。它不只生成文本，而是根据用户请求自主规划下一步，在受控工具集中查询任务、记录体重、完成打卡、管理目标和检索长期记忆，并把每一步执行过程实时展示给用户。

### 核心理念

- **数据说话**：用客观数据评估用户状态
- **鼓励驱动**：用正向反馈激励用户坚持
- **关注趋势**：单次失败不代表失败，关注长期进步
- **主动关怀**：检测到异常时主动询问
- **可控执行**：写操作经过意图校验，负向操作要求显式确认
- **过程可见**：前端实时展示 Plan、Tool、Observation、护栏和耗时

## 🧠 Agent 架构

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

- Planner 每轮只选择一个动作，单次请求最多 4 步，并阻止重复工具调用。
- 工具参数由 Pydantic schema 校验；完成任务、记录体重、创建目标都有明确意图护栏，跳过任务必须二次确认。
- 记忆、工具结果和用户资料以“不可信数据区”进入上下文，不能覆盖系统指令，降低持久化 Prompt Injection 风险。
- SSE 同时传输执行 trace、回复 token 和运行指标；对话记录保存 `run_id`、trace 与 metrics，便于复盘。
- 主模型失败时支持可配置 fallback；无模型可用时，关键动作仍有确定性规则兜底。

## 📸 项目截图

### 身体数据采集
<p align="center">
  <img src="docs/screenshots/onboarding.png" width="700" alt="身体数据采集引导页"/>
</p>

### 主仪表盘
<p align="center">
  <img src="docs/screenshots/dashboard.png" width="700" alt="主仪表盘 - 四维评分、今日任务、趋势图表"/>
</p>

### AI 对话系统
<p align="center">
  <img src="docs/screenshots/chat.png" width="700" alt="系统对话 - 意图识别、任务完成、流式响应"/>
</p>

### 肤质分析
<p align="center">
  <img src="docs/screenshots/skin-analysis.png" width="700" alt="肤质分析 - face++ API 集成"/>
</p>

### 任务列表
<p align="center">
  <img src="docs/screenshots/task-list.png" width="700" alt="任务列表 - 按维度筛选、完成状态"/>
</p>

## 🚀 功能特点

### 四大成长维度

| 维度 | 说明 | 评估方式 |
|------|------|----------|
| 🏃 运动 | 运动频率、时长、久坐情况 | 结构化问卷 + 固定规则 |
| 🥗 饮食 | 进餐规律、蔬果与含糖饮料习惯 | 结构化问卷 + 固定规则 |
| 😴 睡眠 | 睡眠时长、规律性、醒后状态 | 结构化问卷 + 固定规则 |
| ✨ 形象管理 | 清洁护肤、防晒、仪容整理 | 结构化问卷 + Face++ 独立观察 |

### 🤖 AI对话系统

- **Agent Runtime**：Plan → Tool → Observation 的迭代执行循环
- **八个受控工具**：任务、评分、体重、目标与长期记忆
- **安全护栏**：危险操作确认、参数校验、最大步数和重复调用阻断
- **可观测流式响应**：SSE 实时输出 trace、正文与运行指标
- **长期记忆**：向量召回、重要性衰减、语义重排、缓存隔离与删除能力

### 📋 任务系统

- **个性化任务**：根据目标、画像基线、近期完成率和今日 Check-in 生成每日任务
- **难度自适应**：结合精力、可用时间与历史反馈调整难度和数量
- **任务预算**：每天 1–4 个任务，可在设置中调整，低精力时自动降载
- **肤质针对性**：根据肤质分析结果生成护肤任务

### 📊 评分系统

- **多维度评分**：四个维度独立评分（0-100分）
- **可复现基线**：同一份资料、同一规则版本始终得到相同分数
- **证据可解释**：保存每个答案、分项权重、置信度和规则版本
- **照片与行为解耦**：照片不用于推断运动、饮食或睡眠
- **行为闭环**：画像基线、7/28 天完成率和成长动量分别展示
- **无惩罚调整**：延后或未完成不会改变画像基线，任务会根据反馈自适应
- **评估复用**：按输入哈希复用评估记录，避免重复和漂移

### 🔍 肤质分析（v4.0新增）

- **face++ API集成**：使用旷视科技专业肤质分析API
- **单一视觉来源**：肤质观察只使用 Face++，不可用时明确返回不可用状态
- **质量前检**：上传时检查尺寸、亮度、对比度和清晰度，并清除 EXIF/GPS
- **分析来源显示**：明确标注当前使用的分析方式
- **聊天界面分析**：支持在对话中上传照片进行肤质分析
- **明确不可用状态**：Face++ 失败时不再伪造默认分数，也不会切换随机视觉模型
- **多维度检测**：黑眼圈、痘痘、毛孔、皱纹等14项指标

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

本项目默认不使用 Docker：Redis 与 PostgreSQL 在本机运行，Embedding 和聊天模型通过远程 API 调用。PostgreSQL 需要启用 `vector` 扩展；Alembic 首次迁移会执行 `CREATE EXTENSION IF NOT EXISTS vector`。HNSW 不可用时会自动继续使用精确向量检索。

### 快速开始

#### 1. 克隆项目

```bash
git clone https://github.com/amazzfanfan/Self-discipline-system.git
cd Self-discipline-system
```

#### 2. 后端配置

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

#### 3. 前端配置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

#### 4. 访问应用

- 前端：http://localhost:5174
- 后端API文档：http://localhost:8000/docs

### 环境变量说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DATABASE_URL` | PostgreSQL连接字符串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent` |
| `REDIS_URL` | Redis连接字符串 | `redis://localhost:6379/0` |
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

# 前端
cd frontend
npm ci
npm run lint
npm run test
npm run build
npm run test:e2e
```

GitHub Actions 会在每次 PR 上执行同样的编译、测试、lint 和生产构建。后端还提供 `/health` 存活探针与 `/health/ready` 数据库/Redis 就绪探针。

## 📖 使用说明

### 1. 注册账号

访问 http://localhost:5174，点击"注册"创建新账号

### 2. 完成初始评估

登录后，系统会引导你完成初始评估：
- 输入身高、体重、年龄、性别
- 所有用户都完成四组结构化状态问题
- 上传照片（可选；正面肖像仅用于 Face++ 肤质观察）
- 全身照片只作为成长对比素材，不参与初始评分

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

## 📝 版本历史

### v9.0 (2026-08-09)
- 🔐 私有图片鉴权、EXIF 清理、Argon2、HttpOnly refresh Cookie 与会话轮换
- 📈 将画像基线、行为完成率和成长动量解耦，增加每日 Check-in 与周复盘
- 🎯 增加任务预算、难度反馈、无惩罚延后和可量化目标
- 🧾 持久化 Agent Run/Step、待审批动作、Token/成本指标和 Redis Stream Worker
- 🧠 增加中文 n-gram 降级检索、可控记忆、数据导出和账号删除
- 🧪 增加 Agent 安全评测集、前端单测和 Playwright E2E

### v8.0 (2026-08-09)
- ♻️ 将单轮意图分发重做为可迭代 Agent Runtime
- 🛡️ 增加工具 schema、危险操作确认、重复调用与 Prompt Injection 护栏
- 🔭 增加实时执行 trace、运行指标和持久化审计数据
- 🧠 修复记忆相似度方向、缓存键隔离，并加入衰减重排
- 🎨 重做对话页，加入动态背景、微交互、执行时间线与页面转场
- ⚙️ 增加路由懒加载、CI、健康检查、幂等任务生成和可运行 Docker 编排

### v4.0 (2026-05-10)
- ✨ 集成face++旷视肤质分析API
- ✨ 初版 Face++ 肤质分析（后续版本已移除随机视觉兜底）
- ✨ 聊天界面肤质分析功能
- 🎨 统一markdown格式显示
- 🐛 修复时区问题（使用北京时间）
- 🐛 优化任务列表UI

### v3.0 (2026-05-10)
- 🐛 修复AI四维评分功能
- 🐛 修复照片分析功能
- ✨ 添加socksio代理支持

### v2.0
- ✨ AI四维评分功能
- ✨ 问卷评估系统
- ✨ 任务生成系统

### v1.0
- 🎉 初始版本发布

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
