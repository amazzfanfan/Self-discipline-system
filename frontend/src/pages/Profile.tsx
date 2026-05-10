import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function Profile() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ height_cm: '', weight_kg: '', age: '', gender: 'male' });
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/users/me/profile').then((r) => {
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

  const updateMutation = useMutation({
    mutationFn: (data: any) => api.put('/users/me/profile', data),
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
      alert('AI评估完成，四维度分数已更新');
    },
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
                <img
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
            <p className="text-slate-600 text-xs mt-2 text-center">正面照用于AI外貌评估</p>
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

        {/* Re-evaluate */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          className="bg-slate-900 rounded-2xl p-5 border border-slate-800">
          <h2 className="text-base font-semibold text-slate-300 mb-2">AI 重新评估</h2>
          <p className="text-slate-500 text-sm mb-4">
            更新身体数据或更换照片后，可让AI重新评估你的四维度评分。
            {profile?.front_photo_url
              ? '将通过照片分析评估运动、饮食、睡眠、外貌四个维度。'
              : profile?.questionnaire
              ? '将根据身体数据和问卷回答评估四维度评分。'
              : '请先上传照片或填写问卷。'}
          </p>
          <div className="flex items-center gap-3">
            <button onClick={() => evaluateMutation.mutate()} disabled={evaluateMutation.isPending}
              className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 text-white rounded-lg text-sm transition-colors">
              {evaluateMutation.isPending ? '评估中...' : '重新评估'}
            </button>
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
          </div>
        </motion.div>
      </div>
    </div>
  );
}
