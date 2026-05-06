import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';
import ScoreRing from '../components/ScoreRing';
import DimensionBar from '../components/DimensionBar';

export default function Dashboard() {
  const { data: scores } = useQuery({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: tasks } = useQuery({
    queryKey: ['today-tasks'],
    queryFn: () => api.get('/tasks/today').then((r) => r.data),
  });

  const avgScore = scores ? scores.reduce((a: number, s: any) => a + s.score, 0) / scores.length : 0;

  return (
    <div className="min-h-screen bg-slate-950 p-6">
      <div className="max-w-2xl mx-auto">
        <motion.h1 initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="text-2xl font-bold text-white mb-6">⚡ 系统</motion.h1>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-6 flex items-center gap-8">
          <ScoreRing score={avgScore} />
          <div className="flex-1">
            {scores?.map((s: any) => (
              <DimensionBar key={s.dimension} dimension={s.dimension}
                score={s.score} streak={s.streak_days} threshold={7} />
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-4">今日任务</h2>
          {tasks?.length === 0 && <p className="text-slate-500">暂无任务，等待系统发布...</p>}
          {tasks?.map((t: any) => (
            <div key={t.id} className="bg-slate-800 rounded-lg p-3 mb-2 flex justify-between items-center">
              <div>
                <div className="text-white text-sm">{t.title}</div>
                <div className="text-slate-500 text-xs">{t.difficulty}</div>
              </div>
              <span className={`text-xs px-2 py-1 rounded ${
                t.status === 'completed' ? 'bg-emerald-900 text-emerald-400' : 'bg-slate-700 text-slate-400'
              }`}>
                {t.status === 'completed' ? '已完成' : '待完成'}
              </span>
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
