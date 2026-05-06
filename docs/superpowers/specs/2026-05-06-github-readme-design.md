# GitHub上传与README设计文档

## 目标

将"系统"项目上传到GitHub，创建完整中文README文档。

## GitHub仓库

- **仓库名称：** Self-discipline system
- **可见性：** Public
- **描述：** AI驱动的自律成长系统

## README结构

### 1. 项目介绍
- 系统名称：系统（System Agent）
- 灵感来源：小说中的成长系统
- 核心理念：用数据驱动自律，用AI辅助成长
- 目标用户：想要提升自律能力的人

### 2. 功能特点
- **四大维度：** 运动、饮食、睡眠、外貌
- **AI对话：** 智能助手，支持意图识别
- **任务系统：** 每日个性化任务生成
- **评分系统：** 多维度评分，趋势追踪
- **体重记录：** 通过对话记录体重

### 3. 技术栈
- **前端：** React + TypeScript + Vite + TailwindCSS
- **后端：** FastAPI + SQLAlchemy + PostgreSQL
- **AI模型：** MiMo-V2.5（支持JSON模式）
- **其他：** Redis、Alembic、APScheduler

### 4. 项目结构
```
Self-discipline system/
├── backend/           # 后端服务
│   ├── app/
│   │   ├── core/      # 核心配置
│   │   ├── models/    # 数据模型
│   │   ├── modules/   # 功能模块
│   │   ├── schemas/   # Pydantic schemas
│   │   └── services/  # 业务逻辑
│   ├── alembic/       # 数据库迁移
│   └── uploads/       # 上传文件
├── frontend/          # 前端应用
│   ├── src/
│   │   ├── components/# 组件
│   │   ├── pages/     # 页面
│   │   ├── services/  # API服务
│   │   └── stores/    # 状态管理
│   └── public/        # 静态资源
└── docs/              # 文档
```

### 5. 安装配置教程

#### 5.1 环境要求
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 7+

#### 5.2 后端配置
```bash
# 克隆项目
git clone https://github.com/username/Self-discipline-system.git
cd Self-discipline-system/backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填写配置

# 数据库迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --reload --port 8000
```

#### 5.3 前端配置
```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

#### 5.4 环境变量说明
| 变量名 | 说明 | 示例 |
|--------|------|------|
| DATABASE_URL | 数据库连接字符串 | postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent |
| REDIS_URL | Redis连接字符串 | redis://localhost:6379/0 |
| SECRET_KEY | JWT密钥 | your-secret-key |
| AI_API_KEY | AI模型API密钥 | your-api-key |
| AI_BASE_URL | AI模型API地址 | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| AI_CHAT_MODEL | 聊天模型名称 | mimo-v2.5 |

### 6. 使用说明
1. 注册账号
2. 完成初始评估（身高、体重、年龄、性别）
3. 上传照片（可选）
4. 系统生成每日任务
5. 通过对话完成任务
6. 查看评分趋势

### 7. 截图展示
（可选，后续添加）

### 8. 贡献指南
- Fork项目
- 创建功能分支
- 提交PR

### 9. 许可证
MIT License

## 实施步骤

1. 创建GitHub仓库
2. 初始化git（如果需要）
3. 添加远程仓库
4. 编写README.md
5. 提交并推送

## 注意事项

- 确保.gitignore正确配置
- 不要上传.env文件
- 不要上传node_modules和__pycache__
- 上传前清理测试文件
