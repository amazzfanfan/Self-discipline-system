import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function Profile() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ height_cm: '', weight_kg: '', age: '', gender: 'male' });

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
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scores'] });
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      alert('AI评估完成，分数已更新');
    },
  });

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
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-6">个人画像</h1>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg text-slate-300">身体数据</h2>
            {!editing && (
              <button onClick={() => setEditing(true)}
                className="text-sm text-blue-400 hover:text-blue-300">编辑</button>
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
                  className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-sm">取消</button>
                <button onClick={handleSave}
                  className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">保存</button>
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

        {/* Re-evaluate button */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-2">AI 重新评估</h2>
          <p className="text-slate-500 text-sm mb-4">
            更新身体数据后，可让AI重新评估你的四维度初始评分。
          </p>
          <button onClick={() => evaluateMutation.mutate()} disabled={evaluateMutation.isPending}
            className="px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 text-white rounded-lg text-sm transition-colors">
            {evaluateMutation.isPending ? '评估中...' : '重新评估'}
          </button>
        </motion.div>
      </div>
    </div>
  );
}
