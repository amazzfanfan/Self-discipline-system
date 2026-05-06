# 聊天任务意图识别设计

## 问题描述

当前聊天接口只做对话转发，用户在聊天中说"我完成了XX任务"时，系统不会实际更新任务状态和评分。AI 回复"已记录"只是文字，数据库未变化。

## 设计方案

### 1. 意图类型

| 意图 | 触发示例 | 操作 |
|------|----------|------|
| `complete_task` | "快走30分钟我完成了" | 完成指定任务 + 更新评分 |
| `skip_task` | "今天不想做运动了" | 标记任务为 failed |
| `record_weight` | "今天体重72公斤" | 记录体重 |
| `chat` | 其他所有消息 | 正常对话 |

AI 返回结构：
```json
{"intent": "complete_task", "dimension": "exercise"}
{"intent": "skip_task", "dimension": "diet"}
{"intent": "record_weight", "weight_kg": 72.0}
{"intent": "chat"}
```

dimension 值域：`exercise`, `diet`, `sleep`, `appearance`

### 2. 新增函数

**文件：** `backend/app/services/ai_service.py`

新增 `detect_intent(message: str, today_tasks: list[dict]) -> dict` 函数：
- 使用 `settings.chat_model`
- Prompt 要求只返回 JSON
- 接收今日任务列表作为上下文（帮助 AI 判断哪个维度）
- 返回 `{"intent": "chat"}` 作为默认/失败兜底

### 3. 执行流程

修改 `backend/app/modules/chat/router.py` 中的 `send_message` 和 `stream_message`：

```
用户消息 → 保存到对话表
         → 查询今日任务列表
         → 调用 detect_intent（AI 意图识别）
         → 如果是 complete_task：
             查询今日该维度待完成任务
             调用 complete_task 逻辑更新状态+评分
             构建操作结果上下文
         → 如果是 skip_task：
             标记任务为 failed
             构建操作结果上下文
         → 如果是 record_weight：
             记录体重
             构建操作结果上下文
         → 如果是 chat：
             无额外操作
         → 将操作结果作为额外上下文传给 chat_completion
         → AI 回复（包含操作确认）
         → 保存 AI 回复
```

### 4. 意图识别 Prompt

```
分析用户消息，判断意图。只返回JSON，不要其他内容。

意图类型：
- complete_task: 用户报告完成了某个任务（运动/饮食/睡眠/外貌）
- skip_task: 用户表示不想做或放弃某个任务
- record_weight: 用户报告体重数据
- chat: 普通对话、提问、闲聊

返回格式：
{"intent": "complete_task", "dimension": "exercise"}
{"intent": "skip_task", "dimension": "diet"}
{"intent": "record_weight", "weight_kg": 72.5}
{"intent": "chat"}

dimension 只能是: exercise, diet, sleep, appearance

今日任务：
{today_tasks_json}

用户消息：{message}
```

### 5. 容错策略

- AI 返回非法 JSON → 视为 `chat`
- 意图是 `complete_task` 但今日无该维度待完成任务 → 告知用户"该任务已完成或不存在"，不调用 AI 回复
- 意图是 `record_weight` 但未提取到体重数据 → 视为 `chat`
- 意图识别 AI 调用失败 → 视为 `chat`，不影响正常对话

### 6. 代码复用

- 任务完成逻辑复用 `task/router.py` 中 `complete_task` 的核心逻辑（查询任务、更新状态、调用 `record_task_completion`）
- 体重记录复用 `weight/router.py` 中的逻辑
- 将核心逻辑提取为 service 函数，避免在 chat router 中重复

## 不变的部分

- 前端 Chat 页面不变
- task/router.py 的 complete_task 端点不变（仍然可用）
- 评分算法不变

## 测试要点

1. 用户说"快走30分钟我完成了" → 任务状态变为 completed，评分更新
2. 用户说"今天不想运动" → 任务状态变为 failed
3. 用户说"今天体重72公斤" → 体重记录表新增一条
4. 用户说"你好" → 正常对话，无意图识别操作
5. 今日无待完成任务时说"我完成了" → 提示任务已完成或不存在
