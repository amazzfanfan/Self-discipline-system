import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import ScoreRing from '../components/ScoreRing';
import DimensionBar from '../components/DimensionBar';
import { useNotification } from '../components/Notification';

const DIM_COLORS: Record<string, string> = {
  exercise: '#3b82f6',
  diet: '#10b981',
  sleep: '#8b5cf6',
  appearance: '#ec4899',
};

const DIM_LABELS: Record<string, string> = {
  exercise: '运动',
  diet: '饮食',
  sleep: '睡眠',
  appearance: '外貌',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { addNotification } = useNotification();
  const hasNotifiedRef = useRef(false);

  const { data: scores } = useQuery({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: tasks } = useQuery({
    queryKey: ['today-tasks'],
    queryFn: () => api.get('/tasks/today').then((r) => r.data),
  });

  const { data: history } = useQuery({
    queryKey: ['score-history'],
    queryFn: () => api.get('/scores/history?limit=100').then((r) => r.data),
  });

  // 检测任务发布（只在当天首次加载时通知）
  useEffect(() => {
    if (tasks && tasks.length > 0 && !hasNotifiedRef.current) {
      const today = new Date().toISOString().split('T')[0];
      const lastNotified = localStorage.getItem('lastTaskNotified');
      
      console.log('[通知调试]', { today, lastNotified, shouldNotify: lastNotified !== today });
      
      // 如果今天还没有通知过，就显示通知
      if (lastNotified !== today) {
        hasNotifiedRef.current = true;
        addNotification({
          type: 'success',
          title: '任务已发布',
          message: `今日已发布 ${tasks.length} 个任务，快去完成吧！`,
          duration: 6000,
        });
        localStorage.setItem('lastTaskNotified', today);
        console.log('[通知调试] 已保存:', today);
      }
    }
  }, [tasks, addNotification]);

  const avgScore = scores ? scores.reduce((a: number, s: any) => a + s.score, 0) / scores.length : 0;
  const completedCount = tasks?.filter((t: any) => t.status === 'completed').length || 0;
  const totalCount = tasks?.length || 0;
  const maxStreak = scores ? Math.max(...scores.map((s: any) => s.streak_days), 0) : 0;

  // Build per-dimension mini trend data
  const buildDimTrend = (dim: string) => {
    if (!history) return [];
    return history
      .filter((h: any) => h.dimension === dim)
      .reverse()
      .map((h: any, i: number) => ({ x: i, y: Math.abs(h.delta) }));
  };

  return (
    <div className="h-full overflow-y-auto scrollbar-hide p-6">
      <div className="max-w-5xl mx-auto">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">仪表盘</h1>
            <p className="text-slate-500 text-sm mt-1">
              {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
            </p>
          </div>
          <button onClick={() => navigate('/chat')}
            className="px-4 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg text-sm transition-colors flex items-center gap-2">
            <span>⚡</span> 去对话
          </button>
        </motion.div>

        {/* Top section: Score + Stats */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
          {/* Score overview */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="lg:col-span-2 bg-slate-900 rounded-2xl p-6 border border-slate-800 flex items-center gap-8">
            <ScoreRing score={avgScore} />
            <div className="flex-1 min-w-0">
              {scores?.map((s: any) => (
                <DimensionBar key={s.dimension} dimension={s.dimension}
                  score={s.score} streak={s.streak_days} threshold={7} />
              ))}
            </div>
          </motion.div>

          {/* Stats cards */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex flex-col gap-4">
            <div className="bg-slate-900 rounded-2xl p-5 border border-slate-800 flex-1">
              <div className="text-slate-500 text-xs mb-1">今日完成</div>
              <div className="text-3xl font-bold text-white">{completedCount}<span className="text-lg text-slate-500">/{totalCount}</span></div>
              <div className="mt-2 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
                  style={{ width: totalCount > 0 ? `${(completedCount / totalCount) * 100}%` : '0%' }} />
              </div>
            </div>
            <div className="bg-slate-900 rounded-2xl p-5 border border-slate-800 flex-1">
              <div className="text-slate-500 text-xs mb-1">最长连续</div>
              <div className="text-3xl font-bold text-white">{maxStreak}<span className="text-lg text-slate-500"> 天</span></div>
              <div className="text-slate-600 text-xs mt-1">继续保持</div>
            </div>
            <div className="bg-slate-900 rounded-2xl p-5 border border-slate-800 flex-1">
              <div className="text-slate-500 text-xs mb-1">综合评分</div>
              <div className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
                {avgScore.toFixed(1)}
              </div>
              <div className="text-slate-600 text-xs mt-1">
                {avgScore >= 70 ? '状态良好' : avgScore >= 50 ? '稳步提升中' : '加油，从今天开始'}
              </div>
            </div>
          </motion.div>
        </div>

        {/* Middle section: Today Tasks + Trends */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          {/* Today tasks */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-slate-900 rounded-2xl p-5 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-slate-300">今日任务</h2>
              <button onClick={() => navigate('/tasks')}
                className="text-xs text-slate-500 hover:text-slate-400 transition-colors">查看全部 →</button>
            </div>
            {tasks?.length === 0 && (
              <p className="text-slate-600 text-sm py-4 text-center">暂无任务，等待系统发布...</p>
            )}
            <div className="space-y-2">
              {tasks?.map((t: any) => (
                <div key={t.id} className="bg-slate-800/60 rounded-lg p-3 flex items-start gap-3">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${
                    t.status === 'completed' ? 'bg-emerald-400' : 'bg-slate-600'
                  }`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-white text-sm">{t.title}</div>
                    <div className="text-slate-500 text-xs mt-0.5">{t.difficulty}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded whitespace-nowrap flex-shrink-0 mt-0.5 ${
                    t.status === 'completed' ? 'bg-emerald-900/60 text-emerald-400' : 'bg-slate-700/60 text-slate-400'
                  }`}>
                    {t.status === 'completed' ? '已完成' : '待完成'}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Mini trend charts */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-slate-900 rounded-2xl p-5 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-slate-300">评分趋势</h2>
              <button onClick={() => navigate('/trends')}
                className="text-xs text-slate-500 hover:text-slate-400 transition-colors">详细趋势 →</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {scores?.map((s: any) => (
                <div key={s.dimension} className="bg-slate-800/60 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-400">{DIM_LABELS[s.dimension]}</span>
                    <span className="text-sm font-semibold" style={{ color: DIM_COLORS[s.dimension] }}>
                      {s.score.toFixed(1)}
                    </span>
                  </div>
                  <div className="h-10">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={buildDimTrend(s.dimension)}>
                        <Line type="monotone" dataKey="y" stroke={DIM_COLORS[s.dimension]}
                          strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Bottom: Quick actions */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '开始对话', desc: '报告今日任务', icon: '💬', to: '/chat', color: 'from-blue-600/20 to-blue-600/10 border-blue-500/20' },
            { label: '任务列表', desc: '查看所有任务', icon: '📋', to: '/tasks', color: 'from-emerald-600/20 to-emerald-600/10 border-emerald-500/20' },
            { label: '个人画像', desc: '查看评分详情', icon: '👤', to: '/profile', color: 'from-violet-600/20 to-violet-600/10 border-violet-500/20' },
            { label: '评分趋势', desc: '查看成长曲线', icon: '📈', to: '/trends', color: 'from-pink-600/20 to-pink-600/10 border-pink-500/20' },
          ].map((item) => (
            <button key={item.to} onClick={() => navigate(item.to)}
              className={`bg-gradient-to-br ${item.color} border rounded-xl p-4 text-left hover:scale-[1.02] transition-all`}>
              <div className="text-2xl mb-2">{item.icon}</div>
              <div className="text-white text-sm font-medium">{item.label}</div>
              <div className="text-slate-500 text-xs mt-0.5">{item.desc}</div>
            </button>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
