import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { motion } from 'framer-motion';
import api from '../services/api';
import type { ScoreHistory, UserScore } from '../types';

const DIM_COLORS = {
  exercise: '#3b82f6',
  diet: '#10b981',
  sleep: '#8b5cf6',
  appearance: '#ec4899',
};

const DIM_LABELS: Record<string, string> = {
  exercise: '运动',
  diet: '饮食',
  sleep: '睡眠',
  appearance: '形象管理',
};

export default function Trends() {
  const { data: scores } = useQuery<UserScore[]>({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: history } = useQuery<ScoreHistory[]>({
    queryKey: ['score-history'],
    queryFn: () => api.get('/scores/history?limit=100').then((r) => r.data),
  });

  // Build chart data
  const chartData = [...(history ?? [])].reverse().map((h, i) => ({
    index: i + 1,
    [h.dimension]: h.delta,
    date: new Date(h.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
  }));

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        <motion.h1 initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="text-2xl font-bold text-white mb-6">评分趋势</motion.h1>

        {/* Current score cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {scores?.map((s) => (
            <motion.div key={s.dimension} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
              className="bg-slate-900 rounded-xl p-4 border border-slate-800 text-center">
              <div className="text-2xl font-bold" style={{ color: DIM_COLORS[s.dimension as keyof typeof DIM_COLORS] }}>
                {s.score.toFixed(1)}
              </div>
              <div className="text-sm text-slate-400 mt-1">{DIM_LABELS[s.dimension]}</div>
              <div className="text-xs text-slate-500 mt-1">连续 {s.streak_days} 天</div>
            </motion.div>
          ))}
        </div>

        {/* Trend chart */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-4">评分变动历史</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
              <Legend />
              {Object.entries(DIM_COLORS).map(([dim, color]) => (
                <Line key={dim} type="monotone" dataKey={dim} stroke={color} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      </div>
    </div>
  );
}
