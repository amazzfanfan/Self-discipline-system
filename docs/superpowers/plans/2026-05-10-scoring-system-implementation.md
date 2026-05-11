# 四维评分系统优化实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 优化用户初始化四维评分系统，支持更丰富的图片上传类型，并通过 AI 综合分析实现更智能的评分。

**Architecture:** 
- 后端：FastAPI + SQLAlchemy + face++ API + MiMo AI
- 前端：React + TypeScript + TailwindCSS
- 数据库：PostgreSQL

**Tech Stack:** Python 3.11+, React 19, TypeScript, FastAPI, SQLAlchemy 2.0, face++ API, MiMo AI

---

## Task 1: 更新 UserProfile 模型，新增头像和肖像图字段

**Objective:** 在用户档案模型中新增 avatar_url 和 portrait_photo_url 字段

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/xxxx_add_avatar_portrait_fields.py`

**Step 1: 修改 UserProfile 模型**

```python
# backend/app/models/user.py
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    height_cm = Column(Numeric(5, 1))
    weight_kg = Column(Numeric(5, 1))
    age = Column(Integer)
    gender = Column(SAEnum(GenderEnum))
    body_fat_pct = Column(Numeric(4, 1))
    avatar_url = Column(String(500))           # 新增：头像（仅显示）
    portrait_photo_url = Column(String(500))   # 新增：正面肖像图（旷视分析）
    front_photo_url = Column(String(500))      # 正面图（AI分析体态）
    side_photo_url = Column(String(500))       # 侧面图（AI分析体态）
    ai_profile_score = Column(JSON)
    questionnaire = Column(JSON, nullable=True)
    skin_analysis = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")
```

**Step 2: 生成数据库迁移**

Run: `cd backend && alembic revision --autogenerate -m "add avatar and portrait fields"`

**Step 3: 执行迁移**

Run: `cd backend && alembic upgrade head`

**Step 4: 提交**

```bash
git add backend/app/models/user.py backend/alembic/versions/xxxx_add_avatar_portrait_fields.py
git commit -m "feat: add avatar and portrait fields to UserProfile"
```

---

## Task 2: 更新用户 Schema，支持新字段

**Objective:** 更新 Pydantic schema 以支持新字段

**Files:**
- Modify: `backend/app/schemas/user.py`

**Step 1: 更新 ProfileResponse**

```python
# backend/app/schemas/user.py
class ProfileResponse(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    age: int | None
    gender: str | None
    avatar_url: str | None
    portrait_photo_url: str | None
    front_photo_url: str | None
    side_photo_url: str | None
    questionnaire: dict[str, str] | None
    skin_analysis: dict | None

    class Config:
        from_attributes = True
```

**Step 2: 提交**

```bash
git add backend/app/schemas/user.py
git commit -m "feat: update ProfileResponse schema with new fields"
```

---

## Task 3: 更新图片上传接口，支持四种图片类型

**Objective:** 修改图片上传接口，支持头像、肖像图、正面图、侧面图

**Files:**
- Modify: `backend/app/modules/user/router.py`

**Step 1: 更新上传接口**

```python
# backend/app/modules/user/router.py
@router.post("/me/photos/upload")
async def upload_photos(
    avatar: UploadFile | None = File(None),
    portrait_photo: UploadFile | None = File(None),
    front_photo: UploadFile | None = File(None),
    side_photo: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload photos during onboarding. Returns saved URLs."""
    os.makedirs("uploads", exist_ok=True)
    user_id = user.id
    
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    
    uploaded = {}
    
    # 保存头像
    if avatar:
        ext = os.path.splitext(avatar.filename or "photo.jpg")[1]
        filename = f"{user_id}_avatar_{uuid.uuid4().hex[:8]}{ext}"
        with open(f"uploads/{filename}", "wb") as f:
            f.write(await avatar.read())
        profile.avatar_url = f"/uploads/{filename}"
        uploaded["avatar_url"] = profile.avatar_url
    
    # 保存正面肖像图
    if portrait_photo:
        ext = os.path.splitext(portrait_photo.filename or "photo.jpg")[1]
        filename = f"{user_id}_portrait_{uuid.uuid4().hex[:8]}{ext}"
        with open(f"uploads/{filename}", "wb") as f:
            f.write(await portrait_photo.read())
        profile.portrait_photo_url = f"/uploads/{filename}"
        uploaded["portrait_photo_url"] = profile.portrait_photo_url
    
    # 保存正面图
    if front_photo:
        ext = os.path.splitext(front_photo.filename or "photo.jpg")[1]
        filename = f"{user_id}_front_{uuid.uuid4().hex[:8]}{ext}"
        with open(f"uploads/{filename}", "wb") as f:
            f.write(await front_photo.read())
        profile.front_photo_url = f"/uploads/{filename}"
        uploaded["front_photo_url"] = profile.front_photo_url
    
    # 保存侧面图
    if side_photo:
        ext = os.path.splitext(side_photo.filename or "photo.jpg")[1]
        filename = f"{user_id}_side_{uuid.uuid4().hex[:8]}{ext}"
        with open(f"uploads/{filename}", "wb") as f:
            f.write(await side_photo.read())
        profile.side_photo_url = f"/uploads/{filename}"
        uploaded["side_photo_url"] = profile.side_photo_url
    
    await db.flush()
    return uploaded
```

**Step 2: 提交**

```bash
git add backend/app/modules/user/router.py
git commit -m "feat: update photo upload to support 4 types"
```

---

## Task 4: 重写 evaluate_all_scores 函数

**Objective:** 实现新的评分逻辑：综合模式（图片+旷视）和问卷模式

**Files:**
- Modify: `backend/app/services/ai_service.py`

**Step 1: 添加新的评分 prompt**

```python
# backend/app/services/ai_service.py

# 综合评分模式 prompt
COMPREHENSIVE_PROMPT = """你是一个专业的健康评估AI。请根据以下信息，为用户评估四个维度的初始分数（0-100分）。

【身体数据】
- 身高：{height}cm
- 体重：{weight}kg
- BMI：{bmi:.1f}（{bmi_label}）
- 年龄：{age}岁
- 性别：{gender_cn}

{skin_info}

【评分标准】
- 运动维度：BMI>25属于超重，运动评分应偏低；体态显示缺乏运动则更低
- 饮食维度：BMI>25说明饮食可能不健康，评分应偏低
- 睡眠维度：有黑眼圈、眼袋、疲惫迹象说明睡眠不足，评分应偏低
- 外貌维度：肤质差、形象不整洁则评分偏低

请根据图片和数据综合判断，返回JSON：
{{"exercise": 分数, "diet": 分数, "sleep": 分数, "appearance": 分数}}"""

# 问卷评分模式 prompt
QUESTIONNAIRE_PROMPT = """你是一个专业的健康评估AI。请根据以下信息，为用户评估四个维度的初始分数（0-100分）。

【身体数据】
- 身高：{height}cm
- 体重：{weight}kg
- BMI：{bmi:.1f}（{bmi_label}）
- 年龄：{age}岁
- 性别：{gender_cn}

【用户自述】
- 运动：{exercise_answer}
- 饮食：{diet_answer}
- 睡眠：{sleep_answer}
- 外貌：{appearance_answer}

【评分标准】
- 根据用户自述内容合理评估，回答越详细、习惯越好，分数越高
- BMI>25属于超重，运动/饮食评分应适当偏低

请返回JSON：
{{"exercise": 分数, "diet": 分数, "sleep": 分数, "appearance": 分数}}"""
```

**Step 2: 实现综合评分函数**

```python
async def _evaluate_comprehensive(
    height_cm: float, weight_kg: float, age: int, gender: str,
    portrait_photo_url: str | None = None,
    front_photo_url: str | None = None,
    side_photo_url: str | None = None,
    skin_analysis: dict | None = None,
) -> dict[str, float]:
    """综合评分模式：图片 + 旷视结果 + 身体数据"""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")
    
    # 构建肤质信息
    skin_info = ""
    if skin_analysis:
        skin_info = f"""【肤质分析结果】
- 皮肤类型：{skin_analysis.get('skin_type_name', '未知')}
- 肤质评分：{skin_analysis.get('skin_score', 0)}/100
- 存在问题：{', '.join(skin_analysis.get('issues', ['无']))}"""
    
    prompt = COMPREHENSIVE_PROMPT.format(
        height=height_cm, weight=weight_kg, bmi=bmi,
        bmi_label="偏瘦" if bmi < 18.5 else "正常" if bmi < 24 else "偏胖" if bmi < 28 else "肥胖",
        age=age, gender_cn=gender_cn, skin_info=skin_info
    )
    
    # 构建图片消息
    messages = [{"role": "user", "content": []}]
    
    # 添加肖像图（用于肤质参考）
    if portrait_photo_url:
        b64_url = _image_path_to_base64(portrait_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    
    # 添加正面图（用于体态分析）
    if front_photo_url:
        b64_url = _image_path_to_base64(front_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    
    # 添加侧面图（用于体态分析）
    if side_photo_url:
        b64_url = _image_path_to_base64(side_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    
    messages[0]["content"].append({"type": "text", "text": prompt})
    
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": messages,
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
            print(f"[四维评分] 综合评分成功: {result}")
            return result
    except Exception as e:
        print(f"[四维评分] 综合评分失败: {e}")
        raise
```

**Step 3: 更新 evaluate_all_scores 主函数**

```python
async def evaluate_all_scores(
    height_cm: float, weight_kg: float, age: int, gender: str,
    portrait_photo_url: str | None = None,
    front_photo_url: str | None = None,
    side_photo_url: str | None = None,
    skin_analysis: dict | None = None,
    questionnaire: dict[str, str] | None = None,
) -> tuple[dict[str, float], str]:
    """Main entry: evaluate all 4 dimension scores.
    
    Returns: (scores_dict, eval_mode)
    - eval_mode: "photo" or "questionnaire"
    """
    # 有评估图片（肖像图/正面图/侧面图）时使用综合评分模式
    has_eval_photo = portrait_photo_url or front_photo_url or side_photo_url
    
    if has_eval_photo:
        print("[四维评分] 使用综合评分模式（图片+旷视+身体数据）")
        try:
            scores = await _evaluate_comprehensive(
                height_cm, weight_kg, age, gender,
                portrait_photo_url, front_photo_url, side_photo_url,
                skin_analysis
            )
            return scores, "photo"
        except Exception as e:
            print(f"[四维评分] 综合评分失败，尝试问卷模式: {e}")
    
    # 无图片或综合评分失败时使用问卷模式
    if questionnaire:
        print("[四维评分] 使用问卷模式")
        scores = await _evaluate_with_questionnaire(height_cm, weight_kg, age, gender, questionnaire)
        return scores, "questionnaire"
    
    # 都没有时使用默认分数
    print("[四维评分] 无图片无问卷，使用默认分数")
    return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}, "default"
```

**Step 4: 提交**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: rewrite evaluate_all_scores with comprehensive mode"
```

---

## Task 5: 更新评估接口，集成新评分逻辑

**Objective:** 更新用户评估接口，使用新的评分逻辑

**Files:**
- Modify: `backend/app/modules/user/router.py`

**Step 1: 更新 evaluate 接口**

```python
# backend/app/modules/user/router.py
@router.post("/me/evaluate")
async def evaluate(
    req: EvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id

    # Update profile
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id, height_cm=req.height_cm, weight_kg=req.weight_kg, age=req.age, gender=req.gender)
        db.add(profile)
    else:
        profile.height_cm = req.height_cm
        profile.weight_kg = req.weight_kg
        profile.age = req.age
        profile.gender = req.gender

    # Save questionnaire if provided
    if req.questionnaire:
        profile.questionnaire = req.questionnaire

    # 判断是否有评估图片
    has_eval_photo = profile.portrait_photo_url or profile.front_photo_url or profile.side_photo_url
    
    # 肤质分析（如果有肖像图或正面图）
    skin_result = None
    skin_source = "none"
    photo_for_skin = profile.portrait_photo_url or profile.front_photo_url
    
    if photo_for_skin:
        try:
            skin_result = await analyze_skin(photo_for_skin.lstrip('/'))
            skin_source = skin_result.source
            
            # 存储肤质分析结果
            profile.skin_analysis = {
                "source": skin_result.source,
                "skin_type": skin_result.skin_type,
                "skin_type_name": skin_result.skin_type_name,
                "skin_score": skin_result.skin_score,
                "issues": skin_result.issues,
                "suggestions": skin_result.suggestions,
            }
            
            from app.services.faceplus_service import get_source_display
            print(f"[评估] 肤质分析成功 ({get_source_display(skin_result.source)}): {skin_result.skin_type_name}, 评分: {skin_result.skin_score}")
        except Exception as e:
            print(f"[评估] 肤质分析异常: {e}")

    # AI 综合评分
    try:
        scores, eval_mode = await evaluate_all_scores(
            float(req.height_cm), float(req.weight_kg), req.age, req.gender,
            portrait_photo_url=profile.portrait_photo_url,
            front_photo_url=profile.front_photo_url,
            side_photo_url=profile.side_photo_url,
            skin_analysis=profile.skin_analysis,
            questionnaire=req.questionnaire,
        )
    except Exception as e:
        print(f"[评估] evaluate_all_scores 异常，使用默认分数: {e}")
        scores = {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}
        eval_mode = "default"

    # Update user_scores
    result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    db_scores = {s.dimension: s for s in result.scalars().all()}
    for dim in DimensionEnum:
        if dim.value in db_scores:
            db_scores[dim.value].score = scores[dim.value]
        else:
            db.add(UserScore(user_id=user_id, dimension=dim, score=scores[dim.value]))

    await db.flush()

    # Generate first-login analysis message
    # ... (保持原有逻辑)

    return {
        "message": "evaluation complete",
        "scores": scores,
        "skin_analysis": profile.skin_analysis,
        "skin_source": skin_source,
        "eval_mode": eval_mode,
    }
```

**Step 2: 提交**

```bash
git add backend/app/modules/user/router.py
git commit -m "feat: update evaluate endpoint with new scoring logic"
```

---

## Task 6: 更新前端 Onboarding 页面，支持四种图片上传

**Objective:** 修改前端 Onboarding 页面，支持头像、肖像图、正面图、侧面图上传

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`

**Step 1: 更新状态变量**

```typescript
// frontend/src/pages/Onboarding.tsx
const [avatar, setAvatar] = useState<File | null>(null);
const [portraitPhoto, setPortraitPhoto] = useState<File | null>(null);
const [frontPhoto, setFrontPhoto] = useState<File | null>(null);
const [sidePhoto, setSidePhoto] = useState<File | null>(null);
const [avatarPreview, setAvatarPreview] = useState('');
const [portraitPreview, setPortraitPreview] = useState('');
const [frontPreview, setFrontPreview] = useState('');
const [sidePreview, setSidePreview] = useState('');
```

**Step 2: 更新图片上传步骤**

```typescript
// Step 2: Photo upload
<motion.div key="photos" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
  <h2 className="text-xl font-bold text-white mb-2">上传照片</h2>
  <p className="text-slate-400 text-sm mb-6">
    上传照片可以帮助系统更准确地评估你的状态。所有照片都是可选的。
  </p>
  
  {/* 头像 */}
  <div className="mb-4">
    <label className="text-slate-300 text-sm mb-2 block">头像（仅用于显示）</label>
    {/* 上传组件 */}
  </div>
  
  {/* 正面肖像图 */}
  <div className="mb-4">
    <label className="text-slate-300 text-sm mb-2 block">正面肖像图（用于肤质分析）</label>
    <p className="text-slate-500 text-xs mb-2">请上传清晰的面部特写照片</p>
    {/* 上传组件 */}
  </div>
  
  {/* 正面图 */}
  <div className="mb-4">
    <label className="text-slate-300 text-sm mb-2 block">正面图（用于体态分析）</label>
    <p className="text-slate-500 text-xs mb-2">请上传全身或半身正面照片</p>
    {/* 上传组件 */}
  </div>
  
  {/* 侧面图 */}
  <div className="mb-4">
    <label className="text-slate-300 text-sm mb-2 block">侧面图（用于体态分析）</label>
    <p className="text-slate-500 text-xs mb-2">请上传全身侧面照片</p>
    {/* 上传组件 */}
  </div>
  
  <p className="text-slate-500 text-xs">
    如果不上传评估照片（肖像图/正面图/侧面图），系统将以问卷形式进行评估。
  </p>
</motion.div>
```

**Step 3: 更新上传逻辑**

```typescript
const handleSubmit = async () => {
  setEvaluating(true);
  setEvalStep(0);
  setEvalError('');
  try {
    // 上传照片
    const formData = new FormData();
    if (avatar) formData.append('avatar', avatar);
    if (portraitPhoto) formData.append('portrait_photo', portraitPhoto);
    if (frontPhoto) formData.append('front_photo', frontPhoto);
    if (sidePhoto) formData.append('side_photo', sidePhoto);
    
    if (avatar || portraitPhoto || frontPhoto || sidePhoto) {
      await api.post('/users/me/photos/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    }
    
    // 判断是否需要问卷
    const hasEvalPhoto = portraitPhoto || frontPhoto || sidePhoto;
    
    if (!hasEvalPhoto) {
      // 没有评估图片，显示问卷
      setStep(3); // 跳转到问卷步骤
      setEvaluating(false);
      return;
    }
    
    // 有评估图片，直接评估
    setEvalStep(1);
    await api.post('/users/me/evaluate', {
      height_cm: parseFloat(height),
      weight_kg: parseFloat(weight),
      age: parseInt(age),
      gender,
      questionnaire: Object.keys(questionnaire).length > 0 ? questionnaire : undefined,
    });
    setEvalStep(3);
    setTimeout(() => navigate('/'), 1200);
  } catch {
    setEvalError('评估失败，请重试');
    setEvaluating(false);
  }
};
```

**Step 4: 提交**

```bash
git add frontend/src/pages/Onboarding.tsx
git commit -m "feat: update Onboarding with 4 photo types"
```

---

## Task 7: 更新加载动画，显示分析方式

**Objective:** 在评估过程中显示当前使用的分析方式

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`

**Step 1: 添加分析方式状态**

```typescript
const [evalMode, setEvalMode] = useState<string>('');
```

**Step 2: 更新加载动画显示**

```typescript
{isAnalyzing && (
  <motion.div key="analyzing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
    className="flex gap-3">
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center text-sm flex-shrink-0">
      🔍
    </div>
    <div className="bg-slate-800/80 border border-slate-700/50 rounded-2xl rounded-bl-sm px-4 py-3">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        <span className="text-sm text-slate-400 ml-1">
          {evalMode === 'photo' ? '正在使用 AI综合分析...' : 
           evalMode === 'questionnaire' ? '正在使用 问卷评估...' : 
           '正在评估...'}
        </span>
      </div>
    </div>
  </motion.div>
)}
```

**Step 3: 提交**

```bash
git add frontend/src/pages/Onboarding.tsx
git commit -m "feat: show evaluation mode in loading animation"
```

---

## Task 8: 测试和验证

**Objective:** 测试完整流程，确保所有功能正常工作

**Files:**
- None (testing only)

**Step 1: 启动后端服务**

Run: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000`

**Step 2: 启动前端服务**

Run: `cd frontend && npm run dev`

**Step 3: 测试场景**

1. **场景1：上传所有图片**
   - 注册新账号
   - 上传头像、肖像图、正面图、侧面图
   - 完成评估
   - 验证：使用综合评分模式，肤质分析正常

2. **场景2：只上传部分图片**
   - 注册新账号
   - 只上传正面图
   - 完成评估
   - 验证：使用综合评分模式，无肤质分析

3. **场景3：不上传图片**
   - 注册新账号
   - 不上传任何图片
   - 填写问卷
   - 完成评估
   - 验证：使用问卷评分模式

4. **场景4：降级测试**
   - 模拟 face++ API 不可用
   - 验证：降级到系统 AI 或保底规则

**Step 4: 提交最终版本**

```bash
git add .
git commit -m "feat: complete scoring system optimization"
git tag -a v5.0 -m "v5.0: 四维评分系统优化"
git push origin master --tags
```

---

## 完成

实现计划已完成。所有任务都是 bite-sized（2-5分钟），包含完整的代码和验证步骤。

**执行顺序：** Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8
