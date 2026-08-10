import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import api from '../services/api';
import type { Dimension, Goal } from '../types';

const labels: Record<Dimension, string> = {
  exercise: '运动', diet: '饮食', sleep: '睡眠', appearance: '形象管理',
};

export default function Goals() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [content, setContent] = useState('');
  const [goalType, setGoalType] = useState<Dimension>('exercise');
  const [metric, setMetric] = useState('');
  const [target, setTarget] = useState('');
  const [deadline, setDeadline] = useState('');
  const { data: goals } = useQuery<Goal[]>({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals', { params: { status: 'active' } }).then((response) => response.data),
  });

  const createGoal = async () => {
    await api.post('/goals', {
      content,
      goal_type: goalType,
      target_metric: metric || null,
      target_value: target ? Number(target) : null,
      current_value: 0,
      deadline: deadline || null,
      milestones: [],
    });
    setContent(''); setMetric(''); setTarget(''); setDeadline(''); setCreating(false);
    await queryClient.invalidateQueries({ queryKey: ['goals'] });
  };

  const updateGoal = async (goal: Goal, updates: Record<string, unknown>) => {
    await api.put(`/goals/${goal.id}`, updates);
    await queryClient.invalidateQueries({ queryKey: ['goals'] });
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex items-center justify-between">
          <div><h1 className="text-2xl font-bold text-white">成长目标</h1><p className="mt-1 text-sm text-slate-500">目标会影响每日任务优先级</p></div>
          <button type="button" onClick={() => setCreating((value) => !value)} className="rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-slate-950">新建目标</button>
        </div>

        <AnimatePresence>
          {creating && <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="mb-5 overflow-hidden rounded-2xl border border-cyan-400/15 bg-slate-900 p-5">
            <div className="grid gap-3 md:grid-cols-2">
              <input value={content} onChange={(event) => setContent(event.target.value)} placeholder="例如：12 周内完成 5 公里慢跑"
                className="rounded-xl bg-slate-800 px-3 py-2.5 text-sm text-white outline-none md:col-span-2" />
              <select value={goalType} onChange={(event) => setGoalType(event.target.value as Dimension)} className="rounded-xl bg-slate-800 px-3 py-2.5 text-sm text-white outline-none">
                {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <input value={metric} onChange={(event) => setMetric(event.target.value)} placeholder="目标指标，如每周跑步次数" className="rounded-xl bg-slate-800 px-3 py-2.5 text-sm text-white outline-none" />
              <input value={target} onChange={(event) => setTarget(event.target.value)} type="number" placeholder="目标值" className="rounded-xl bg-slate-800 px-3 py-2.5 text-sm text-white outline-none" />
              <input value={deadline} onChange={(event) => setDeadline(event.target.value)} type="date" className="rounded-xl bg-slate-800 px-3 py-2.5 text-sm text-white outline-none" />
            </div>
            <button disabled={!content.trim()} type="button" onClick={() => void createGoal()} className="mt-4 rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-slate-950 disabled:opacity-40">创建并纳入计划</button>
          </motion.div>}
        </AnimatePresence>

        <div className="grid gap-4 md:grid-cols-2">
          {goals?.map((goal, index) => {
            const progress = goal.target_value ? Math.min(100, 100 * (goal.current_value ?? 0) / goal.target_value) : 0;
            return <motion.article key={goal.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }}
              className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <div className="flex items-start justify-between gap-3"><span className="rounded-lg bg-cyan-400/10 px-2 py-1 text-[10px] text-cyan-300">{labels[goal.goal_type]}</span><span className="text-[10px] text-slate-600">{goal.deadline ?? '长期目标'}</span></div>
              <h2 className="mt-4 text-base font-medium leading-6 text-white">{goal.content}</h2>
              {goal.target_value != null && <div className="mt-4"><div className="flex justify-between text-xs text-slate-500"><span>{goal.target_metric || '进度'}</span><span>{goal.current_value ?? 0}/{goal.target_value}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-500" style={{ width: `${progress}%` }} /></div></div>}
              <div className="mt-4 flex gap-2">
                {goal.target_value != null && <button type="button" onClick={() => {
                  const next = window.prompt('更新当前进度', String(goal.current_value ?? 0));
                  if (next != null) void updateGoal(goal, { current_value: Number(next) });
                }} className="rounded-lg bg-white/5 px-3 py-1.5 text-[11px] text-slate-400">更新进度</button>}
                <button type="button" onClick={() => void updateGoal(goal, { status: 'paused' })} className="rounded-lg bg-amber-400/5 px-3 py-1.5 text-[11px] text-amber-400">暂停</button>
                <button type="button" onClick={() => void updateGoal(goal, { status: 'completed' })} className="rounded-lg bg-emerald-400/5 px-3 py-1.5 text-[11px] text-emerald-400">完成</button>
              </div>
            </motion.article>;
          })}
        </div>
      </div>
    </div>
  );
}
