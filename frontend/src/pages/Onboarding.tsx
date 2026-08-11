import { useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';

import { useNotification } from '../components/notification-context';
import api from '../services/api';

type PhotoType = 'avatar' | 'portrait' | 'front' | 'side';
type EvalStage = 'upload' | 'assess' | 'done';

interface QuestionOption {
  value: string;
  label: string;
}

interface Question {
  key: string;
  label: string;
  hint: string;
  options: QuestionOption[];
}

interface QuestionGroup {
  dimension: string;
  title: string;
  icon: string;
  accent: string;
  questions: Question[];
}

const QUESTION_GROUPS: QuestionGroup[] = [
  {
    dimension: 'exercise',
    title: '运动状态',
    icon: '🏃',
    accent: 'from-blue-500/20 to-cyan-500/10 border-blue-400/20',
    questions: [
      {
        key: 'exercise_days',
        label: '你每周通常有几天会主动运动？',
        hint: '快走、跑步、力量训练、球类等都可以计算。',
        options: [
          { value: 'none', label: '几乎不运动' },
          { value: '1_2', label: '1–2 天' },
          { value: '3_4', label: '3–4 天' },
          { value: '5_plus', label: '5 天及以上' },
        ],
      },
      {
        key: 'exercise_duration',
        label: '每次运动通常持续多久？',
        hint: '按最近一个月的常见情况选择。',
        options: [
          { value: 'under_20', label: '少于 20 分钟' },
          { value: '20_40', label: '20–40 分钟' },
          { value: '40_60', label: '40–60 分钟' },
          { value: 'over_60', label: '60 分钟以上' },
        ],
      },
      {
        key: 'sedentary_hours',
        label: '你每天大约久坐多长时间？',
        hint: '包括学习、办公、刷手机和通勤。',
        options: [
          { value: 'under_4', label: '少于 4 小时' },
          { value: '4_6', label: '4–6 小时' },
          { value: '7_9', label: '7–9 小时' },
          { value: '10_plus', label: '10 小时及以上' },
        ],
      },
    ],
  },
  {
    dimension: 'diet',
    title: '饮食习惯',
    icon: '🥗',
    accent: 'from-emerald-500/20 to-lime-500/10 border-emerald-400/20',
    questions: [
      {
        key: 'meal_regularity',
        label: '你最近的三餐规律程度如何？',
        hint: '按最近两周的实际情况选择。',
        options: [
          { value: 'rarely', label: '经常不规律' },
          { value: 'sometimes', label: '偶尔规律' },
          { value: 'usually', label: '大多数时候规律' },
          { value: 'always', label: '基本每天规律' },
        ],
      },
      {
        key: 'vegetable_frequency',
        label: '你通常多久吃一次蔬菜或水果？',
        hint: '这里关注持续习惯，不要求精确称重。',
        options: [
          { value: 'rarely', label: '很少' },
          { value: 'one', label: '每天约 1 次' },
          { value: 'two_plus', label: '每天 2 次及以上' },
        ],
      },
      {
        key: 'sugary_drinks',
        label: '你喝含糖饮料的频率是？',
        hint: '包括奶茶、含糖汽水和加糖咖啡。',
        options: [
          { value: 'daily', label: '几乎每天' },
          { value: 'weekly', label: '每周 1–3 次' },
          { value: 'rarely', label: '很少或不喝' },
        ],
      },
    ],
  },
  {
    dimension: 'sleep',
    title: '睡眠状态',
    icon: '🌙',
    accent: 'from-violet-500/20 to-indigo-500/10 border-violet-400/20',
    questions: [
      {
        key: 'sleep_duration',
        label: '你平均每天睡多久？',
        hint: '以最近两周的平均情况为准。',
        options: [
          { value: 'under_6', label: '少于 6 小时' },
          { value: '6_7', label: '6–7 小时' },
          { value: '7_9', label: '7–9 小时' },
          { value: 'over_9', label: '9 小时以上' },
        ],
      },
      {
        key: 'sleep_regularity',
        label: '你的入睡和起床时间规律吗？',
        hint: '周末和工作日差异很大也属于不规律。',
        options: [
          { value: 'irregular', label: '经常变化' },
          { value: 'sometimes', label: '偶尔规律' },
          { value: 'regular', label: '基本固定' },
        ],
      },
      {
        key: 'sleep_quality',
        label: '早上醒来时通常是什么状态？',
        hint: '这是主观感受，没有“标准答案”。',
        options: [
          { value: 'poor', label: '经常疲惫' },
          { value: 'average', label: '一般' },
          { value: 'good', label: '大多数时候精神良好' },
        ],
      },
    ],
  },
  {
    dimension: 'appearance',
    title: '形象管理',
    icon: '✨',
    accent: 'from-pink-500/20 to-rose-500/10 border-pink-400/20',
    questions: [
      {
        key: 'skincare_frequency',
        label: '你进行基础清洁和护肤的频率是？',
        hint: '只评估习惯，不评价长相。',
        options: [
          { value: 'rarely', label: '很少' },
          { value: 'sometimes', label: '偶尔' },
          { value: 'daily', label: '基本每天' },
        ],
      },
      {
        key: 'sunscreen_frequency',
        label: '日间外出时，你通常会防晒吗？',
        hint: '包括防晒霜、帽子或遮阳伞。',
        options: [
          { value: 'rarely', label: '很少' },
          { value: 'sometimes', label: '按需使用' },
          { value: 'daily', label: '日间基本坚持' },
        ],
      },
      {
        key: 'grooming_frequency',
        label: '你整理仪容和保持整洁的习惯是？',
        hint: '关注自我护理，而不是审美排名。',
        options: [
          { value: 'rarely', label: '很少注意' },
          { value: 'sometimes', label: '重要场合会注意' },
          { value: 'daily', label: '日常保持整洁' },
        ],
      },
    ],
  },
];

const EVAL_STAGES: Array<{ key: EvalStage; label: string; icon: string }> = [
  { key: 'upload', label: '上传并校验资料', icon: '↑' },
  { key: 'assess', label: 'Face++ 与规则引擎评估', icon: '◇' },
  { key: 'done', label: '保存画像并排队生成 AI 方案', icon: '✓' },
];

interface PhotoSlotProps {
  label: string;
  description: string;
  preview: string;
  onUpload: (file: File) => void;
  onRemove: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function PhotoSlot({ label, description, preview, onUpload, onRemove, inputRef }: PhotoSlotProps) {
  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])}
      />
      {preview ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          className="group relative aspect-square overflow-hidden rounded-2xl border border-cyan-400/20 bg-slate-900"
        >
          <img src={preview} alt={label} className="h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent" />
          <button
            onClick={onRemove}
            className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-slate-950/80 text-xs text-white transition hover:bg-rose-500"
            aria-label={`移除${label}`}
          >
            ✕
          </button>
          <div className="absolute bottom-0 left-0 right-0 p-3">
            <p className="text-sm font-medium text-white">{label}</p>
            <p className="text-[11px] text-slate-400">{description}</p>
          </div>
        </motion.div>
      ) : (
        <motion.button
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => inputRef.current?.click()}
          className="flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-700 bg-slate-900/60 text-slate-400 transition hover:border-cyan-400/50 hover:bg-cyan-400/5 hover:text-cyan-300"
        >
          <span className="text-2xl">＋</span>
          <span className="text-sm font-medium">{label}</span>
          <span className="px-3 text-center text-[10px] text-slate-500">{description}</span>
        </motion.button>
      )}
    </div>
  );
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { addNotification } = useNotification();
  const [step, setStep] = useState(0);
  const [questionGroup, setQuestionGroup] = useState(0);
  const [height, setHeight] = useState('');
  const [weight, setWeight] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('male');
  const [questionnaire, setQuestionnaire] = useState<Record<string, string>>({});
  const [photos, setPhotos] = useState<Record<PhotoType, File | null>>({
    avatar: null,
    portrait: null,
    front: null,
    side: null,
  });
  const [previews, setPreviews] = useState<Record<PhotoType, string>>({
    avatar: '',
    portrait: '',
    front: '',
    side: '',
  });
  const [evaluating, setEvaluating] = useState(false);
  const [evalStage, setEvalStage] = useState<EvalStage>('upload');
  const [evalError, setEvalError] = useState('');

  const avatarInputRef = useRef<HTMLInputElement>(null);
  const portraitInputRef = useRef<HTMLInputElement>(null);
  const frontInputRef = useRef<HTMLInputElement>(null);
  const sideInputRef = useRef<HTMLInputElement>(null);

  const bmi = useMemo(() => {
    const heightValue = Number(height);
    const weightValue = Number(weight);
    if (!heightValue || !weightValue) return null;
    return weightValue / (heightValue / 100) ** 2;
  }, [height, weight]);

  const currentGroup = QUESTION_GROUPS[questionGroup];
  const currentGroupComplete = currentGroup.questions.every((question) => questionnaire[question.key]);
  const allQuestionsComplete = QUESTION_GROUPS.every((group) =>
    group.questions.every((question) => questionnaire[question.key]),
  );

  const selectPhoto = (file: File, type: PhotoType) => {
    if (previews[type]) URL.revokeObjectURL(previews[type]);
    setPhotos((current) => ({ ...current, [type]: file }));
    setPreviews((current) => ({ ...current, [type]: URL.createObjectURL(file) }));
  };

  const removePhoto = (type: PhotoType) => {
    if (previews[type]) URL.revokeObjectURL(previews[type]);
    setPhotos((current) => ({ ...current, [type]: null }));
    setPreviews((current) => ({ ...current, [type]: '' }));
  };

  const submitAssessment = async () => {
    if (!allQuestionsComplete) return;
    setEvaluating(true);
    setEvalStage('upload');
    setEvalError('');

    try {
      if (Object.values(photos).some(Boolean)) {
        const formData = new FormData();
        if (photos.avatar) formData.append('avatar', photos.avatar);
        if (photos.portrait) formData.append('portrait_photo', photos.portrait);
        if (photos.front) formData.append('front_photo', photos.front);
        if (photos.side) formData.append('side_photo', photos.side);
        const uploadResponse = await api.post('/users/me/photos/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        const quality = uploadResponse.data.portrait_quality as { warnings?: string[] } | undefined;
        if (quality?.warnings?.length) {
          addNotification({
            type: 'warning',
            title: '照片质量提示',
            message: quality.warnings[0],
            duration: 7000,
          });
        }
      }

      setEvalStage('assess');
      const response = await api.post(
        '/users/me/evaluate',
        {
          height_cm: Number(height),
          weight_kg: Number(weight),
          age: Number(age),
          gender,
          questionnaire,
        },
        { timeout: 60_000 },
      );

      if (response.data.skin_source === 'unavailable') {
        addNotification({
          type: 'warning',
          title: 'Face++ 暂未返回结果',
          message: '肤质观察已标记为不可用，四项行为评分不受影响。',
          duration: 7000,
        });
      } else if (response.data.assessment?.reused) {
        addNotification({
          type: 'success',
          title: '已复用一致评估',
          message: '检测到相同输入，已返回同一规则版本的评估结果。',
          duration: 5000,
        });
      }

      if (response.data.generation_queued) {
        addNotification({
          type: 'info',
          title: '画像已建立',
          message: 'AI 护理建议和今日任务正在后台生成，完成后会自动通知你。',
          duration: 7000,
        });
      }

      setEvalStage('done');
      window.setTimeout(() => navigate('/'), 800);
    } catch (error: unknown) {
      let message = '评估失败，请重试。';
      if (
        typeof error === 'object'
        && error !== null
        && 'code' in error
        && (error as { code?: string }).code === 'ECONNABORTED'
      ) {
        message = '评估等待超过 60 秒，请检查 Face++ 服务后重试。';
      } else if (typeof error === 'object' && error !== null && 'response' in error) {
        const response = (error as {
          response?: { status?: number; data?: { detail?: unknown } };
        }).response;
        const detail = response?.data?.detail;
        if (typeof detail === 'string') {
          message = detail;
        } else if (Array.isArray(detail)) {
          const fields = detail.map((item) => {
            if (typeof item !== 'object' || item === null) return '未知字段校验失败';
            const entry = item as { loc?: unknown[]; msg?: string };
            const location = entry.loc?.slice(1).join('.') || '请求数据';
            return `${location}：${entry.msg || '格式不正确'}`;
          });
          message = fields.join('；');
        } else if (response?.status) {
          message = `评估请求失败（HTTP ${response.status}），请稍后重试。`;
        }
      }
      setEvalError(message);
      setEvaluating(false);
    }
  };

  if (evaluating) {
    const activeIndex = EVAL_STAGES.findIndex((stage) => stage.key === evalStage);
    return (
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 p-4">
        <motion.div
          className="absolute h-80 w-80 rounded-full bg-cyan-500/10 blur-3xl"
          animate={{ x: [-80, 90, -80], y: [-30, 50, -30], scale: [0.9, 1.2, 0.9] }}
          transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut' }}
        />
        <div className="relative w-full max-w-lg rounded-3xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl shadow-cyan-950/30 backdrop-blur-xl">
          <div className="mb-8 text-center">
            <motion.div
              className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-3xl"
              animate={{ rotate: [0, 4, -4, 0], boxShadow: ['0 0 0 rgba(34,211,238,0)', '0 0 35px rgba(34,211,238,.25)', '0 0 0 rgba(34,211,238,0)'] }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              ◇
            </motion.div>
            <h2 className="text-2xl font-semibold text-white">正在建立状态画像</h2>
            <p className="mt-2 text-sm text-slate-400">评分由固定规则计算，照片仅用于 Face++ 肤质观察</p>
          </div>

          <div className="mb-7 h-1.5 overflow-hidden rounded-full bg-slate-800">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500"
              animate={{ width: `${((activeIndex + 1) / EVAL_STAGES.length) * 100}%` }}
              transition={{ duration: 0.45 }}
            />
          </div>

          <div className="space-y-3">
            {EVAL_STAGES.map((stage, index) => {
              const complete = index < activeIndex || evalStage === 'done';
              const active = index === activeIndex && evalStage !== 'done';
              return (
                <motion.div
                  key={stage.key}
                  layout
                  className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${
                    active
                      ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-200'
                      : complete
                        ? 'border-emerald-400/20 bg-emerald-400/5 text-emerald-300'
                        : 'border-transparent bg-slate-900 text-slate-600'
                  }`}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-950/60 text-sm">
                    {complete ? '✓' : active ? <span className="h-3 w-3 animate-pulse rounded-full bg-cyan-300" /> : stage.icon}
                  </span>
                  <span className="text-sm font-medium">{stage.label}</span>
                  {active && <span className="ml-auto text-xs text-cyan-300/60">进行中</span>}
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  const steps = [
    <motion.div key="welcome" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="text-center">
      <motion.div
        className="mx-auto mb-7 flex h-20 w-20 items-center justify-center rounded-3xl border border-cyan-300/20 bg-gradient-to-br from-cyan-400/15 to-violet-500/15 text-4xl"
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      >
        ◇
      </motion.div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300/70">Personal Baseline</p>
      <h1 className="text-3xl font-semibold text-white">先建立一份可信的状态画像</h1>
      <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-slate-400">
        初始分数来自结构化问卷和固定规则，同样的输入会得到同样的结果。照片是可选项，Face++ 肤质观察不会被用来猜测你的运动、饮食或睡眠。
      </p>
      <motion.button
        whileHover={{ y: -2 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setStep(1)}
        className="mt-8 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-9 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-950/40"
      >
        开始建立画像
      </motion.button>
    </motion.div>,

    <motion.div key="basic" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }}>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300/60">01 · Basic</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">基础信息</h2>
      <p className="mt-2 text-sm text-slate-400">用于建立档案与后续计划，不通过 BMI 推断生活习惯。</p>
      <div className="mt-7 grid gap-4 sm:grid-cols-2">
        {[
          { label: '身高', unit: 'cm', value: height, setter: setHeight, placeholder: '175', min: 100, max: 250 },
          { label: '体重', unit: 'kg', value: weight, setter: setWeight, placeholder: '70', min: 30, max: 300 },
          { label: '年龄', unit: '岁', value: age, setter: setAge, placeholder: '25', min: 13, max: 100 },
        ].map((field) => (
          <label key={field.label} className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <span className="text-xs text-slate-500">{field.label}</span>
            <div className="mt-2 flex items-center gap-2">
              <input
                type="number"
                min={field.min}
                max={field.max}
                value={field.value}
                onChange={(event) => field.setter(event.target.value)}
                placeholder={field.placeholder}
                className="min-w-0 flex-1 bg-transparent text-xl font-medium text-white outline-none placeholder:text-slate-700"
              />
              <span className="text-xs text-slate-600">{field.unit}</span>
            </div>
          </label>
        ))}
        <label className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <span className="text-xs text-slate-500">性别</span>
          <select
            value={gender}
            onChange={(event) => setGender(event.target.value)}
            className="mt-2 w-full bg-transparent text-lg text-white outline-none"
          >
            <option className="bg-slate-900" value="male">男</option>
            <option className="bg-slate-900" value="female">女</option>
            <option className="bg-slate-900" value="other">其他</option>
          </select>
        </label>
      </div>
      <div className="mt-6 flex gap-3">
        <button onClick={() => setStep(0)} className="flex-1 rounded-xl bg-slate-800 py-3 text-sm text-slate-300 transition hover:bg-slate-700">返回</button>
        <button
          onClick={() => setStep(2)}
          disabled={!height || !weight || !age || Number(age) < 13}
          className="flex-1 rounded-xl bg-blue-600 py-3 text-sm font-medium text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600"
        >
          下一步
        </button>
      </div>
    </motion.div>,

    <motion.div key="photos" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }}>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300/60">02 · Optional photo</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">照片资料</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">正面肖像用于 Face++ 肤质观察；全身照片仅作为日后成长对比素材，不参与初始评分。</p>
      <div className="mt-6 grid grid-cols-2 gap-4">
        <PhotoSlot label="头像" description="仅用于账号展示" preview={previews.avatar} onUpload={(file) => selectPhoto(file, 'avatar')} onRemove={() => removePhoto('avatar')} inputRef={avatarInputRef} />
        <PhotoSlot label="正面肖像" description="Face++ 肤质观察" preview={previews.portrait} onUpload={(file) => selectPhoto(file, 'portrait')} onRemove={() => removePhoto('portrait')} inputRef={portraitInputRef} />
        <PhotoSlot label="正面全身" description="成长对比，不参与评分" preview={previews.front} onUpload={(file) => selectPhoto(file, 'front')} onRemove={() => removePhoto('front')} inputRef={frontInputRef} />
        <PhotoSlot label="侧面全身" description="成长对比，不参与评分" preview={previews.side} onUpload={(file) => selectPhoto(file, 'side')} onRemove={() => removePhoto('side')} inputRef={sideInputRef} />
      </div>
      <div className="mt-6 flex gap-3">
        <button onClick={() => setStep(1)} className="flex-1 rounded-xl bg-slate-800 py-3 text-sm text-slate-300 transition hover:bg-slate-700">返回</button>
        <button onClick={() => setStep(3)} className="flex-1 rounded-xl bg-blue-600 py-3 text-sm font-medium text-white transition hover:bg-blue-500">进入问卷</button>
      </div>
    </motion.div>,

    <motion.div key="questionnaire" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300/60">03 · Evidence</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">{currentGroup.icon} {currentGroup.title}</h2>
          <p className="mt-2 text-sm text-slate-400">第 {questionGroup + 1} / {QUESTION_GROUPS.length} 组 · 请选择最接近真实情况的选项</p>
        </div>
        <div className="flex gap-1.5 pt-2">
          {QUESTION_GROUPS.map((group, index) => (
            <button
              key={group.dimension}
              onClick={() => setQuestionGroup(index)}
              className={`h-2 rounded-full transition-all ${index === questionGroup ? 'w-7 bg-cyan-400' : 'w-2 bg-slate-700'}`}
              aria-label={group.title}
            />
          ))}
        </div>
      </div>

      <div className="mt-6 space-y-4">
        {currentGroup.questions.map((question, questionIndex) => (
          <motion.div
            key={question.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: questionIndex * 0.06 }}
            className={`rounded-2xl border bg-gradient-to-br p-4 ${currentGroup.accent}`}
          >
            <p className="text-sm font-medium text-white">{question.label}</p>
            <p className="mt-1 text-xs text-slate-500">{question.hint}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {question.options.map((option) => {
                const selected = questionnaire[question.key] === option.value;
                return (
                  <motion.button
                    key={option.value}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setQuestionnaire((current) => ({ ...current, [question.key]: option.value }))}
                    className={`rounded-xl border px-3 py-2.5 text-left text-xs transition ${
                      selected
                        ? 'border-cyan-300/50 bg-cyan-300/15 text-cyan-100 shadow-[0_0_20px_rgba(34,211,238,.08)]'
                        : 'border-white/5 bg-slate-950/35 text-slate-400 hover:border-white/15 hover:text-slate-200'
                    }`}
                  >
                    <span className={`mr-2 inline-block h-2 w-2 rounded-full ${selected ? 'bg-cyan-300' : 'bg-slate-700'}`} />
                    {option.label}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-6 flex gap-3">
        <button
          onClick={() => questionGroup === 0 ? setStep(2) : setQuestionGroup((current) => current - 1)}
          className="flex-1 rounded-xl bg-slate-800 py-3 text-sm text-slate-300 transition hover:bg-slate-700"
        >
          返回
        </button>
        <button
          disabled={!currentGroupComplete}
          onClick={() => questionGroup === QUESTION_GROUPS.length - 1 ? setStep(4) : setQuestionGroup((current) => current + 1)}
          className="flex-1 rounded-xl bg-blue-600 py-3 text-sm font-medium text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600"
        >
          {questionGroup === QUESTION_GROUPS.length - 1 ? '查看并确认' : '下一组'}
        </button>
      </div>
    </motion.div>,

    <motion.div key="confirm" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }}>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300/60">04 · Confirm</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">确认评估资料</h2>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs text-slate-500">身体数据</p>
          <p className="mt-2 text-lg font-medium text-white">{height} cm · {weight} kg</p>
          <p className="mt-1 text-xs text-slate-500">{age} 岁 · BMI {bmi?.toFixed(1)}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs text-slate-500">证据完整度</p>
          <p className="mt-2 text-lg font-medium text-emerald-300">12 / 12 项</p>
          <p className="mt-1 text-xs text-slate-500">固定规则 · 可解释 · 可复现</p>
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-cyan-400/15 bg-cyan-400/5 p-4 text-sm leading-6 text-slate-400">
        <p className="font-medium text-cyan-200">本次评估如何工作</p>
        <p className="mt-1">四项分数只由问卷规则计算；{photos.portrait || photos.front ? 'Face++ 会额外生成独立肤质观察。' : '你没有上传面部照片，本次不会调用 Face++。'}</p>
      </div>
      {evalError && <p className="mt-4 rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{evalError}</p>}
      <div className="mt-6 flex gap-3">
        <button onClick={() => setStep(3)} className="flex-1 rounded-xl bg-slate-800 py-3 text-sm text-slate-300 transition hover:bg-slate-700">返回修改</button>
        <motion.button
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.98 }}
          onClick={submitAssessment}
          className="flex-1 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-950/30"
        >
          建立状态画像
        </motion.button>
      </div>
    </motion.div>,
  ];

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 px-4 py-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(34,211,238,.09),transparent_34%),radial-gradient(circle_at_85%_80%,rgba(139,92,246,.08),transparent_34%)]" />
      <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-3xl items-center">
        <div className="w-full rounded-3xl border border-white/10 bg-slate-900/75 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-9">
          <div className="mb-8 flex items-center gap-2">
            {Array.from({ length: 5 }, (_, index) => (
              <div key={index} className="h-1 flex-1 overflow-hidden rounded-full bg-slate-800">
                <motion.div
                  className="h-full bg-gradient-to-r from-cyan-400 to-blue-500"
                  animate={{ width: index <= step ? '100%' : '0%' }}
                  transition={{ duration: 0.35 }}
                />
              </div>
            ))}
          </div>
          <AnimatePresence mode="wait">{steps[step]}</AnimatePresence>
        </div>
      </div>
    </div>
  );
}
