# System Agent - 个人成长系统 设计文档

## 1. 项目概述

**项目名称**：System Agent（个人成长系统）

**灵感来源**：小说中的"系统"概念——一个引导主角成长的智能存在。

**核心定位**：AI驱动的个人外形提升助手，通过每日任务、累计评分、AI对话引导用户持续改善自己。

**目标用户**：希望改善外形（运动、饮食、睡眠、皮肤）但缺乏自律和科学指导的人群。

---

## 2. 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | React 18 + TypeScript + Vite | 类型安全，构建快 |
| UI | TailwindCSS + Headless UI | 原子化CSS，无障碍组件 |
| 状态管理 | Zustand + React Query | 轻量状态 + 服务端数据缓存 |
| 动画/图表 | Framer Motion + Recharts | 丝滑动画 + 数据可视化 |
| 后端 | Python + FastAPI | 异步高性能，AI生态好 |
| 数据库 | PostgreSQL | ACID事务，JSONB灵活扩展 |
| 缓存 | Redis | 会话、评分缓存、任务队列 |
| AI模型 | 通义千问/文心一言 | 多模态，国内访问友好 |
| 文件存储 | 阿里云OSS | 图片加密存储 |
| 定时任务 | APScheduler | 任务发布、评分计算 |
| 部署 | Vercel(前端) + Railway/Render(后端) | 免费额度，面试演示 |

---

## 3. 系统架构

```
React SPA (TypeScript)
    ↕ HTTPS / WebSocket
FastAPI Backend (Python)
    ├── 用户模块 — 注册/登录/画像管理
    ├── 任务模块 — AI生成/定时发布/完成记录
    ├── 评分模块 — 四维度算法/历史趋势
    ├── 对话模块 — AI引导对话/上下文记忆
    ├── AI服务层 — 图片分析/对话生成/任务推荐
    └── 调度模块 — APScheduler定时任务
    ↕
PostgreSQL (主存储) + Redis (缓存/会话)
```

**架构决策**：采用模块化单体架构。
- 模块边界清晰（用户、任务、评分、对话各自独立）
- 单人开发效率高，部署简单
- FastAPI异步特性天然支持高并发
- 后期可平滑演进为微服务

---

## 4. 数据库设计

### 4.1 users 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| email | VARCHAR (unique) | 邮箱（登录名） |
| password_hash | VARCHAR | bcrypt哈希 |
| nickname | VARCHAR | 昵称 |
| avatar_url | VARCHAR | 头像URL |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 4.2 user_profiles 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| height_cm | DECIMAL | 身高(cm) |
| weight_kg | DECIMAL | 体重(kg) |
| age | INTEGER | 年龄 |
| gender | ENUM (male/female/other) | 性别 |
| body_fat_pct | DECIMAL (nullable) | 体脂率 |
| front_photo_url | VARCHAR | 正面照 |
| side_photo_url | VARCHAR (nullable) | 侧面照 |
| ai_profile_score | JSONB | AI分析原始数据 |
| updated_at | TIMESTAMP | 更新时间 |

### 4.3 user_scores 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| dimension | ENUM (exercise/diet/sleep/appearance) | 评分维度 |
| score | DECIMAL (0-100) | 当前分数 |
| total_positive_count | INTEGER | 累计正向行为次数 |
| total_negative_count | INTEGER | 累计负向行为次数 |
| streak_days | INTEGER | 当前连续天数 |
| last_score_change | TIMESTAMP | 上次分数变动 |
| updated_at | TIMESTAMP | 更新时间 |

### 4.4 tasks 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| dimension | ENUM | 所属维度 |
| title | VARCHAR | 任务标题 |
| description | TEXT | 任务描述 |
| difficulty | ENUM (easy/medium/hard) | 难度 |
| scheduled_date | DATE | 计划日期 |
| status | ENUM (pending/in_progress/completed/failed) | 状态 |
| completion_proof | TEXT (nullable) | 完成凭证 |
| completed_at | TIMESTAMP (nullable) | 完成时间 |
| created_at | TIMESTAMP | 创建时间 |

### 4.5 score_history 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| dimension | ENUM | 评分维度 |
| delta | DECIMAL | 变动值 (+0.1 / -0.1) |
| reason | VARCHAR | 变动原因 |
| task_ids | UUID[] | 关联任务ID列表 |
| created_at | TIMESTAMP | 创建时间 |

### 4.6 conversations 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| role | ENUM (system/user) | 消息角色 |
| content | TEXT | 消息内容 |
| metadata | JSONB | 附加数据（任务ID、评分变动等） |
| created_at | TIMESTAMP | 创建时间 |

### 4.7 weight_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK→users) | 关联用户 |
| weight_kg | DECIMAL | 体重记录 |
| recorded_at | DATE | 记录日期 |
| ai_evaluation | JSONB | AI评估结果 |
| created_at | TIMESTAMP | 创建时间 |

---

## 5. 评分算法

### 5.1 核心原则

- **不是完成一次任务就加分，而是坚持一段时间后才加分**
- 分数变化幅度 ±0.1，符合真实人体变化节奏
- 负向扣分由AI驱动，非硬编码
- 体重变化看趋势，单次波动不触发

### 5.2 正向加分规则（达到累计阈值后 +0.1）

| 维度 | 基础阈值 | 坚持奖励 | 真实变化周期 |
|------|---------|---------|-------------|
| 运动/体态 | 连续7天 | 连续30天额外+0.1 | 2-4周 |
| 饮食/营养 | 连续5天 | 连续21天额外+0.1 | 1-2周 |
| 睡眠/作息 | 连续7天 | 连续30天额外+0.1 | 1-3周 |
| 外貌/皮肤 | 连续14天 | 连续60天额外+0.1 | 4-8周 |

**"连续天数"定义**：用户完成该维度当日所有任务即计为1天。若当日有多个任务（如运动+饮食），需全部完成才计入对应维度的连续天数。某一天中断则该维度连续天数重置为0，但不影响其他维度。

### 5.3 负向扣分规则（AI驱动）

不再硬编码"中断即扣分"，由AI综合判断：

**触发条件**：
- 系统检测到用户连续3天以上未完成某维度任务 → AI分析是否需要扣分
- 用户主动汇报负向行为（暴食、熬夜等）→ AI评估严重程度

**AI判断考虑因素**：
- 中断频率和持续时间
- 是否有补偿行为
- 历史完成模式
- 用户整体趋势

**扣分后对话**："系统检测到你最近连续X天没有运动，评分调整-0.1"

### 5.4 体重模块

- 用户定期汇报体重（建议每周1次）
- AI根据身高、当前体重、目标体重判断变化合理性
- **BMI偏高用户**：体重下降0.5-1kg/周 → 运动+饮食维度 +0.1
- **BMI正常用户**：体重稳定±0.5kg → 不变
- **BMI偏低用户**：体重增加0.5-1kg/周 → 运动+饮食维度 +0.1
- **异常波动**：一周变化>2kg → AI主动对话询问原因
- **关键**：看连续2-3周趋势，单次波动不触发

### 5.5 初始评分

由AI根据用户数据评估，范围40-70分：
- 身高体重 → BMI评估 → 运动/饮食维度基础分
- 正面/侧面照 → AI分析体态、皮肤 → 外貌维度基础分
- 年龄、性别 → 调整系数（不同年龄段标准不同）

**照片缺失降级策略**：
- 用户未上传照片 → 外貌维度默认50分，提示"上传照片可获得更精准的AI评估"
- 用户仅提供身高体重 → 运动/饮食维度由BMI推算，外貌/睡眠维度默认50分
- 用户拒绝提供任何数据 → 所有维度默认50分，引导后续补充

**AI评分Prompt**："基于身高{X}cm、体重{Y}kg、年龄{Z}岁，评估该用户的运动/饮食/外貌维度得分（0-100），参考中国成年人健康标准"

### 5.6 任务生成逻辑

每日8:00由定时任务触发，AI为每个用户生成当日任务。

**生成规则**：
- 每天每个维度1-2个任务，总任务数3-6个
- 任务难度根据用户当前评分动态调整（评分低→简单任务，评分高→挑战任务）
- 优先补齐用户薄弱维度（评分最低的维度多分配任务）
- 避免连续两天完全相同的任务（防止枯燥）

**任务模板示例**：
- 运动：跑步机爬坡40分钟、做30个俯卧撑、快走60分钟
- 饮食：午餐吃鸡胸肉沙拉、全天喝满8杯水、晚餐不吃主食
- 睡眠：23:00前入睡、午休不超过30分钟、睡前1小时不看手机
- 外貌：敷面膜一次、涂防晒出门、认真洗脸护肤

**AI生成Prompt**：
"用户{nickname}，{dimension}维度当前评分{score}分。请生成1个今日任务，要求：难度{difficulty}，具体可执行，有明确的完成标准。参考用户历史任务，避免重复。"

---

## 6. AI对话系统

### 6.1 对话场景

| 场景 | 触发方式 | 说明 |
|------|---------|------|
| 每日任务推送 | 系统定时（8:00） | AI主动推送当日任务 |
| 任务完成确认 | 用户汇报 | AI确认记录+显示进度 |
| 负向行为汇报 | 用户主动 | AI不批评，分析原因给建议 |
| 愧疚式激励 | AI触发 | 连续未完成时使用 |
| 定期复盘 | 系统定时（每周/月） | AI分析趋势、调整策略 |
| 图片分析 | 用户上传 | AI评估体态皮肤变化 |
| 体重汇报 | 用户主动 | AI评估体重变化趋势 |
| 自由对话 | 用户随时 | AI保持系统人设引导 |

### 6.2 对话策略矩阵

| 模式 | 触发条件 | 语气 |
|------|---------|------|
| 鼓励模式 | 正常完成任务 | 积极、肯定 |
| 温和提醒 | 偶尔中断1天 | 理解、鼓励 |
| 愧疚激励 | 连续多天未完成 | 严肃、触动 |
| 关怀模式 | 检测到情绪低落 | 温暖、支持 |
| 复盘模式 | 每周/月定期 | 分析、引导 |
| 引导模式 | 新用户/初期 | 耐心、教学 |

### 6.3 愧疚式激励策略

**轻度（连续2-3天未完成）**：温和提醒 + 对比历史
> "上次你坚持了12天，那时候的你比现在更有行动力"

**中度（连续5-7天未完成）**：强调损失 + 降低行动门槛
> "每拖一天，之前积累的连续天数都在浪费。今天只需要30分钟，就能重新开始"

**重度（连续10天+）**：情感触动 + 唤起初心
> "你在注册时告诉系统，你想成为更好的自己...系统不会生气，但系统替你感到可惜"

**安全阀机制**：
- 同一用户同一维度，每周最多触发1次
- 用户说"别说了" → 立即停止，切换鼓励模式
- 检测到情绪低落 → 暂停愧疚策略，切换关怀模式
- 连续多次忽略 → 切换关怀模式

### 6.4 AI人设

```
你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。
你的职责是帮助用户提升自己。
你不是朋友，不是医生，而是一个严格但关怀的引导者。
你用数据说话，用鼓励驱动，偶尔带一点幽默。
你相信持续的小进步会带来大变化。
```

**对话原则**：
- 不批评，不说教 — 用数据和事实引导
- 承认人性 — 偶尔放松是正常的
- 关注趋势 — 单次失败不代表失败
- 主动关怀 — 检测到异常时主动询问
- 保持人设 — 始终以"系统"身份对话

---

## 7. 前端设计

### 7.1 设计风格

- 暗色主题，科技感，符合"系统"人设
- 数据可视化为核心（评分环形图、进度条、趋势线）
- Framer Motion实现丝滑动画过渡
- 响应式布局，PC和移动端适配

### 7.2 页面结构

| 页面 | 路由 | 功能 |
|------|------|------|
| Dashboard | `/` | 综合评分、四维度进度、今日任务 |
| 对话 | `/chat` | AI对话交互（核心页面） |
| 趋势 | `/trends` | 评分历史图表、变化趋势 |
| 画像 | `/profile` | 用户资料、照片上传、AI评估 |
| 任务 | `/tasks` | 任务列表、完成历史、筛选 |
| 设置 | `/settings` | 目标设定、偏好配置、通知管理 |

### 7.3 核心交互

- **对话为主**：用户主要通过对话与系统交互
- **任务确认**：用户在对话中汇报完成，系统自动记录
- **图片上传**：在画像页面上传照片，触发AI分析
- **评分展示**：Dashboard实时展示评分变化
- **趋势图表**：折线图展示各维度评分历史

---

## 8. API设计

### 8.1 认证

- `POST /api/auth/register` — 注册
- `POST /api/auth/login` — 登录（返回JWT）
- `POST /api/auth/refresh` — 刷新Token
- `POST /api/auth/logout` — 登出

### 8.2 用户

- `GET /api/users/me` — 获取当前用户信息
- `PUT /api/users/me` — 更新用户信息
- `POST /api/users/me/photos` — 上传照片
- `GET /api/users/me/profile` — 获取画像
- `PUT /api/users/me/profile` — 更新画像

### 8.3 评分

- `GET /api/scores` — 获取当前评分（四维度）
- `GET /api/scores/history` — 评分历史（分页）
- `GET /api/scores/trends` — 趋势数据（图表用）

### 8.4 任务

- `GET /api/tasks/today` — 获取今日任务
- `POST /api/tasks/{id}/complete` — 完成任务
- `GET /api/tasks` — 任务列表（筛选/分页）

### 8.5 对话

- `POST /api/chat/send` — 发送消息
- `GET /api/chat/history` — 对话历史
- `WebSocket /ws/chat` — 实时对话

### 8.6 体重

- `POST /api/weight` — 记录体重
- `GET /api/weight/history` — 体重历史

---

## 9. 安全设计

### 9.1 认证授权
- JWT + Refresh Token 双令牌
- Access Token 15分钟过期
- Refresh Token 7天，存HttpOnly Cookie
- 敏感操作需二次验证

### 9.2 数据安全
- 密码 bcrypt 加盐哈希
- 用户照片加密存储（OSS + KMS）
- SQL注入防护（ORM参数化查询）
- XSS防护（DOMPurify + 后端转义）

### 9.3 接口安全
- 限流：每用户 60次/分钟（slowapi）
- CORS 白名单配置
- 文件上传：类型校验 + 大小限制（5MB）

### 9.4 审计日志
- 操作日志：登录/评分变动/敏感操作
- 结构化日志（JSON格式）
- 异常告警（错误率>5%自动通知）

---

## 10. 高并发设计

### 10.1 异步架构
- FastAPI 原生 async/await
- 数据库连接池（asyncpg，20连接）
- AI调用异步化（不阻塞主线程）

### 10.2 缓存策略
- Redis 缓存用户评分（TTL 5分钟）
- Redis 缓存今日任务（TTL 到当天24:00）
- 对话上下文 Redis 暂存
- 缓存击穿：分布式锁 + 热点预加载

### 10.3 数据库优化
- 索引：user_id + dimension 复合索引
- 分页查询（避免全表扫描）
- 慢查询监控（>500ms告警）

### 10.4 定时任务
- APScheduler 管理定时任务
- 每日8:00批量生成任务（分批处理）
- 每日凌晨跑评分计算（错峰）
- 任务幂等性保证

---

## 11. 部署架构

```
用户 → Cloudflare CDN → 静态资源（React SPA）
用户 → Nginx → FastAPI (Gunicorn + Uvicorn workers)
    → PostgreSQL（主库）+ Redis（缓存）
    → 通义千问/文心 API（AI服务）+ OSS（文件存储）
```

- 前端：Vercel 部署
- 后端：Railway/Render 部署
- 数据库：云数据库 PostgreSQL
- 缓存：云 Redis
- 文件：阿里云 OSS

---

## 12. 项目结构

```
xitong/
├── frontend/                # React前端
│   ├── src/
│   │   ├── components/      # 通用组件
│   │   ├── pages/           # 页面组件
│   │   ├── hooks/           # 自定义Hook
│   │   ├── stores/          # Zustand状态
│   │   ├── services/        # API调用
│   │   ├── types/           # TypeScript类型
│   │   └── utils/           # 工具函数
│   ├── package.json
│   └── vite.config.ts
├── backend/                 # FastAPI后端
│   ├── app/
│   │   ├── modules/         # 业务模块
│   │   │   ├── auth/        # 认证模块
│   │   │   ├── user/        # 用户模块
│   │   │   ├── task/        # 任务模块
│   │   │   ├── score/       # 评分模块
│   │   │   ├── chat/        # 对话模块
│   │   │   └── weight/      # 体重模块
│   │   ├── services/        # 服务层
│   │   │   ├── ai/          # AI服务
│   │   │   └── scheduler/   # 调度服务
│   │   ├── models/          # 数据模型
│   │   ├── schemas/         # Pydantic Schema
│   │   ├── core/            # 核心配置
│   │   │   ├── config.py    # 环境配置
│   │   │   ├── security.py  # 安全工具
│   │   │   └── database.py  # 数据库连接
│   │   └── main.py          # 应用入口
│   ├── requirements.txt
│   └── alembic/             # 数据库迁移
├── docs/                    # 文档
└── docker-compose.yml       # 容器编排
```
