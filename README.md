# 系统 (System Agent)

> AI驱动的自律成长系统，灵感来源于小说中的成长系统

## 项目介绍

**系统**是一个帮助用户提升自律能力的AI驱动成长系统。它不是朋友，不是医生，而是一个严格但关怀的引导者。通过数据驱动和AI辅助，帮助用户在运动、饮食、睡眠、外貌四个维度实现持续的小进步。

### 核心理念

- **数据说话**：用客观数据评估用户状态
- **鼓励驱动**：用正向反馈激励用户坚持
- **关注趋势**：单次失败不代表失败，关注长期进步
- **主动关怀**：检测到异常时主动询问

## 功能特点

### 四大成长维度

| 维度 | 说明 |
|------|------|
| 🏃 运动 | 体能训练、运动习惯 |
| 🥗 饮食 | 营养摄入、饮食习惯 |
| 😴 睡眠 | 作息规律、睡眠质量 |
| ✨ 外貌 | 形象管理、皮肤护理 |

### AI对话系统

- **智能助手**：以"系统"身份与用户对话
- **意图识别**：自动识别用户报告任务完成/跳过
- **体重记录**：通过对话记录体重数据
- **流式响应**：实时流式输出AI回复

### 任务系统

- **个性化任务**：AI根据用户评分和历史生成每日任务
- **难度自适应**：根据评分自动调整任务难度
- **多维度覆盖**：每个维度每日一个任务

### 评分系统

- **多维度评分**：四个维度独立评分（0-100分）
- **趋势追踪**：记录评分变化趋势
- **任务关联**：完成任务提升评分，跳过任务降低评分

## 技术栈

### 前端

- **React 18** + **TypeScript**
- **Vite** 构建工具
- **TailwindCSS** 样式框架
- **Framer Motion** 动画库
- **TanStack Query** 数据获取
- **Zustand** 状态管理

### 后端

- **FastAPI** Web框架
- **SQLAlchemy 2.0** 异步ORM
- **PostgreSQL** 数据库
- **Redis** 缓存
- **Alembic** 数据库迁移
- **APScheduler** 定时任务

### AI模型

- **MiMo-V2.5**：聊天和意图识别（支持JSON模式）
- **MiMo-V2.5-Pro**：图像分析和评分

## 项目结构

```
Self-discipline-system/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── core/              # 核心配置（数据库、安全、配置）
│   │   ├── models/            # SQLAlchemy数据模型
│   │   ├── modules/           # 功能模块（auth、chat、task等）
│   │   ├── schemas/           # Pydantic验证模型
│   │   └── services/          # 业务逻辑服务
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
├── docker-compose.yml          # Docker配置
└── README.md                   # 项目说明
```

## 安装配置教程

### 环境要求

- **Python** 3.11+
- **Node.js** 18+
- **PostgreSQL** 14+
- **Redis** 7+

### 1. 克隆项目

```bash
git clone https://github.com/amazzfanfan/Self-discipline-system.git
cd Self-discipline-system
```

### 2. 后端配置

#### 2.1 创建虚拟环境

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

#### 2.2 安装依赖

```bash
pip install -r requirements.txt
```

#### 2.3 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填写你的配置
```

**环境变量说明：**

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DATABASE_URL` | PostgreSQL连接字符串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent` |
| `REDIS_URL` | Redis连接字符串 | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT密钥（请更换） | `your-secret-key-change-in-production` |
| `AI_API_KEY` | AI模型API密钥 | `your-ai-api-key` |
| `AI_BASE_URL` | AI模型API地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `AI_CHAT_MODEL` | 聊天模型名称 | `mimo-v2.5` |
| `AI_ANALYSIS_MODEL` | 分析模型名称 | `mimo-v2.5-pro` |

#### 2.4 数据库迁移

```bash
# 初始化数据库
alembic upgrade head
```

#### 2.5 启动后端服务

```bash
uvicorn app.main:app --reload --port 8000
```

后端服务将在 http://localhost:8000 启动

### 3. 前端配置

#### 3.1 安装依赖

```bash
cd frontend
npm install
```

#### 3.2 启动开发服务器

```bash
npm run dev
```

前端应用将在 http://localhost:5174 启动

### 4. 使用Docker（可选）

如果你熟悉Docker，可以使用docker-compose一键启动：

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 使用说明

### 1. 注册账号

访问 http://localhost:5174，点击"注册"创建新账号

### 2. 完成初始评估

登录后，系统会引导你完成初始评估：
- 输入身高、体重、年龄、性别
- 上传照片（可选，用于外貌评分）

### 3. 查看每日任务

系统会根据你的评分自动生成每日任务：
- 每个维度一个任务
- 难度根据评分自动调整

### 4. 通过对话完成任务

在"系统对话"页面，你可以：
- 报告任务完成："快走30分钟已完成"
- 跳过任务："今天不想运动"
- 记录体重："体重70公斤"
- 日常对话：与AI助手交流

### 5. 查看评分趋势

在"趋势"页面查看：
- 各维度评分变化
- 历史趋势图表
- 任务完成情况

## API文档

启动后端后，访问以下地址查看API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送到分支：`git push origin feature/your-feature`
5. 提交 Pull Request

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

如有问题或建议，请通过以下方式联系：
- GitHub Issues: https://github.com/amazzfanfan/Self-discipline-system/issues

## 致谢

- 感谢所有贡献者的支持
- 灵感来源于网络小说中的"系统"设定
