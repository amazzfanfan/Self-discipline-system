# 首次登录消息与AI回复质量修复设计

## 问题描述

1. 用户未上传照片时，首次登录后系统不发送任何欢迎/分析消息
2. AI 回复经常是思考过程或乱码，原因是 mimo-v2.5-pro 是推理模型，回复在 `reasoning_content` 字段，当前 `_extract_content` 的关键词提取逻辑不稳定

## 设计方案

### 1. 双模型配置

**修改文件：** `backend/app/core/config.py`

新增两个配置项：
- `AI_CHAT_MODEL` — 非推理模型（如 `qwen-plus`、`deepseek-chat`），用于所有面向用户的回复场景
- `AI_ANALYSIS_MODEL` — 推理模型（如 `mimo-v2.5-pro`），用于评分计算和图片分析

保留 `AI_MODEL` 作为默认值，`AI_CHAT_MODEL` 和 `AI_ANALYSIS_MODEL` 默认回退到 `AI_MODEL`。

**模型分配：**

| 函数 | 使用模型 | 原因 |
|------|----------|------|
| `chat_completion` | AI_CHAT_MODEL | 用户对话需要直接回复 |
| `chat_completion_stream` | AI_CHAT_MODEL | 同上 |
| `generate_task` | AI_CHAT_MODEL | 任务标题需要简洁直接 |
| `generate_appearance_analysis` | AI_CHAT_MODEL | 面向用户的分析消息 |
| `generate_body_analysis`（新增） | AI_CHAT_MODEL | 面向用户的分析消息 |
| `evaluate_initial_score` | AI_ANALYSIS_MODEL | 需要推理能力计算评分 |
| `analyze_image` | AI_ANALYSIS_MODEL | 需要视觉推理能力 |

### 2. 首次登录消息逻辑修复

**修改文件：** `backend/app/modules/user/router.py`

当前 `evaluate` 函数（line 155）只处理了有照片的情况：
```python
if profile.front_photo_url:
    # 生成外貌分析消息
```

修改为：
```python
if profile.front_photo_url:
    # 调用 generate_appearance_analysis（分析外貌/体态）
else:
    # 调用新增的 generate_body_analysis（基于身高/体重/年龄/性别）
```

**新增函数：** `backend/app/services/ai_service.py` 中的 `generate_body_analysis`

功能：基于用户的身高、体重、年龄、性别，生成综合身体状况评价和改善建议。

Prompt 设计：
- 计算 BMI 并参考中国标准
- 给出当前身体状况评估
- 提供 3 条具体改善建议
- 一句鼓励
- 200 字以内

### 3. 简化 `_extract_content`

**修改文件：** `backend/app/services/ai_service.py`

当前函数有 4 种启发式提取策略（正则匹配引号、关键词标记、最后段落、最后短行），对非推理模型不必要且有害。

修改为：
1. 优先使用 `content` 字段（非推理模型的主要输出字段）
2. 如果 `content` 为空，降级使用 `reasoning_content` 的最后 300 字符
3. 清理首尾空白和常见无用前缀

删除所有关键词匹配、引号提取、标记提取逻辑。

### 4. 环境变量

**修改文件：** `backend/.env.example`

新增：
```
AI_CHAT_MODEL=qwen-plus
AI_ANALYSIS_MODEL=mimo-v2.5-pro
```

## 不变的部分

- 首次任务生成逻辑（`generate_tasks_for_user` 调用位置和时机）不变
- 评分算法不变
- 前端 Onboarding 流程不变
- 对话模块的 WebSocket/SSE 流式传输逻辑不变

## 测试要点

1. 新用户注册 → 评估（有照片）→ 检查是否收到外貌分析消息 + 任务消息
2. 新用户注册 → 评估（无照片）→ 检查是否收到身体综合评价消息 + 任务消息
3. 发送聊天消息 → 检查 AI 回复是否是正常面向用户的回复（非思考过程）
4. 检查任务标题是否正常生成（非默认值）
