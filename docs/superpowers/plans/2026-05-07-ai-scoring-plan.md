# AI 四维评分系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户初始评分从"外貌AI评分+其余固定50分"升级为AI根据照片或问卷独立评估四个维度。

**Architecture:** 有照片时4个维度并行AI调用（asyncio.gather），无照片时用对话式问卷+身体数据单次AI调用。新增 `evaluate_all_scores()` 替代原有 `evaluate_initial_score()`。

**Tech Stack:** FastAPI, SQLAlchemy async, httpx, asyncio.gather, React, TypeScript, TailwindCSS, Alembic

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/models/user.py` | UserProfile 新增 `questionnaire` JSON 字段 |
| `backend/app/schemas/user.py` | EvaluateRequest/ProfileResponse 新增 questionnaire |
| `backend/app/services/ai_service.py` | 新增 `evaluate_all_scores()`, 4个维度评分函数, 问卷评分函数 |
| `backend/app/modules/user/router.py` | evaluate 端点调用新函数 |
| `backend/alembic/versions/xxx_add_questionnaire.py` | 数据库迁移 |
| `frontend/src/pages/Onboarding.tsx` | 新增问卷对话步骤 |
| `frontend/src/pages/Profile.tsx` | 重新评估发送 questionnaire |

---

### Task 1: 数据库迁移 — UserProfile 新增 questionnaire 字段

**Files:**
- Modify: `backend/app/models/user.py:32-47`
- Create: `backend/alembic/versions/add_questionnaire_field.py`

- [ ] **Step 1: 修改 UserProfile 模型**

在 `backend/app/models/user.py` 的 `UserProfile` 类中，`ai_profile_score` 字段之后新增：

```python
questionnaire = Column(JSON, nullable=True)
```

完整 `UserProfile` 类应为：

```python
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    height_cm = Column(Numeric(5, 1))
    weight_kg = Column(Numeric(5, 1))
    age = Column(Integer)
    gender = Column(SAEnum(GenderEnum))
    body_fat_pct = Column(Numeric(4, 1))
    front_photo_url = Column(String(500))
    side_photo_url = Column(String(500))
    ai_profile_score = Column(JSON)
    questionnaire = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")
```

- [ ] **Step 2: 生成迁移脚本**

Run: `cd E:/agent/xitong/backend && py -m alembic revision --autogenerate -m "add_questionnaire_to_user_profiles"`

Expected: 在 `backend/alembic/versions/` 下生成新迁移文件。

- [ ] **Step 3: 执行迁移**

Run: `cd E:/agent/xitong/backend && py -m alembic upgrade head`

Expected: `Running upgrade ... OK`

- [ ] **Step 4: 验证字段存在**

Run:
```bash
cd E:/agent/xitong/backend && py -c "
from app.core.database import engine
import asyncio
from sqlalchemy import text
async def check():
    async with engine.connect() as conn:
        r = await conn.execute(text(\"SELECT questionnaire FROM user_profiles LIMIT 1\"))
        print('questionnaire column exists')
asyncio.run(check())
"
```

Expected: `questionnaire column exists`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/
git commit -m "feat: add questionnaire JSON field to UserProfile"
```

---

### Task 2: 更新 API Schema

**Files:**
- Modify: `backend/app/schemas/user.py`

- [ ] **Step 1: 更新 EvaluateRequest**

将 `EvaluateRequest` 改为：

```python
class EvaluateRequest(BaseModel):
    height_cm: float
    weight_kg: float
    age: int
    gender: str
    questionnaire: dict[str, str] | None = None
```

- [ ] **Step 2: 更新 ProfileResponse**

将 `ProfileResponse` 改为：

```python
class ProfileResponse(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    age: int | None
    gender: str | None
    front_photo_url: str | None
    side_photo_url: str | None
    questionnaire: dict[str, str] | None

    class Config:
        from_attributes = True
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/user.py
git commit -m "feat: add questionnaire to EvaluateRequest and ProfileResponse schemas"
```

---

### Task 3: AI 服务 — 四维评分核心函数

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: 添加 asyncio import**

在文件顶部 import 区域添加：

```python
import asyncio
```

- [ ] **Step 2: 添加维度评分 prompt 常量**

在 `TASK_DEFAULTS` 之前添加：

```python
# --- Dimension scoring prompts (for photo-based evaluation) ---

DIMENSION_PROMPTS = {
    "exercise": (
        "评估用户的运动能力和体能水平（0-100分）。\n"
        "分析照片中的：体型、肌肉线条、体态、是否有运动痕迹。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100运动员体格，70-89经常运动，50-69普通，30-49缺乏运动，0-29体能极差。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "diet": (
        "评估用户的饮食健康程度（0-100分）。\n"
        "分析照片中的：体脂率、皮肤光泽、面色、是否有营养不良或过剩迹象。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100非常健康，70-89良好，50-69普通，30-49不健康，0-29严重问题。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "sleep": (
        "评估用户的睡眠质量（0-100分）。\n"
        "分析照片中的：黑眼圈、眼袋、肤质、精神状态、面色。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100精神饱满，70-89状态良好，50-69一般，30-49明显疲惫，0-29严重睡眠不足。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "appearance": (
        "评估用户的外在形象（0-100分）。\n"
        "分析照片中的：整体形象、穿着打扮、气质、面部状态。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100形象出众，70-89良好，50-69普通，30-49需要打理，0-29需大幅改善。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
}
```

- [ ] **Step 3: 添加 `_score_dimension_from_photo` 函数**

在 `evaluate_initial_score` 函数之前添加：

```python
async def _score_dimension_from_photo(
    dimension: str,
    image_messages: list[dict],
    height_cm: float, weight_kg: float, age: int, gender: str,
) -> float:
    """Score a single dimension from photo analysis. Returns 0-100."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = DIMENSION_PROMPTS[dimension].format(
        height=height_cm, weight=weight_kg, bmi=bmi, age=age, gender_cn=gender_cn
    )

    messages = [{"role": "user", "content": image_messages + [{"type": "text", "text": prompt}]}]

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": settings.analysis_model, "messages": messages, "max_tokens": 200, "response_format": {"type": "json_object"}},
            )
            data = response.json()
            content = _extract_content(data)
            parsed = json.loads(content)
            score = float(parsed.get("score", 50))
            print(f"[四维评分] {dimension} 照片评分: {score}")
            return min(100, max(0, score))
    except Exception as e:
        print(f"[四维评分] {dimension} 照片评分失败: {e}")
        return 50.0
```

- [ ] **Step 4: 添加 `_evaluate_with_photos` 函数**

```python
async def _evaluate_with_photos(
    height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None, side_photo_url: str | None,
) -> dict[str, float]:
    """Evaluate all 4 dimensions in parallel using photo analysis."""
    # Build image message parts
    image_parts = []
    if front_photo_url:
        image_parts.append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{front_photo_url}"}})
    if side_photo_url:
        image_parts.append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{side_photo_url}"}})

    # Run 4 dimension evaluations in parallel
    results = await asyncio.gather(
        _score_dimension_from_photo("exercise", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("diet", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("sleep", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("appearance", image_parts, height_cm, weight_kg, age, gender),
    )

    return {
        "exercise": results[0],
        "diet": results[1],
        "sleep": results[2],
        "appearance": results[3],
    }
```

- [ ] **Step 5: 添加 `_evaluate_with_questionnaire` 函数**

```python
QUESTIONNAIRE_PROMPT = """评估用户四个维度的初始评分（0-100分）。

身体数据：
- 身高：{height}cm
- 体重：{weight}kg
- BMI：{bmi:.1f}
- 年龄：{age}岁
- 性别：{gender_cn}

用户自述：
- 运动：{exercise_answer}
- 饮食：{diet_answer}
- 睡眠：{sleep_answer}
- 外貌：{appearance_answer}

评分标准：90-100优秀，70-89良好，50-69普通，30-49需改善，0-29需大幅改善。
请根据用户自述内容合理评估，不要全部给50分。回答越详细、习惯越好，分数越高。

只返回JSON：{{"exercise": 数字, "diet": 数字, "sleep": 数字, "appearance": 数字}}"""


async def _evaluate_with_questionnaire(
    height_cm: float, weight_kg: float, age: int, gender: str,
    questionnaire: dict[str, str],
) -> dict[str, float]:
    """Evaluate all 4 dimensions using questionnaire + body data."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = QUESTIONNAIRE_PROMPT.format(
        height=height_cm, weight=weight_kg, bmi=bmi, age=age, gender_cn=gender_cn,
        exercise_answer=questionnaire.get("exercise", "未回答"),
        diet_answer=questionnaire.get("diet", "未回答"),
        sleep_answer=questionnaire.get("sleep", "未回答"),
        appearance_answer=questionnaire.get("appearance", "未回答"),
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
            )
            data = response.json()
            content = _extract_content(data)
            parsed = json.loads(content)
            result = {
                "exercise": min(100, max(0, float(parsed.get("exercise", 50)))),
                "diet": min(100, max(0, float(parsed.get("diet", 50)))),
                "sleep": min(100, max(0, float(parsed.get("sleep", 50)))),
                "appearance": min(100, max(0, float(parsed.get("appearance", 50)))),
            }
            print(f"[四维评分] 问卷评分成功: {result}")
            return result
    except Exception as e:
        print(f"[四维评分] 问卷评分失败: {e}")
        return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}
```

- [ ] **Step 6: 添加主入口 `evaluate_all_scores` 函数**

```python
async def evaluate_all_scores(
    height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None = None, side_photo_url: str | None = None,
    questionnaire: dict[str, str] | None = None,
) -> dict[str, float]:
    """Main entry: evaluate all 4 dimension scores.

    - With photos: 4 parallel AI calls, each analyzing the photo for its dimension.
    - Without photos: single AI call with questionnaire + body data.
    - Fallback: returns 50 for all dimensions.
    """
    if front_photo_url:
        print("[四维评分] 使用照片模式（4次并行调用）")
        return await _evaluate_with_photos(height_cm, weight_kg, age, gender, front_photo_url, side_photo_url)

    if questionnaire:
        print("[四维评分] 使用问卷模式（单次调用）")
        return await _evaluate_with_questionnaire(height_cm, weight_kg, age, gender, questionnaire)

    print("[四维评分] 无照片无问卷，使用默认分数")
    return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: add evaluate_all_scores with photo and questionnaire modes"
```

---

### Task 4: 更新 evaluate 端点

**Files:**
- Modify: `backend/app/modules/user/router.py:1-180`

- [ ] **Step 1: 更新 import 语句**

将第12行的 import 改为：

```python
from app.services.ai_service import evaluate_all_scores, generate_appearance_analysis, generate_body_analysis
```

移除 `evaluate_initial_score` 和 `analyze_image`。

- [ ] **Step 2: 重写 evaluate 端点的核心逻辑**

将 `evaluate` 函数中的评分逻辑（第128-141行）替换为：

```python
    # Save questionnaire if provided
    if req.questionnaire:
        profile.questionnaire = req.questionnaire

    # AI-evaluate all four dimensions
    scores = await evaluate_all_scores(
        float(req.height_cm), float(req.weight_kg), req.age, req.gender,
        front_photo_url=profile.front_photo_url,
        side_photo_url=profile.side_photo_url,
        questionnaire=req.questionnaire,
    )
```

同时更新 `generate_appearance_analysis` 调用中的参数，保持不变（它已经接收 photo_url）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/user/router.py
git commit -m "feat: update evaluate endpoint to use evaluate_all_scores"
```

---

### Task 5: 前端 — Onboarding 问卷对话步骤

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`

- [ ] **Step 1: 添加问卷状态和问题定义**

在 `Onboarding` 组件的 state 声明区域（第23行附近）新增：

```typescript
const [questionnaire, setQuestionnaire] = useState<Record<string, string>>({});
const [questionStep, setQuestionStep] = useState(0);
const [currentAnswer, setCurrentAnswer] = useState('');

const QUESTIONS = [
  { key: 'exercise', text: '你每周运动几次，一次运动多长时间？' },
  { key: 'diet', text: '你的饮食规律如何？' },
  { key: 'sleep', text: '你通常几点睡觉，每次睡几个小时？' },
  { key: 'appearance', text: '你平常是否有注意打理自己，你对自己的外在形象满意吗？' },
];
```

- [ ] **Step 2: 修改步骤流程**

将 `onboardingSteps` 数组从4个步骤改为：

- Step 0: Welcome（不变）
- Step 1: Basic info（不变，下一步改为 `setStep(frontPhoto ? 3 : 2)` 即有照片跳到确认）
- Step 2: **问卷对话**（新增，仅无照片时显示）
- Step 3: Photo upload（移到 step 3，"下一步"改为 `setStep(frontPhoto ? 4 : 2)`）
- Step 4: Confirm & evaluate（原 step 3）

实际上更简单的做法：保持 step 0-2 不变，step 2 的"下一步"按钮改为：
- 有照片 → `setStep(3)`（确认页）
- 无照片 → `setStep(2.5)` 即问卷页

但由于 step 是整数，重新编号：
- Step 0: Welcome
- Step 1: Basic info → "下一步" `setStep(2)`
- Step 2: Photo upload → 有照片"下一步" `setStep(4)`，无照片"下一步" `setStep(3)`
- Step 3: **Questionnaire**（新增）
- Step 4: Confirm & evaluate

进度点从 `[0,1,2,3]` 改为 `[0,1,2,3,4]`。

- [ ] **Step 3: 编写问卷对话步骤 UI**

在 `onboardingSteps` 数组中，step 2（Photo upload）之后插入新步骤：

```tsx
// Step 3: Questionnaire (shown when no photo)
<motion.div key="questionnaire" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
  <h2 className="text-xl font-bold text-white mb-2">回答几个问题</h2>
  <p className="text-slate-400 text-sm mb-6">
    你没有上传照片，系统将通过以下问题来评估你的四维度初始评分。
  </p>

  {/* Already answered questions */}
  <div className="space-y-3 mb-4">
    {QUESTIONS.slice(0, questionStep).map((q, i) => (
      <div key={q.key} className="bg-slate-800 rounded-lg p-3">
        <div className="text-blue-400 text-xs mb-1">系统：{q.text}</div>
        <div className="text-white text-sm">{questionnaire[q.key]}</div>
      </div>
    ))}
  </div>

  {/* Current question */}
  {questionStep < QUESTIONS.length && (
    <div className="space-y-3">
      <div className="bg-slate-800 rounded-lg p-3">
        <div className="text-blue-400 text-xs mb-1">系统：</div>
        <div className="text-white text-sm">{QUESTIONS[questionStep].text}</div>
      </div>
      <div className="flex gap-2">
        <input
          value={currentAnswer}
          onChange={(e) => setCurrentAnswer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && currentAnswer.trim()) {
              const q = QUESTIONS[questionStep];
              setQuestionnaire({ ...questionnaire, [q.key]: currentAnswer.trim() });
              setCurrentAnswer('');
              setQuestionStep(questionStep + 1);
            }
          }}
          placeholder="输入你的回答..."
          className="flex-1 px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => {
            const q = QUESTIONS[questionStep];
            setQuestionnaire({ ...questionnaire, [q.key]: currentAnswer.trim() });
            setCurrentAnswer('');
            setQuestionStep(questionStep + 1);
          }}
          disabled={!currentAnswer.trim()}
          className="px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-lg text-sm transition-colors"
        >
          发送
        </button>
      </div>
    </div>
  )}

  {/* All questions answered */}
  {questionStep >= QUESTIONS.length && (
    <div className="text-center">
      <p className="text-emerald-400 text-sm mb-4">所有问题已回答完毕！</p>
      <button onClick={() => setStep(4)}
        className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
        下一步
      </button>
    </div>
  )}

  <div className="flex gap-3 mt-4">
    <button onClick={() => { setStep(2); setQuestionStep(0); setQuestionnaire({}); }}
      className="flex-1 py-3 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors">
      返回
    </button>
  </div>
</motion.div>,
```

- [ ] **Step 4: 修改 handleSubmit 传递 questionnaire**

在 `handleSubmit` 函数中，evaluate 请求改为：

```typescript
await api.post('/users/me/evaluate', {
  height_cm: parseFloat(height),
  weight_kg: parseFloat(weight),
  age: parseInt(age),
  gender,
  questionnaire: Object.keys(questionnaire).length > 0 ? questionnaire : undefined,
});
```

- [ ] **Step 5: 修改进度点和步骤映射**

将进度点从 `[0,1,2,3]` 改为动态显示：
- 有照片时显示 4 个点（跳过问卷步骤）
- 无照片时显示 5 个点

```typescript
const totalSteps = frontPhoto ? 4 : 5;
```

进度点渲染改为：

```tsx
{Array.from({ length: totalSteps }, (_, i) => (
  <div key={i} className={`w-2 h-2 rounded-full transition-colors ${i <= step ? 'bg-blue-500' : 'bg-slate-700'}`} />
))}
```

- [ ] **Step 6: 修改确认页的评分说明**

确认页（原 step 3，现 step 4）的说明文字改为：

```tsx
<p className="text-slate-500 text-sm mb-6">
  {frontPhoto
    ? 'AI将通过分析你的照片，独立评估运动、饮食、睡眠、外貌四个维度的初始评分。'
    : 'AI将根据你的身体数据和问卷回答，评估四维度初始评分。'}
</p>
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx
git commit -m "feat: add questionnaire conversation step to onboarding for no-photo users"
```

---

### Task 6: 前端 — Profile 重新评估传递 questionnaire

**Files:**
- Modify: `frontend/src/pages/Profile.tsx`

- [ ] **Step 1: 修改 evaluateMutation 传递 questionnaire**

将第35-47行的 `evaluateMutation` 改为：

```typescript
const evaluateMutation = useMutation({
  mutationFn: () => api.post('/users/me/evaluate', {
    height_cm: parseFloat(form.height_cm),
    weight_kg: parseFloat(form.weight_kg),
    age: parseInt(form.age),
    gender: form.gender,
    questionnaire: profile?.questionnaire || undefined,
  }),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['scores'] });
    queryClient.invalidateQueries({ queryKey: ['profile'] });
    alert('AI评估完成，四维度分数已更新');
  },
});
```

- [ ] **Step 2: 更新重新评估说明文字**

将第216-217行的说明文字改为：

```tsx
<p className="text-slate-500 text-sm mb-4">
  更新身体数据或更换照片后，可让AI重新评估你的四维度评分。
  {profile?.front_photo_url
    ? '将通过照片分析评估运动、饮食、睡眠、外貌四个维度。'
    : profile?.questionnaire
    ? '将根据身体数据和问卷回答评估四维度评分。'
    : '请先上传照片或填写问卷。'}
</p>
```

- [ ] **Step 3: 更新状态提示**

将第224-235行的状态提示改为：

```tsx
{profile?.front_photo_url && (
  <span className="text-emerald-500/60 text-xs flex items-center gap-1">
    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
    已上传照片，四维度将被AI评估
  </span>
)}
{!profile?.front_photo_url && profile?.questionnaire && (
  <span className="text-blue-500/60 text-xs flex items-center gap-1">
    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
    已填写问卷，四维度将被AI评估
  </span>
)}
{!profile?.front_photo_url && !profile?.questionnaire && (
  <span className="text-amber-500/60 text-xs flex items-center gap-1">
    <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
    未上传照片/问卷，评分默认50分
  </span>
)}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Profile.tsx
git commit -m "feat: pass questionnaire data on profile re-evaluation"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 启动后端，检查无错误**

Run: `cd E:/agent/xitong/backend && py -m uvicorn app.main:app --reload --port 8000`

Expected: 无 import 错误，服务正常启动。

- [ ] **Step 2: 测试有照片评估**

用已有照片的用户调用 evaluate 接口，验证返回四维分数且不再全部为50：

```bash
curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"test@test.com","password":"123456"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

用获取的 token 测试：
```bash
curl -s -X POST http://localhost:8000/api/users/me/evaluate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"height_cm":175,"weight_kg":70,"age":25,"gender":"male"}'
```

Expected: 返回的 `scores` 中四个维度分数各不相同（不再全部为50）。

- [ ] **Step 3: 测试无照片+问卷评估**

```bash
curl -s -X POST http://localhost:8000/api/users/me/evaluate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"height_cm":170,"weight_kg":65,"age":28,"gender":"female","questionnaire":{"exercise":"每周跑步3次，每次30分钟","diet":"三餐规律，很少吃夜宵","sleep":"通常11点睡，睡7个小时","appearance":"基本每天护肤"}}'
```

Expected: 四维度分数根据问卷内容合理评估，不会全部为50。

- [ ] **Step 4: 测试无照片无问卷（降级）**

```bash
curl -s -X POST http://localhost:8000/api/users/me/evaluate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"height_cm":170,"weight_kg":65,"age":28,"gender":"female"}'
```

Expected: 四维度全部为50（降级到默认值）。

- [ ] **Step 5: 前端验证 — 无照片用户走问卷流程**

打开 http://localhost:5174，注册新账号，跳过照片上传，验证出现问卷对话步骤，回答问题后评估完成。
