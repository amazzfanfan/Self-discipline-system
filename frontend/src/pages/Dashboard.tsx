import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import CheckInPanel from '../components/CheckInPanel';
import DepthPanel from '../components/DepthPanel';
import GrowthCore from '../components/GrowthCore';
import { useNotification } from '../components/notification-context';
import type { AssessmentRun, BehaviorMetrics, Task, UserScore, WeeklyReview } from '../types';

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
  appearance: '形象管理',
};

const TASK_STATUS: Record<Task['status'], { label: string; badge: string; dot: string }> = {
  pending: { label: '待完成', badge: 'bg-slate-700/60 text-slate-400', dot: 'bg-slate-500' },
  in_progress: { label: '进行中', badge: 'bg-blue-900/60 text-blue-300', dot: 'bg-blue-400' },
  completed: { label: '已完成', badge: 'bg-emerald-900/60 text-emerald-400', dot: 'bg-emerald-400' },
  failed: { label: '已跳过', badge: 'bg-rose-900/60 text-rose-300', dot: 'bg-rose-400' },
  deferred: { label: '已调整', badge: 'bg-amber-900/60 text-amber-300', dot: 'bg-amber-400' },
};

function getTaskStatus(task: Task) {
  if (task.disposition === 'snoozed') return { label: '稍后再做', badge: 'bg-cyan-900/60 text-cyan-300', dot: 'bg-cyan-400' };
  if (task.disposition === 'excused') return { label: '今日免做', badge: 'bg-amber-900/60 text-amber-300', dot: 'bg-amber-400' };
  if (task.disposition === 'rescheduled') return { label: '已改期', badge: 'bg-violet-900/60 text-violet-300', dot: 'bg-violet-400' };
  if (task.disposition === 'expired') return { label: '已过期', badge: 'bg-rose-900/60 text-rose-300', dot: 'bg-rose-400' };
  if (task.disposition === 'skipped') return { label: '已跳过', badge: 'bg-rose-900/60 text-rose-300', dot: 'bg-rose-400' };
  return TASK_STATUS[task.status];
}

const DIFFICULTY_LABELS: Record<Task['difficulty'], string> = {
  easy: '简单',
  medium: '适中',
  hard: '较难',
};

function localDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function metricText(value: number | null | undefined, sampleCount: number | undefined) {
  return value == null ? '暂无数据' : `${value}% · ${sampleCount ?? 0} 项`;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addNotification } = useNotification();
  const hasNotifiedRef = useRef(false);

  const { data: scores } = useQuery<UserScore[]>({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: tasks, isLoading: tasksLoading } = useQuery<Task[]>({
    queryKey: ['today-tasks'],
    queryFn: () => api.get('/tasks/today').then((r) => r.data),
  });

  const { data: behaviorMetrics } = useQuery<BehaviorMetrics>({
    queryKey: ['behavior-metrics'],
    queryFn: () => api.get('/behavior/metrics').then((r) => r.data),
  });

  const { data: weeklyReview } = useQuery<WeeklyReview>({
    queryKey: ['weekly-review'],
    queryFn: () => api.get('/behavior/weekly-review').then((r) => r.data),
  });

  const { data: latestAssessment } = useQuery<AssessmentRun>({
    queryKey: ['latest-assessment'],
    queryFn: () => api.get('/users/me/assessment/latest').then((response) => response.data),
    retry: false,
    refetchInterval: (query) => {
      const assessment = query.state.data as AssessmentRun | undefined;
      return assessment && ['pending', 'running'].includes(assessment.generation.status)
        ? 2_000
        : false;
    },
  });

  useEffect(() => {
    if (latestAssessment?.generation.status !== 'completed') return;
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['chat-history'] }),
    ]);
  }, [latestAssessment?.generation.status, queryClient]);

  // 检测任务发布（只在当天首次加载时通知）
  useEffect(() => {
    if (tasks && tasks.length > 0 && !hasNotifiedRef.current) {
      const today = localDateKey(new Date());
      const lastNotified = localStorage.getItem('lastTaskNotified');

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
      }
    }
  }, [tasks, addNotification]);

  const avgScore = scores?.length ? scores.reduce((total, score) => total + score.score, 0) / scores.length : 0;
  const completedCount = tasks?.filter((task) => task.status === 'completed').length || 0;
  const totalCount = tasks?.filter((task) => task.disposition !== 'excused').length || 0;
  const maxStreak = scores ? Math.max(...scores.map((score) => score.streak_days), 0) : 0;

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

        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="mb-4">
          <DepthPanel className="rounded-[28px]" glow="rgba(34, 211, 238, 0.17)">
            <GrowthCore scores={scores} metrics={behaviorMetrics} />
          </DepthPanel>
        </motion.div>

        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="lift-surface rounded-2xl border border-emerald-400/10 bg-slate-900/80 p-4">
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-600">Today</div>
            <div className="mt-2 text-2xl font-semibold text-white">{tasksLoading ? '—' : completedCount}<span className="text-sm text-slate-600"> / {tasksLoading ? '—' : totalCount}</span></div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400 transition-all duration-500"
                style={{ width: totalCount > 0 ? `${(completedCount / totalCount) * 100}%` : '0%' }} />
            </div>
            <p className="mt-2 text-[10px] text-slate-600">今日任务完成进度</p>
          </div>
          <div className="lift-surface rounded-2xl border border-cyan-400/10 bg-slate-900/80 p-4">
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-600">7 Day Adherence</div>
            <div className="mt-2 text-2xl font-semibold text-cyan-300">{behaviorMetrics?.overall.adherence_7d == null ? '—' : `${behaviorMetrics.overall.adherence_7d}%`}</div>
            <p className="mt-3 text-[10px] text-slate-600">有效样本 {behaviorMetrics?.overall.sample_count_7d ?? 0} 项 · 最长连续 {maxStreak} 天</p>
          </div>
          <div className="lift-surface rounded-2xl border border-violet-400/10 bg-slate-900/80 p-4">
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-600">Stable Baseline</div>
            <div className="mt-2 bg-gradient-to-r from-blue-300 to-violet-300 bg-clip-text text-2xl font-semibold text-transparent">{avgScore.toFixed(1)}</div>
            <p className="mt-3 text-[10px] text-slate-600">结构化问卷画像均值 · 不代表医学结论</p>
          </div>
        </div>

        <CheckInPanel />

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
            {tasksLoading && (
              <p className="py-4 text-center text-sm text-slate-600">正在同步今日任务…</p>
            )}
            {!tasksLoading && tasks?.length === 0 && (
              <p className="text-slate-600 text-sm py-4 text-center">暂无任务，等待系统发布...</p>
            )}
            <div className="space-y-2">
              {tasks?.map((t) => {
                const status = getTaskStatus(t);
                return (
                <div key={t.id} className="bg-slate-800/60 rounded-lg p-3 flex items-start gap-3">
                  <div className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${status.dot}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-white text-sm">{t.title}</div>
                    <div className="text-slate-500 text-xs mt-0.5">{DIFFICULTY_LABELS[t.difficulty]}</div>
                  </div>
                  <span className={`mt-0.5 flex-shrink-0 whitespace-nowrap rounded px-2 py-0.5 text-xs ${status.badge}`}>
                    {status.label}
                  </span>
                </div>
              );})}
            </div>
          </motion.div>

          {/* Behavior momentum */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-slate-900 rounded-2xl p-5 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-slate-300">行为成长动量</h2>
              <button onClick={() => navigate('/trends')}
                className="text-xs text-slate-500 hover:text-slate-400 transition-colors">详细趋势 →</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {scores?.map((s) => (
                <div key={s.dimension} className="bg-slate-800/60 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-400">{DIM_LABELS[s.dimension]}</span>
                    <span className="text-sm font-semibold" style={{ color: DIM_COLORS[s.dimension] }}>
                      {behaviorMetrics?.dimensions[s.dimension]?.momentum ?? '—'}
                    </span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-700">
                    <div className="h-full rounded-full transition-all" style={{
                      width: `${behaviorMetrics?.dimensions[s.dimension]?.momentum ?? 0}%`,
                      backgroundColor: DIM_COLORS[s.dimension],
                    }} />
                  </div>
                  <p className="mt-2 text-[10px] text-slate-600">
                    {metricText(
                      behaviorMetrics?.dimensions[s.dimension]?.adherence_7d,
                      behaviorMetrics?.dimensions[s.dimension]?.sample_count_7d,
                    )}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {weeklyReview && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            className="mb-4 rounded-2xl border border-violet-400/15 bg-violet-400/[0.04] p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold text-violet-200">上周复盘</h2>
                <p className="mt-1 text-[10px] text-slate-600">
                  {weeklyReview.summary.week_start} 至 {weeklyReview.summary.week_end}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  完成 {weeklyReview.summary.completed_tasks}/{weeklyReview.summary.planned_tasks} 项 · Check-in {weeklyReview.summary.checkin_days} 天
                </p>
                {(weeklyReview.summary.excused_tasks || weeklyReview.summary.rescheduled_tasks) ? (
                  <p className="mt-1 text-[10px] text-slate-600">
                    今日免做 {weeklyReview.summary.excused_tasks || 0} 项 · 改期 {weeklyReview.summary.rescheduled_tasks || 0} 项
                  </p>
                ) : null}
                {weeklyReview.summary.goal_scheduled > 0 && (
                  <div className="mt-3 rounded-xl border border-violet-300/10 bg-slate-950/30 px-3 py-2">
                    <p className="text-[10px] text-violet-200/80">成长目标完成 {weeklyReview.summary.goal_completed}/{weeklyReview.summary.goal_scheduled} 次 · 达成率 {weeklyReview.summary.goal_adherence ?? 0}%</p>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-slate-600">{weeklyReview.summary.goal_progress.map((goal) => <span key={goal.goal_id}>{DIM_LABELS[goal.goal_type]} {goal.completed}/{goal.scheduled_to_date}</span>)}</div>
                  </div>
                )}
              </div>
              <div className="text-right text-xs text-slate-500">
                {weeklyReview.summary.suggested_focus
                  ? `建议关注：${DIM_LABELS[weeklyReview.summary.suggested_focus]}`
                  : '积累更多行为数据后生成建议'}
              </div>
            </div>
          </motion.div>
        )}

        {latestAssessment && (
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.36 }}
            className="mb-4 overflow-hidden rounded-2xl border border-cyan-400/15 bg-gradient-to-r from-cyan-400/5 via-slate-900 to-violet-400/5 p-5"
          >
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,.8)]" />
                  <h2 className="text-sm font-semibold text-slate-200">可复现状态基线</h2>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {latestAssessment.rubric_version} · 结构化问卷与固定规则 · 照片不参与行为评分
                </p>
                {latestAssessment.generation.status !== 'completed' && (
                  <p className="mt-2 text-xs text-cyan-300/80">
                    {latestAssessment.generation.status === 'failed'
                      ? 'AI 方案生成暂时失败，系统将在查询时自动重试。'
                      : '画像已保存，AI 护理建议和今日任务正在后台生成…'}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-5">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-600">证据置信度</p>
                  <p className="mt-1 text-xl font-semibold text-emerald-300">{Math.round(latestAssessment.overall_confidence * 100)}%</p>
                </div>
                <button onClick={() => navigate('/profile')} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-400 transition hover:border-cyan-400/30 hover:text-cyan-300">
                  查看依据 →
                </button>
              </div>
            </div>
          </motion.div>
        )}

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
