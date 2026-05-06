import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';

const dimensionLabels: Record<string, string> = {
  exercise: '🏃 运动',
  diet: '🥗 饮食',
  sleep: '😴 睡眠',
  appearance: '✨ 外貌',
};

const statusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '待完成', color: 'bg-slate-700 text-slate-400' },
  in_progress: { text: '进行中', color: 'bg-blue-900 text-blue-400' },
  completed: { text: '已完成', color: 'bg-emerald-900 text-emerald-400' },
  failed: { text: '未完成', color: 'bg-red-900 text-red-400' },
};

export default function Tasks() {
  const [filter, setFilter] = useState('all');

  const { data: tasks } = useQuery({
    queryKey: ['tasks', filter],
    queryFn: () => api.get('/tasks', { params: filter !== 'all' ? { dimension: filter } : {} }).then((r) => r.data),
  });

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-6">任务列表</h1>

        {/* Filters */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {['all', 'exercise', 'diet', 'sleep', 'appearance'].map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                filter === f ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}>
              {f === 'all' ? '全部' : dimensionLabels[f]}
            </button>
          ))}
        </div>

        {/* Task list */}
        <div className="space-y-3">
          {tasks?.length === 0 && (
            <p className="text-slate-500 text-center py-8">暂无任务</p>
          )}
          {tasks?.map((t: any, i: number) => (
            <motion.div key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-slate-900 rounded-xl p-4 border border-slate-800">
              <div className="flex justify-between items-start">
                <div>
                  <div className="text-white font-medium">{t.title}</div>
                  <div className="text-slate-500 text-sm mt-1">
                    {dimensionLabels[t.dimension]} · {t.difficulty}
                  </div>
                  {t.scheduled_date && (
                    <div className="text-slate-600 text-xs mt-1">{t.scheduled_date}</div>
                  )}
                </div>
                <span className={`text-xs px-2 py-1 rounded ${statusLabels[t.status]?.color}`}>
                  {statusLabels[t.status]?.text}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
