import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';
import { useNotification } from '../components/Notification';

const EVAL_STEPS = [
  { key: 'upload', label: '上传照片', icon: '📸' },
  { key: 'skin', label: '肤质分析', icon: '🔍' },
  { key: 'analyze', label: 'AI综合分析', icon: '🧠' },
  { key: 'score', label: '建立评分', icon: '📊' },
  { key: 'tasks', label: '生成任务', icon: '📋' },
];

const QUESTIONS = [
  { key: 'exercise', text: '你每周运动几次，一次运动多长时间？' },
  { key: 'diet', text: '你的饮食规律如何？' },
  { key: 'sleep', text: '你通常几点睡觉，每次睡几个小时？' },
  { key: 'appearance', text: '你平常是否有注意打理自己，你对自己的外在形象满意吗？' },
];

interface PhotoSlotProps {
  label: string;
  desc: string;
  preview: string;
  onUpload: (file: File) => void;
  onRemove: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function PhotoSlot({ label, desc, preview, onUpload, onRemove, inputRef }: PhotoSlotProps) {
  return (
    <div className="relative">
      <input ref={inputRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
      {preview ? (
        <div className="relative aspect-square rounded-xl overflow-hidden border border-slate-700">
          <img src={preview} alt={label} className="w-full h-full object-cover" />
          <button onClick={onRemove}
            className="absolute top-1.5 right-1.5 w-6 h-6 bg-slate-900/80 rounded-full flex items-center justify-center text-white hover:bg-red-600 transition-colors text-xs">
            ✕
          </button>
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-2">
            <p className="text-white text-xs font-medium">{label}</p>
          </div>
        </div>
      ) : (
        <button onClick={() => inputRef.current?.click()}
          className="w-full aspect-square border-2 border-dashed border-slate-700 rounded-xl flex flex-col items-center justify-center gap-1.5 text-slate-400 hover:border-blue-500 hover:text-blue-400 transition-colors">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 16v-8m0 0l-3 3m3-3l3 3M3 16l3-3a2 2 0 012.828 0L12 16.172l3.172-3.172a2 2 0 012.828 0L21 16" />
          </svg>
          <span className="text-xs font-medium">{label}</span>
          <span className="text-[10px] text-slate-500">{desc}</span>
        </button>
      )}
    </div>
  );
}

export default function Onboarding() {
  const { addNotification } = useNotification();
  const [step, setStep] = useState(0);
  const [height, setHeight] = useState('');
  const [weight, setWeight] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('male');
  
  // 图片状态
  const [avatar, setAvatar] = useState<File | null>(null);
  const [portraitPhoto, setPortraitPhoto] = useState<File | null>(null);
  const [frontPhoto, setFrontPhoto] = useState<File | null>(null);
  const [sidePhoto, setSidePhoto] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState('');
  const [portraitPreview, setPortraitPreview] = useState('');
  const [frontPreview, setFrontPreview] = useState('');
  const [sidePreview, setSidePreview] = useState('');
  
  // 评估状态
  const [evaluating, setEvaluating] = useState(false);
  const [evalStep, setEvalStep] = useState(0);
  const [evalError, setEvalError] = useState('');
  const [evalMode, setEvalMode] = useState('');
  
  // 问卷状态
  const [questionnaire, setQuestionnaire] = useState<Record<string, string>>({});
  const [questionStep, setQuestionStep] = useState(0);
  const [currentAnswer, setCurrentAnswer] = useState('');
  
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const portraitInputRef = useRef<HTMLInputElement>(null);
  const frontInputRef = useRef<HTMLInputElement>(null);
  const sideInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const handleAnswerSubmit = () => {
    if (!currentAnswer.trim()) return;
    const q = QUESTIONS[questionStep];
    setQuestionnaire({ ...questionnaire, [q.key]: currentAnswer.trim() });
    setCurrentAnswer('');
    setQuestionStep(questionStep + 1);
  };

  const handlePhotoSelect = (file: File, type: 'avatar' | 'portrait' | 'front' | 'side') => {
    const url = URL.createObjectURL(file);
    switch (type) {
      case 'avatar':
        setAvatar(file);
        setAvatarPreview(url);
        break;
      case 'portrait':
        setPortraitPhoto(file);
        setPortraitPreview(url);
        break;
      case 'front':
        setFrontPhoto(file);
        setFrontPreview(url);
        break;
      case 'side':
        setSidePhoto(file);
        setSidePreview(url);
        break;
    }
  };

  const handlePhotoRemove = (type: 'avatar' | 'portrait' | 'front' | 'side') => {
    switch (type) {
      case 'avatar':
        setAvatar(null);
        setAvatarPreview('');
        break;
      case 'portrait':
        setPortraitPhoto(null);
        setPortraitPreview('');
        break;
      case 'front':
        setFrontPhoto(null);
        setFrontPreview('');
        break;
      case 'side':
        setSidePhoto(null);
        setSidePreview('');
        break;
    }
  };

  const hasEvalPhoto = portraitPhoto || frontPhoto || sidePhoto;

  // Auto-advance eval steps with simulated timing
  useEffect(() => {
    if (!evaluating) return;
    const delays = hasEvalPhoto ? [1500, 3000, 5000, 2000, 3000] : [500, 500, 500, 1500, 3000];
    let timeout: ReturnType<typeof setTimeout>;
    if (evalStep < delays.length - 1) {
      timeout = setTimeout(() => setEvalStep((s) => s + 1), delays[evalStep]);
    }
    return () => clearTimeout(timeout);
  }, [evaluating, evalStep, hasEvalPhoto]);

  const handleSubmit = async () => {
    setEvaluating(true);
    setEvalStep(0);
    setEvalError('');
    
    try {
      // 上传照片
      if (avatar || portraitPhoto || frontPhoto || sidePhoto) {
        const formData = new FormData();
        if (avatar) formData.append('avatar', avatar);
        if (portraitPhoto) formData.append('portrait_photo', portraitPhoto);
        if (frontPhoto) formData.append('front_photo', frontPhoto);
        if (sidePhoto) formData.append('side_photo', sidePhoto);
        
        await api.post('/users/me/photos/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      
      // 判断是否需要问卷
      if (!hasEvalPhoto) {
        // 没有评估图片，显示问卷
        setEvaluating(false);
        setStep(4); // 跳转到问卷步骤
        return;
      }
      
      // 有评估图片，直接评估
      setEvalStep(2); // 跳到AI分析步骤
      const response = await api.post('/users/me/evaluate', {
        height_cm: parseFloat(height),
        weight_kg: parseFloat(weight),
        age: parseInt(age),
        gender,
        questionnaire: Object.keys(questionnaire).length > 0 ? questionnaire : undefined,
      });
      
      setEvalMode(response.data.eval_mode);
      
      // 检查降级情况
      const { skin_source, eval_mode } = response.data;
      if (skin_source === 'ai') {
        addNotification({
          type: 'warning',
          title: '肤质分析降级',
          message: '外部API不可用，已使用系统AI进行肤质分析',
          duration: 8000,
        });
      } else if (skin_source === 'fallback') {
        addNotification({
          type: 'warning',
          title: '肤质分析降级',
          message: '肤质分析服务不可用，已使用默认评估',
          duration: 8000,
        });
      }
      
      setEvalStep(4); // 跳到生成任务步骤
      setTimeout(() => navigate('/'), 1200);
    } catch {
      setEvalError('评估失败，请重试');
      setEvaluating(false);
    }
  };

  const handleQuestionnaireSubmit = async () => {
    setEvaluating(true);
    setEvalStep(2);
    
    try {
      const response = await api.post('/users/me/evaluate', {
        height_cm: parseFloat(height),
        weight_kg: parseFloat(weight),
        age: parseInt(age),
        gender,
        questionnaire,
      });
      
      setEvalMode(response.data.eval_mode);
      
      // 检查降级情况
      const { eval_mode } = response.data;
      if (eval_mode === 'default') {
        addNotification({
          type: 'warning',
          title: '评估降级',
          message: 'AI评估服务不可用，已使用默认评分',
          duration: 8000,
        });
      }
      
      setEvalStep(4);
      setTimeout(() => navigate('/'), 1200);
    } catch {
      setEvalError('评估失败，请重试');
      setEvaluating(false);
    }
  };

  // Evaluating progress screen
  if (evaluating) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="bg-slate-900 rounded-2xl p-8 w-full max-w-md border border-slate-800">
          <div className="text-center mb-8">
            <div className="text-5xl mb-4">⚡</div>
            <h2 className="text-xl font-bold text-white mb-2">系统初始化中</h2>
            <p className="text-slate-400 text-sm">正在为你建立个人画像...</p>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-slate-800 rounded-full h-2 mb-8">
            <motion.div
              className="bg-gradient-to-r from-blue-600 to-violet-500 h-2 rounded-full"
              initial={{ width: '0%' }}
              animate={{ width: `${((evalStep + 1) / EVAL_STEPS.length) * 100}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
            />
          </div>

          {/* Steps */}
          <div className="space-y-4">
            {EVAL_STEPS.map((s, i) => (
              <motion.div
                key={s.key}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className={`flex items-center gap-3 ${
                  i < evalStep ? 'text-emerald-400' : i === evalStep ? 'text-blue-400' : 'text-slate-600'
                }`}
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${
                  i < evalStep ? 'bg-emerald-900/50' : i === evalStep ? 'bg-blue-900/50' : 'bg-slate-800'
                }`}>
                  {i < evalStep ? '✓' : i === evalStep ? (
                    <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  ) : s.icon}
                </div>
                <span className="text-sm font-medium">{s.label}</span>
                {i === evalStep && evalMode && (
                  <span className="text-xs text-slate-500 ml-auto">
                    {evalMode === 'photo' ? '图片+AI' : evalMode === 'questionnaire' ? '问卷' : ''}
                  </span>
                )}
              </motion.div>
            ))}
          </div>

          {evalError && (
            <div className="mt-6 text-center">
              <p className="text-red-400 text-sm mb-3">{evalError}</p>
              <button onClick={() => { setEvaluating(false); setEvalStep(0); }}
                className="px-6 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-sm transition-colors">
                重试
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const onboardingSteps = [
    // Step 0: Welcome
    <motion.div key="welcome" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      className="text-center">
      <div className="text-6xl mb-6">⚡</div>
      <h1 className="text-3xl font-bold text-white mb-4">欢迎来到系统</h1>
      <p className="text-slate-400 mb-8 max-w-md">
        系统将根据你的身体数据和照片，为你建立初始画像并制定专属成长计划。
        请如实填写，这将影响你的初始评分。
      </p>
      <button onClick={() => setStep(1)}
        className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
        开始评估
      </button>
    </motion.div>,

    // Step 1: Basic info
    <motion.div key="info" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
      <h2 className="text-xl font-bold text-white mb-6">身体数据</h2>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-slate-400 text-sm mb-1 block">身高 (cm)</label>
            <input type="number" value={height} onChange={(e) => setHeight(e.target.value)}
              placeholder="175" className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="text-slate-400 text-sm mb-1 block">体重 (kg)</label>
            <input type="number" value={weight} onChange={(e) => setWeight(e.target.value)}
              placeholder="70" className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-slate-400 text-sm mb-1 block">年龄</label>
            <input type="number" value={age} onChange={(e) => setAge(e.target.value)}
              placeholder="25" className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="text-slate-400 text-sm mb-1 block">性别</label>
            <select value={gender} onChange={(e) => setGender(e.target.value)}
              className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500">
              <option value="male">男</option>
              <option value="female">女</option>
              <option value="other">其他</option>
            </select>
          </div>
        </div>
        <button onClick={() => setStep(2)} disabled={!height || !weight || !age}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg font-medium transition-colors">
          下一步
        </button>
      </div>
    </motion.div>,

    // Step 2: Photo upload (2x2 grid)
    <motion.div key="photos" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
      <h2 className="text-xl font-bold text-white mb-2">上传照片</h2>
      <p className="text-slate-400 text-sm mb-5">
        上传照片可以帮助系统更准确地评估你的状态。所有照片都是可选的。
      </p>
      
      <div className="grid grid-cols-2 gap-3 mb-4">
        <PhotoSlot
          label="头像"
          desc="仅显示"
          preview={avatarPreview}
          onUpload={(file) => handlePhotoSelect(file, 'avatar')}
          onRemove={() => handlePhotoRemove('avatar')}
          inputRef={avatarInputRef}
        />
        <PhotoSlot
          label="正面肖像"
          desc="肤质分析"
          preview={portraitPreview}
          onUpload={(file) => handlePhotoSelect(file, 'portrait')}
          onRemove={() => handlePhotoRemove('portrait')}
          inputRef={portraitInputRef}
        />
        <PhotoSlot
          label="正面图"
          desc="体态分析"
          preview={frontPreview}
          onUpload={(file) => handlePhotoSelect(file, 'front')}
          onRemove={() => handlePhotoRemove('front')}
          inputRef={frontInputRef}
        />
        <PhotoSlot
          label="侧面图"
          desc="体态分析"
          preview={sidePreview}
          onUpload={(file) => handlePhotoSelect(file, 'side')}
          onRemove={() => handlePhotoRemove('side')}
          inputRef={sideInputRef}
        />
      </div>
      
      <p className="text-slate-500 text-xs mb-4">
        如果不上传评估照片（肖像/正面/侧面），系统将以问卷形式进行评估。
      </p>
      
      <div className="flex gap-3">
        <button onClick={() => setStep(1)}
          className="flex-1 py-3 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors">返回</button>
        <button onClick={() => setStep(hasEvalPhoto ? 3 : 4)}
          className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">下一步</button>
      </div>
    </motion.div>,

    // Step 3: Confirm & evaluate (有图片)
    <motion.div key="confirm" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
      <h2 className="text-xl font-bold text-white mb-6">确认信息</h2>
      <div className="bg-slate-800 rounded-lg p-4 mb-6 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">身高</span>
          <span className="text-white">{height} cm</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">体重</span>
          <span className="text-white">{weight} kg</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">年龄</span>
          <span className="text-white">{age} 岁</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">性别</span>
          <span className="text-white">{gender === 'male' ? '男' : gender === 'female' ? '女' : '其他'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">BMI</span>
          <span className="text-white">{(parseFloat(weight) / (parseFloat(height) / 100) ** 2).toFixed(1)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">头像</span>
          <span className="text-white">{avatar ? '已上传' : '未上传'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">正面肖像图</span>
          <span className="text-white">{portraitPhoto ? '已上传' : '未上传'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">正面图</span>
          <span className="text-white">{frontPhoto ? '已上传' : '未上传'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">侧面图</span>
          <span className="text-white">{sidePhoto ? '已上传' : '未上传'}</span>
        </div>
      </div>
      <p className="text-slate-500 text-sm mb-6">
        AI将综合分析你的照片和身体数据，给出四维初始评分。
      </p>
      <div className="flex gap-3">
        <button onClick={() => setStep(2)}
          className="flex-1 py-3 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors">返回修改</button>
        <button onClick={handleSubmit}
          className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">开始评估</button>
      </div>
    </motion.div>,

    // Step 4: Questionnaire (无图片)
    <motion.div key="questionnaire" initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }}>
      <h2 className="text-xl font-bold text-white mb-2">回答几个问题</h2>
      <p className="text-slate-400 text-sm mb-6">
        你没有上传评估照片，系统将通过以下问题来评估你的四维度初始评分。
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
              onKeyDown={(e) => { if (e.key === 'Enter') handleAnswerSubmit(); }}
              placeholder="输入你的回答..."
              aria-label="回答当前问题"
              className="flex-1 px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleAnswerSubmit}
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
          <button onClick={handleQuestionnaireSubmit}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
            开始评估
          </button>
        </div>
      )}

      <div className="flex gap-3 mt-4">
        <button onClick={() => { setStep(2); setQuestionStep(0); setQuestionnaire({}); setCurrentAnswer(''); }}
          className="flex-1 py-3 bg-slate-800 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors">
          返回
        </button>
      </div>
    </motion.div>,
  ];

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="bg-slate-900 rounded-2xl p-8 w-full max-w-md border border-slate-800">
        {/* Progress dots */}
        <div className="flex justify-center gap-2 mb-8">
          {Array.from({ length: hasEvalPhoto ? 4 : 5 }, (_, i) => (
            <div key={i} className={`w-2 h-2 rounded-full transition-colors ${i <= step ? 'bg-blue-500' : 'bg-slate-700'}`} />
          ))}
        </div>
        <AnimatePresence mode="wait">
          {onboardingSteps[step]}
        </AnimatePresence>
      </div>
    </div>
  );
}
