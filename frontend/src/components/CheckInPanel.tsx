import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';
import type { DailyCheckIn } from '../types';

export default function CheckInPanel() {
  const queryClient = useQueryClient();
  const [energy, setEnergy] = useState(3);
  const [mood, setMood] = useState(3);
  const [stress, setStress] = useState(3);
  const [availableMinutes, setAvailableMinutes] = useState(45);
  const [sleepHours, setSleepHours] = useState('');

  const { data } = useQuery<DailyCheckIn>({
    queryKey: ['today-checkin'],
    queryFn: () => api.get('/behavior/checkin/today').then((response) => response.data),
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: () => api.put('/behavior/checkin/today', {
      energy, mood, stress, available_minutes: availableMinutes,
      sleep_hours: sleepHours ? Number(sleepHours) : null,
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['today-checkin'] }),
        queryClient.invalidateQueries({ queryKey: ['behavior-metrics'] }),
      ]);
    },
  });

  if (data) {
    return (
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.05] px-5 py-4">
        <div>
          <p className="text-sm font-medium text-emerald-200">今日 Check-in 已完成</p>
          <p className="mt-1 text-xs text-slate-500">精力 {data.energy}/5 · 压力 {data.stress}/5 · 可投入 {data.available_minutes} 分钟</p>
        </div>
        <span className="text-xs text-emerald-300">计划会参考今天的状态</span>
      </div>
    );
  }

  const scales = [1, 2, 3, 4, 5];
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="mb-4 rounded-2xl border border-cyan-400/15 bg-slate-900 p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">30 秒今日 Check-in</h2>
        <p className="mt-1 text-xs text-slate-500">系统会据此调整今天的任务量和难度</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[['精力', energy, setEnergy], ['心情', mood, setMood], ['压力', stress, setStress]].map(([label, value, setter]) => (
          <div key={String(label)}>
            <p className="mb-2 text-xs text-slate-400">{String(label)}</p>
            <div className="flex gap-1">
              {scales.map((item) => <button key={item} type="button" onClick={() => (setter as (v: number) => void)(item)}
                className={`h-8 w-8 rounded-lg text-xs ${value === item ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-500'}`}>{item}</button>)}
            </div>
          </div>
        ))}
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-400">睡眠小时
            <input value={sleepHours} onChange={(event) => setSleepHours(event.target.value)} type="number" min="0" max="16" step="0.5"
              className="mt-2 w-full rounded-lg bg-slate-800 px-2 py-2 text-white outline-none" />
          </label>
          <label className="text-xs text-slate-400">可用分钟
            <input value={availableMinutes} onChange={(event) => setAvailableMinutes(Number(event.target.value))} type="number" min="0" max="360"
              className="mt-2 w-full rounded-lg bg-slate-800 px-2 py-2 text-white outline-none" />
          </label>
        </div>
      </div>
      <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}
        className="mt-4 rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50">保存今日状态</button>
    </motion.div>
  );
}
