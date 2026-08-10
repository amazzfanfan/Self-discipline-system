import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import PrivateImage from '../components/PrivateImage';
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
  status: string;
}

interface GoalPayload {
  content: string;
  goal_type: string;
  structured_data: GoalStructuredData;
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
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ height_cm: '', weight_kg: '', age: '', gender: 'male' });
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Goal management state
  const [showGoalForm, setShowGoalForm] = useState(false);
  const [goalForm, setGoalForm] = useState<GoalForm>(emptyGoalForm);
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [deletingGoalId, setDeletingGoalId] = useState<string | null>(null);

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
      alert('规则评估完成，状态基线已更新');
    },
    onError: () => alert('请先重新填写结构化问卷，再进行评估'),
  });

  const photoMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('front_photo', file);
      return api.post('/users/me/photos/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      setUploadingPhoto(false);
    },
    onError: () => {
      setUploadingPhoto(false);
      alert('照片上传失败，请重试');
    },
  });

  // Goal mutations
  const createGoalMutation = useMutation({
    mutationFn: (data: GoalPayload) => api.post('/goals', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setShowGoalForm(false);
      setGoalForm(emptyGoalForm);
    },
  });

  const updateGoalMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: GoalPayload }) => api.put(`/goals/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setEditingGoalId(null);
      setShowGoalForm(false);
      setGoalForm(emptyGoalForm);
    },
  });

  const deleteGoalMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/goals/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setDeletingGoalId(null);
    },
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
      content: goalForm.title,
      goal_type: goalForm.goal_type,
      structured_data: {
        description: goalForm.description || undefined,
        target_value: goalForm.target_value ? parseFloat(goalForm.target_value) : undefined,
        target_unit: goalForm.target_unit || undefined,
        deadline: goalForm.deadline || undefined,
      },
    };

    if (editingGoalId !== null) {
      updateGoalMutation.mutate({ id: editingGoalId, data: payload });
    } else {
      createGoalMutation.mutate(payload);
    }
  };

  const handleEditGoal = (goal: GoalData) => {
    const details = goal.structured_data ?? {};
    setEditingGoalId(goal.id);
    setGoalForm({
      title: goal.content || '',
      description: details.description || '',
      goal_type: goal.goal_type || 'exercise',
      target_value: details.target_value?.toString() || '',
      target_unit: details.target_unit || '',
      deadline: details.deadline || '',
    });
    setShowGoalForm(true);
  };

  const handleCancelGoalForm = () => {
    setShowGoalForm(false);
    setEditingGoalId(null);
    setGoalForm(emptyGoalForm);
  };

  const handleDeleteGoal = (id: string) => {
    if (confirm('确定要删除这个目标吗？')) {
      deleteGoalMutation.mutate(id);
    }
  };

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
              {profile?.front_photo_url ? (
                <PrivateImage
                  src={profile.front_photo_url}
                  alt="个人照片"
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
                <span className="text-white text-sm">{profile?.front_photo_url ? '更换照片' : '上传照片'}</span>
              </div>
              <button onClick={() => fileInputRef.current?.click()}
                className="absolute inset-0 cursor-pointer" />
            </div>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
              onChange={handlePhotoSelect} />
            <button onClick={() => fileInputRef.current?.click()}
              disabled={uploadingPhoto}
              className="w-full py-2 text-sm text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50">
              {uploadingPhoto ? '上传中...' : profile?.front_photo_url ? '更换照片' : '上传照片'}
            </button>
            <p className="text-slate-600 text-xs mt-2 text-center">正面照仅用于 Face++ 肤质观察</p>
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
                      {goal.structured_data?.target_value && (
                        <span className="text-slate-600 text-xs">
                          目标: {goal.structured_data.target_value} {goal.structured_data.target_unit || ''}
                        </span>
                      )}
                      {goal.structured_data?.deadline && (
                        <span className="text-slate-600 text-xs">
                          截止: {goal.structured_data.deadline}
                        </span>
                      )}
                      {goal.structured_data?.current_value !== undefined && goal.structured_data.target_value && (
                        <span className="text-emerald-500/60 text-xs">
                          进度: {goal.structured_data.current_value}/{goal.structured_data.target_value} {goal.structured_data.target_unit || ''}
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
                      onClick={() => handleDeleteGoal(goal.id)}
                      disabled={deletingGoalId === goal.id}
                      className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors"
                      title="删除"
                    >
                      {deletingGoalId === goal.id ? (
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
    </div>
  );
}
