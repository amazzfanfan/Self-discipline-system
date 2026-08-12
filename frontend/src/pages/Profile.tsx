import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import ConfirmDialog from '../components/ConfirmDialog';
import PrivateImage from '../components/PrivateImage';
import { useNotification } from '../components/notification-context';
import { useAuthStore } from '../stores/authStore';
import type { AssessmentRun } from '../types';

const goalTypeIcons: Record<string, string> = {
  exercise: '🏃',
  diet: '🥗',
  sleep: '😴',
  appearance: '✨',
};

const goalTypeLabels: Record<string, string> = {
  exercise: '运动',
  diet: '饮食',
  sleep: '睡眠',
  appearance: '形象管理',
};

interface ProfileData {
  height_cm: number | null;
  weight_kg: number | null;
  age: number | null;
  gender: string | null;
  avatar_url: string | null;
  portrait_photo_url: string | null;
  front_photo_url: string | null;
  side_photo_url: string | null;
  questionnaire: Record<string, string> | null;
  skin_analysis: Record<string, unknown> | null;
  skincare_constraints: {
    sensitive_skin: boolean;
    pregnancy_or_breastfeeding: boolean;
    skin_barrier_damaged: boolean;
    prescription_treatment: boolean;
    allergies: string[];
  };
}

interface ProfilePayload {
  height_cm: number;
  weight_kg: number;
  age: number;
  gender: string;
}

interface GoalStructuredData {
  description?: string;
  target_value?: number;
  target_unit?: string;
  deadline?: string;
  current_value?: number;
}

interface GoalData {
  id: string;
  content: string;
  goal_type: string;
  structured_data?: GoalStructuredData | null;
  target_metric: string | null;
  target_value: number | null;
  current_value: number | null;
  deadline: string | null;
  status: string;
}

interface GoalPayload {
  content: string;
  goal_type: string;
  structured_data: GoalStructuredData;
  target_metric: string | null;
  target_value: number | null;
  current_value?: number;
  deadline: string | null;
}

interface GoalForm {
  title: string;
  description: string;
  goal_type: string;
  target_value: string;
  target_unit: string;
  deadline: string;
}

const emptyGoalForm: GoalForm = {
  title: '',
  description: '',
  goal_type: 'exercise',
  target_value: '',
  target_unit: '',
  deadline: '',
};

export default function Profile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addNotification } = useNotification();
  const fetchUser = useAuthStore((state) => state.fetchUser);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ height_cm: '', weight_kg: '', age: '', gender: 'male' });
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [safetyForm, setSafetyForm] = useState({
    sensitive_skin: false,
    pregnancy_or_breastfeeding: false,
    skin_barrier_damaged: false,
    prescription_treatment: false,
    allergies: '',
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Goal management state
  const [showGoalForm, setShowGoalForm] = useState(false);
  const [goalForm, setGoalForm] = useState<GoalForm>(emptyGoalForm);
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<GoalData | null>(null);

  const { data: profile } = useQuery<ProfileData>({
    queryKey: ['profile'],
    queryFn: () => api.get<ProfileData>('/users/me/profile').then((r) => {
      const p = r.data;
      setForm({
        height_cm: p.height_cm?.toString() || '',
        weight_kg: p.weight_kg?.toString() || '',
        age: p.age?.toString() || '',
        gender: p.gender || 'male',
      });
      const constraints = p.skincare_constraints || {
        sensitive_skin: false,
        pregnancy_or_breastfeeding: false,
        skin_barrier_damaged: false,
        prescription_treatment: false,
        allergies: [],
      };
      setSafetyForm({
        ...constraints,
        allergies: constraints.allergies.join('、'),
      });
      return p;
    }),
  });

  const { data: latestAssessment } = useQuery<AssessmentRun>({
    queryKey: ['latest-assessment'],
    queryFn: () => api.get<AssessmentRun>('/users/me/assessment/latest').then((response) => response.data),
    retry: false,
  });

  // Goals query
  const { data: goals, isLoading: goalsLoading } = useQuery<GoalData[]>({
    queryKey: ['goals'],
    queryFn: () => api.get<GoalData[]>('/goals').then((r) => r.data),
  });

  const updateMutation = useMutation({
    mutationFn: (data: ProfilePayload) => api.put('/users/me/profile', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      setEditing(false);
    },
    onError: () => addNotification({ type: 'error', title: '保存失败', message: '身体数据未更新，请检查输入后重试。' }),
  });

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
      queryClient.invalidateQueries({ queryKey: ['latest-assessment'] });
      addNotification({ type: 'success', title: '评估完成', message: '状态基线已按固定规则更新。' });
    },
    onError: () => addNotification({ type: 'error', title: '无法重新评估', message: '请先重新填写结构化问卷，再进行评估。' }),
  });

  const photoMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('avatar', file);
      return api.post('/users/me/photos/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      void fetchUser();
      setUploadingPhoto(false);
    },
    onError: () => {
      setUploadingPhoto(false);
      addNotification({ type: 'error', title: '照片上传失败', message: '请检查图片格式和大小后重试。' });
    },
  });

  const safetyMutation = useMutation({
    mutationFn: () => api.put('/users/me/profile', {
      skincare_constraints: {
        sensitive_skin: safetyForm.sensitive_skin,
        pregnancy_or_breastfeeding: safetyForm.pregnancy_or_breastfeeding,
        skin_barrier_damaged: safetyForm.skin_barrier_damaged,
        prescription_treatment: safetyForm.prescription_treatment,
        allergies: safetyForm.allergies.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
      },
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['profile'] });
      addNotification({ type: 'success', title: '护理限制已保存', message: '后续 AI 护理建议和形象任务都会执行安全校验。' });
    },
    onError: () => addNotification({ type: 'error', title: '保存失败', message: '护理限制没有更新，请稍后重试。' }),
  });

  // Goal mutations
  const createGoalMutation = useMutation({
    mutationFn: (data: GoalPayload) => api.post('/goals', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setShowGoalForm(false);
      setGoalForm(emptyGoalForm);
      addNotification({ type: 'success', title: '目标已创建', message: '可以在“成长目标”页面继续管理。' });
    },
    onError: () => addNotification({ type: 'error', title: '目标创建失败', message: '请检查填写内容后重试。' }),
  });

  const updateGoalMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: GoalPayload }) => api.put(`/goals/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setEditingGoalId(null);
      setShowGoalForm(false);
      setGoalForm(emptyGoalForm);
      addNotification({ type: 'success', title: '目标已更新', message: '目标数据已经同步。' });
    },
    onError: () => addNotification({ type: 'error', title: '目标更新失败', message: '目标数据未改变，请稍后重试。' }),
  });

  const deleteGoalMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/goals/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setDeleteCandidate(null);
      addNotification({ type: 'success', title: '目标已删除', message: '该目标已从规划中移除。' });
    },
    onError: () => addNotification({ type: 'error', title: '删除失败', message: '目标仍然保留，请稍后重试。' }),
  });

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPhoto(true);
    photoMutation.mutate(file);
  };

  const handleSave = () => {
    updateMutation.mutate({
      height_cm: parseFloat(form.height_cm),
      weight_kg: parseFloat(form.weight_kg),
      age: parseInt(form.age),
      gender: form.gender,
    });
  };

  const handleGoalSubmit = () => {
    const payload: GoalPayload = {
      content: goalForm.title.trim(),
      goal_type: goalForm.goal_type,
      structured_data: {
        description: goalForm.description || undefined,
        target_unit: goalForm.target_unit || undefined,
      },
      target_metric: goalForm.target_unit ? `目标（${goalForm.target_unit}）` : null,
      target_value: goalForm.target_value ? parseFloat(goalForm.target_value) : null,
      deadline: goalForm.deadline || null,
    };

    if (editingGoalId !== null) {
      updateGoalMutation.mutate({ id: editingGoalId, data: payload });
    } else {
      createGoalMutation.mutate({ ...payload, current_value: 0 });
    }
  };

  const handleEditGoal = (goal: GoalData) => {
    const details = goal.structured_data ?? {};
    setEditingGoalId(goal.id);
    setGoalForm({
      title: goal.content || '',
      description: details.description || '',
      goal_type: goal.goal_type || 'exercise',
      target_value: goal.target_value?.toString() || '',
      target_unit: details.target_unit || '',
      deadline: goal.deadline || '',
    });
    setShowGoalForm(true);
  };

  const handleCancelGoalForm = () => {
    setShowGoalForm(false);
    setEditingGoalId(null);
    setGoalForm(emptyGoalForm);
  };

  const handleDeleteGoal = (goal: GoalData) => setDeleteCandidate(goal);

  const genderLabel: Record<string, string> = { male: '男', female: '女', other: '其他' };

  return (
    <div className="h-full overflow-y-auto scrollbar-hide p-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-6">个人画像</h1>

        {/* Photo + Basic info row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          {/* Photo card */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="bg-slate-900 rounded-2xl p-5 border border-slate-800 flex flex-col items-center">
            <div className="w-full aspect-square rounded-xl overflow-hidden bg-slate-800 mb-3 relative group">
              {profile?.avatar_url ? (
                <PrivateImage
                  src={profile.avatar_url}
                  alt="个人头像"
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center text-slate-600">
                  <svg className="w-12 h-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  <span className="text-xs">暂无照片</span>
                </div>
              )}
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span className="text-white text-sm">{profile?.avatar_url ? '更换头像' : '上传头像'}</span>
              </div>
              <button onClick={() => fileInputRef.current?.click()}
                className="absolute inset-0 cursor-pointer" />
            </div>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
              onChange={handlePhotoSelect} />
            <button onClick={() => fileInputRef.current?.click()}
              disabled={uploadingPhoto}
              className="w-full py-2 text-sm text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50">
              {uploadingPhoto ? '上传中...' : profile?.avatar_url ? '更换头像' : '上传头像'}
            </button>
            <p className="text-slate-600 text-xs mt-2 text-center">头像仅用于个人资料与聊天展示</p>
          </motion.div>

          {/* Body data card */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="md:col-span-2 bg-slate-900 rounded-2xl p-5 border border-slate-800">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-base font-semibold text-slate-300">身体数据</h2>
              {!editing && (
                <button onClick={() => setEditing(true)}
                  className="text-sm text-blue-400 hover:text-blue-300 transition-colors">编辑</button>
              )}
            </div>

            {editing ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-slate-400 text-sm mb-1 block">身高 (cm)</label>
                    <input type="number" value={form.height_cm}
                      onChange={(e) => setForm({ ...form, height_cm: e.target.value })}
                      className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="text-slate-400 text-sm mb-1 block">体重 (kg)</label>
                    <input type="number" value={form.weight_kg}
                      onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
                      className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-slate-400 text-sm mb-1 block">年龄</label>
                    <input type="number" value={form.age}
                      onChange={(e) => setForm({ ...form, age: e.target.value })}
                      className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="text-slate-400 text-sm mb-1 block">性别</label>
                    <select value={form.gender}
                      onChange={(e) => setForm({ ...form, gender: e.target.value })}
                      className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="male">男</option>
                      <option value="female">女</option>
                      <option value="other">其他</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button onClick={() => setEditing(false)}
                    className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-sm transition-colors">取消</button>
                  <button onClick={handleSave}
                    className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors">保存</button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">身高</span>
                  <span className="text-white">{profile?.height_cm || '-'} cm</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">体重</span>
                  <span className="text-white">{profile?.weight_kg || '-'} kg</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">年龄</span>
                  <span className="text-white">{profile?.age || '-'} 岁</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">性别</span>
                  <span className="text-white">{genderLabel[profile?.gender || ''] || '-'}</span>
                </div>
                {profile?.height_cm && profile?.weight_kg && (
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">BMI</span>
                    <span className="text-white">
                      {(profile.weight_kg / (profile.height_cm / 100) ** 2).toFixed(1)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
          className="mb-4 rounded-2xl border border-amber-400/10 bg-slate-900 p-5">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-slate-300">护理安全限制</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">这些信息只用于约束 AI 护理建议，不参与状态评分，也不会交给 Face++。</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              ['sensitive_skin', '敏感肌或容易刺痛'],
              ['skin_barrier_damaged', '当前屏障受损或明显泛红'],
              ['pregnancy_or_breastfeeding', '孕期或哺乳期'],
              ['prescription_treatment', '正在接受皮肤处方治疗'],
            ].map(([key, label]) => (
              <label key={key} className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/5 bg-slate-950/40 px-3 py-3 text-sm text-slate-400">
                <input type="checkbox"
                  checked={Boolean(safetyForm[key as keyof typeof safetyForm])}
                  onChange={(event) => setSafetyForm({ ...safetyForm, [key]: event.target.checked })}
                  className="h-4 w-4 accent-cyan-400" />
                {label}
              </label>
            ))}
          </div>
          <label className="mt-3 block text-xs text-slate-500">
            已知过敏成分
            <input value={safetyForm.allergies}
              onChange={(event) => setSafetyForm({ ...safetyForm, allergies: event.target.value })}
              placeholder="例如：烟酰胺、香精；多个成分用顿号分隔"
              className="mt-2 w-full rounded-xl border border-white/5 bg-slate-950/50 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
          </label>
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-[11px] text-slate-600">命中禁忌的 AI 输出会被拒绝，不会用固定护理模板代替。</p>
            <button type="button" onClick={() => safetyMutation.mutate()} disabled={safetyMutation.isPending}
              className="shrink-0 rounded-xl bg-cyan-400/10 px-4 py-2.5 text-xs font-medium text-cyan-300 disabled:opacity-50">
              {safetyMutation.isPending ? '保存中...' : '保存限制'}
            </button>
          </div>
        </motion.div>

        {/* Goals Management */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-slate-900 rounded-2xl p-5 border border-slate-800 mb-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold text-slate-300">🎯 我的目标</h2>
            {!showGoalForm && (
              <button onClick={() => { setShowGoalForm(true); setEditingGoalId(null); setGoalForm(emptyGoalForm); }}
                className="text-sm text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1">
                <span className="text-lg leading-none">+</span> 新增目标
              </button>
            )}
          </div>

          {/* Goal Form */}
          <AnimatePresence>
            {showGoalForm && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden mb-4"
              >
                <div className="bg-slate-800/60 rounded-xl p-4 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-slate-400 text-sm mb-1 block">目标名称 *</label>
                      <input
                        type="text"
                        value={goalForm.title}
                        onChange={(e) => setGoalForm({ ...goalForm, title: e.target.value })}
                        placeholder="如：减重5公斤"
                        className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 text-sm mb-1 block">目标类型</label>
                      <select
                        value={goalForm.goal_type}
                        onChange={(e) => setGoalForm({ ...goalForm, goal_type: e.target.value })}
                        className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      >
                        {Object.entries(goalTypeLabels).map(([key, label]) => (
                          <option key={key} value={key}>{goalTypeIcons[key]} {label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-slate-400 text-sm mb-1 block">描述</label>
                    <input
                      type="text"
                      value={goalForm.description}
                      onChange={(e) => setGoalForm({ ...goalForm, description: e.target.value })}
                      placeholder="目标详情（可选）"
                      className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="text-slate-400 text-sm mb-1 block">目标值</label>
                      <input
                        type="number"
                        value={goalForm.target_value}
                        onChange={(e) => setGoalForm({ ...goalForm, target_value: e.target.value })}
                        placeholder="如 70"
                        className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 text-sm mb-1 block">单位</label>
                      <input
                        type="text"
                        value={goalForm.target_unit}
                        onChange={(e) => setGoalForm({ ...goalForm, target_unit: e.target.value })}
                        placeholder="如 kg、次"
                        className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 text-sm mb-1 block">截止日期</label>
                      <input
                        type="date"
                        value={goalForm.deadline}
                        onChange={(e) => setGoalForm({ ...goalForm, deadline: e.target.value })}
                        className="w-full px-4 py-2.5 bg-slate-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                  </div>
                  <div className="flex gap-3 pt-1">
                    <button onClick={handleCancelGoalForm}
                      className="flex-1 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm transition-colors">
                      取消
                    </button>
                    <button
                      onClick={handleGoalSubmit}
                      disabled={!goalForm.title || createGoalMutation.isPending || updateGoalMutation.isPending}
                      className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm transition-colors"
                    >
                      {createGoalMutation.isPending || updateGoalMutation.isPending
                        ? '保存中...'
                        : editingGoalId !== null ? '更新目标' : '创建目标'}
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Goals List */}
          {goalsLoading ? (
            <div className="text-center py-6 text-slate-500 text-sm">加载中...</div>
          ) : goals?.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-3xl mb-2">🎯</div>
              <p className="text-slate-500 text-sm">暂无目标，点击上方按钮添加第一个目标</p>
            </div>
          ) : (
            <div className="space-y-2">
              {goals?.map((goal, i) => (
                <motion.div
                  key={goal.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="bg-slate-800/60 rounded-xl p-4 flex items-center gap-3 group"
                >
                  <div className="text-2xl flex-shrink-0">
                    {goalTypeIcons[goal.goal_type] || '🎯'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium text-sm truncate">{goal.content}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-400 flex-shrink-0">
                        {goalTypeLabels[goal.goal_type] || '其他'}
                      </span>
                    </div>
                    {goal.structured_data?.description && (
                      <p className="text-slate-500 text-xs mt-0.5 truncate">{goal.structured_data.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1">
                      {goal.target_value != null && (
                        <span className="text-slate-600 text-xs">
                          目标: {goal.target_value} {goal.structured_data?.target_unit || ''}
                        </span>
                      )}
                      {goal.deadline && (
                        <span className="text-slate-600 text-xs">
                          截止: {goal.deadline}
                        </span>
                      )}
                      {goal.current_value != null && goal.target_value != null && (
                        <span className="text-emerald-500/60 text-xs">
                          进度: {goal.current_value}/{goal.target_value} {goal.structured_data?.target_unit || ''}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <button
                      onClick={() => handleEditGoal(goal)}
                      className="p-2 text-slate-400 hover:text-blue-400 hover:bg-slate-700 rounded-lg transition-colors"
                      title="编辑"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDeleteGoal(goal)}
                      disabled={deleteGoalMutation.isPending && deleteCandidate?.id === goal.id}
                      className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors"
                      title="删除"
                    >
                      {deleteGoalMutation.isPending && deleteCandidate?.id === goal.id ? (
                        <span className="text-xs">...</span>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      )}
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>

        {/* Re-evaluate */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          className="bg-slate-900 rounded-2xl p-5 border border-slate-800">
          <h2 className="text-base font-semibold text-slate-300 mb-2">状态基线重新评估</h2>
          <p className="text-slate-500 text-sm mb-4">
            四项分数由结构化问卷和固定规则计算；照片只更新 Face++ 肤质观察，不影响运动、饮食或睡眠评分。
          </p>
          {latestAssessment && (
            <div className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/30 p-3 text-xs">
              <div>
                <p className="text-slate-600">规则版本</p>
                <p className="mt-1 text-slate-300">{latestAssessment.rubric_version}</p>
              </div>
              <div>
                <p className="text-slate-600">证据置信度</p>
                <p className="mt-1 text-emerald-400">{Math.round(latestAssessment.overall_confidence * 100)}%</p>
              </div>
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={() => evaluateMutation.mutate()} disabled={evaluateMutation.isPending || !profile?.questionnaire}
              className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 text-white rounded-lg text-sm transition-colors">
              {evaluateMutation.isPending ? '评估中...' : '重新评估'}
            </button>
            {profile?.questionnaire && (
              <span className="text-blue-500/60 text-xs flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                同一输入会复用一致结果
              </span>
            )}
            {!profile?.questionnaire && (
              <button onClick={() => navigate('/onboarding')} className="text-xs text-amber-400 hover:text-amber-300">
                去填写新版问卷 →
              </button>
            )}
          </div>
        </motion.div>
      </div>
      <ConfirmDialog
        open={Boolean(deleteCandidate)}
        title="永久删除这个目标？"
        description={deleteCandidate ? `“${deleteCandidate.content}”将从目标规划中移除，此操作无法恢复。` : ''}
        confirmLabel="确认删除"
        busy={deleteGoalMutation.isPending}
        onCancel={() => setDeleteCandidate(null)}
        onConfirm={() => { if (deleteCandidate) deleteGoalMutation.mutate(deleteCandidate.id); }}
      />
    </div>
  );
}
