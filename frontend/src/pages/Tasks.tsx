import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';
import type { Task } from '../types';

const dimensionLabels: Record<string, string> = {
  exercise: '🏃 运动',
  diet: '🥗 饮食',
  sleep: '😴 睡眠',
  appearance: '✨ 形象管理',
};

const statusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '待完成', color: 'bg-slate-700 text-slate-400' },
  in_progress: { text: '进行中', color: 'bg-blue-900 text-blue-400' },
  completed: { text: '已完成', color: 'bg-emerald-900 text-emerald-400' },
  failed: { text: '未完成', color: 'bg-red-900 text-red-400' },
  deferred: { text: '已延后', color: 'bg-amber-900/60 text-amber-400' },
};

export default function Tasks() {
  const [filter, setFilter] = useState('all');
  const queryClient = useQueryClient();

  const { data: tasks } = useQuery<Task[]>({
    queryKey: ['tasks', filter],
    queryFn: () => api.get('/tasks', { params: filter !== 'all' ? { dimension: filter } : {} }).then((r) => r.data),
  });

  const refreshTasks = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['behavior-metrics'] }),
    ]);
  };

  const deferTask = async (taskId: string) => {
    await api.post(`/tasks/${taskId}/defer`);
    await refreshTasks();
  };

  const feedbackTask = async (taskId: string, feedback: 'too_easy' | 'just_right' | 'too_hard' | 'not_suitable') => {
    await api.post(`/tasks/${taskId}/feedback`, { feedback });
    await refreshTasks();
  };

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
          {tasks?.map((t, i) => (
            <motion.div key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-slate-900 rounded-xl p-4 border border-slate-800">
              <div className="flex justify-between items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-white font-medium">{t.title}</div>
                  <div className="text-slate-500 text-sm mt-1">
                    {dimensionLabels[t.dimension]} · {t.difficulty}
                    {t.estimated_minutes ? ` · ${t.estimated_minutes} 分钟` : ''}
                  </div>
                  {t.rationale && <p className="mt-2 text-xs leading-5 text-slate-600">{t.rationale}</p>}
                  {t.scheduled_date && (
                    <div className="text-slate-600 text-xs mt-1">{t.scheduled_date}</div>
                  )}
                </div>
                <span className={`text-xs px-2 py-1 rounded whitespace-nowrap flex-shrink-0 ${statusLabels[t.status]?.color}`}>
                  {statusLabels[t.status]?.text}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
                {t.status === 'pending' && (
                  <button type="button" onClick={() => void deferTask(t.id)}
                    className="rounded-lg border border-amber-400/15 px-2.5 py-1 text-[11px] text-amber-300">今天先延后</button>
                )}
                <span className="text-[10px] text-slate-600">难度反馈</span>
                {([
                  ['too_easy', '太简单'], ['just_right', '正合适'], ['too_hard', '太难'], ['not_suitable', '不适合'],
                ] as const).map(([value, label]) => (
                  <button key={value} type="button" onClick={() => void feedbackTask(t.id, value)}
                    className={`rounded-lg px-2 py-1 text-[10px] ${t.user_feedback === value ? 'bg-cyan-400/15 text-cyan-300' : 'bg-slate-800 text-slate-500'}`}>{label}</button>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
