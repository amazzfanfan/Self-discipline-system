# AI 四维评分系统设计文档

## 目标

将用户初始评分从"外貌AI评分 + 其余固定50分"升级为：AI 根据照片或问卷数据对运动、饮食、睡眠、外貌四个维度分别独立评分。

## 方案

**混合模式（方案C）：**
- **有照片**：4 个维度并行调用 AI（asyncio.gather），每个维度独立 prompt 分析照片
- **无照片**：对话式问卷 + 身体数据 → 单次 AI 调用返回四维评分

## 问卷设计

当用户未上传照片时，系统以对话形式依次询问 4 个问题，用户在输入框自由回答：

| 维度 | 问题 |
|------|------|
| 运动 | 你每周运动几次，一次运动多长时间？ |
| 饮食 | 你的饮食规律如何？ |
| 睡眠 | 你通常几点睡觉，每次睡几个小时？ |
| 外貌 | 你平常是否有注意打理自己，你对自己的外在形象满意吗？ |

## 数据模型变更

### UserProfile 新增字段

```python
questionnaire = Column(JSON, nullable=True)
```

存储格式：
```json
{
  "exercise": "每周跑步3次，每次30分钟",
  "diet": "三餐规律，偶尔吃夜宵",
  "sleep": "通常11点睡，睡7个小时",
  "appearance": "比较注意，基本每天洗脸护肤"
}
```

### EvaluateRequest 新增字段

```python
questionnaire: dict[str, str] | None = None
```

## API 变更

### POST /api/users/me/evaluate

请求体新增可选 `questionnaire` 字段：

```json
{
  "height_cm": 175,
  "weight_kg": 70,
  "age": 25,
  "gender": "male",
  "questionnaire": {
    "exercise": "每周跑步3次...",
    "diet": "三餐规律...",
    "sleep": "11点睡...",
    "appearance": "基本护肤..."
  }
}
```

返回值中 `scores` 包含四维评分：

```json
{
  "message": "evaluation complete",
  "scores": {
    "exercise": 65,
    "diet": 70,
    "sleep": 55,
    "appearance": 60
  }
}
```

## AI 服务变更（ai_service.py）

### 新增函数

#### `evaluate_all_scores(height_cm, weight_kg, age, gender, front_photo_url, side_photo_url, questionnaire) -> dict`

主入口函数，根据是否有照片选择不同路径：

- 有照片 → 调用 `_evaluate_with_photos()`（4次并行）
- 无照片 → 调用 `_evaluate_with_questionnaire()`（1次调用）

返回 `{"exercise": float, "diet": float, "sleep": float, "appearance": float}`

#### `_evaluate_with_photos(height_cm, weight_kg, age, gender, front_photo_url, side_photo_url) -> dict`

使用 `asyncio.gather` 并行调用 4 个维度评分函数：

- `_score_exercise_from_photo(image_messages, body_data)` → 分析体型、肌肉线条
- `_score_diet_from_photo(image_messages, body_data)` → 分析体脂、皮肤光泽
- `_score_sleep_from_photo(image_messages, body_data)` → 分析黑眼圈、肤质、精神状态
- `_score_appearance_from_photo(image_messages, body_data)` → 分析整体形象、气质

每个函数返回 0-100 的 float。如果某个维度调用失败，降级为50分。

#### `_evaluate_with_questionnaire(height_cm, weight_kg, age, gender, questionnaire) -> dict`

单次 API 调用，prompt 包含：
- 身体数据（身高、体重、BMI、年龄、性别）
- 4 个问卷回答
- 要求返回 JSON：`{"exercise": N, "diet": N, "sleep": N, "appearance": N}`

使用 `response_format: {"type": "json_object"}` 确保结构化输出。

### 维度评分 prompt 设计

#### 运动维度（有照片）

```
评估用户的运动能力和体能水平（0-100分）。
分析照片中的：体型、肌肉线条、体态、是否有运动痕迹。
结合身体数据：身高{h}cm，体重{w}kg，BMI {bmi}，{age}岁，{gender}。
评分标准：90-100运动员体格，70-89经常运动，50-69普通，30-49缺乏运动，0-29体能极差。
只返回JSON：{"score": 数字, "reason": "一句话理由"}
```

#### 饮食维度（有照片）

```
评估用户的饮食健康程度（0-100分）。
分析照片中的：体脂率、皮肤光泽、面色、是否有营养不良或过剩迹象。
结合身体数据：身高{h}cm，体重{w}kg，BMI {bmi}，{age}岁，{gender}。
评分标准：90-100非常健康，70-89良好，50-69普通，30-49不健康，0-29严重问题。
只返回JSON：{"score": 数字, "reason": "一句话理由"}
```

#### 睡眠维度（有照片）

```
评估用户的睡眠质量（0-100分）。
分析照片中的：黑眼圈、眼袋、肤质、精神状态、面色。
结合身体数据：身高{h}cm，体重{w}kg，BMI {bmi}，{age}岁，{gender}。
评分标准：90-100精神饱满，70-89状态良好，50-69一般，30-49明显疲惫，0-29严重睡眠不足。
只返回JSON：{"score": 数字, "reason": "一句话理由"}
```

#### 外貌维度（有照片）

```
评估用户的外在形象（0-100分）。
分析照片中的：整体形象、穿着打扮、气质、面部状态。
结合身体数据：身高{h}cm，体重{w}kg，BMI {bmi}，{age}岁，{gender}。
评分标准：90-100形象出众，70-89良好，50-69普通，30-49需要打理，0-29需大幅改善。
只返回JSON：{"score": 数字, "reason": "一句话理由"}
```

### 已移除函数

- `evaluate_initial_score()` → 被 `evaluate_all_scores()` 替代

## 前端变更

### Onboarding.tsx

新增"问卷对话"步骤（当用户跳过照片上传时）：

1. 系统依次发送4个问题（带typing动画，间隔1-2秒）
2. 每个问题后等待用户输入回答
3. 用户回答后系统发送下一个问题
4. 4个问题回答完毕后，显示"开始评估"按钮

问卷步骤插入在"照片上传"和"确认评估"之间。

### Profile.tsx

- 重新评估时，如果有 `questionnaire` 数据，一起发送到 evaluate 接口
- 问卷数据从 profile 接口获取（UserProfile.questionnaire）

## 错误处理

- 单个维度 AI 评分失败 → 降级为50分，不影响其他维度
- 整个评估失败 → 保持现有默认50分逻辑
- 照片URL无效 → 跳过照片分析，降级为问卷模式
- 问卷答案过短或无效 → 该维度给较低分（30-40分）

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/models/user.py` | 修改 | UserProfile 新增 questionnaire JSON 字段 |
| `backend/app/schemas/user.py` | 修改 | EvaluateRequest 新增 questionnaire 字段 |
| `backend/app/services/ai_service.py` | 修改 | 新增 evaluate_all_scores、4个维度评分函数、问卷评分函数 |
| `backend/app/modules/user/router.py` | 修改 | evaluate 端点调用新函数 |
| `backend/alembic/versions/` | 新增 | 数据库迁移脚本 |
| `frontend/src/pages/Onboarding.tsx` | 修改 | 新增问卷对话步骤 |
| `frontend/src/pages/Profile.tsx` | 修改 | 重新评估发送问卷数据 |
