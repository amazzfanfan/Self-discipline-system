import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import api from '../services/api';
import type { Dimension, Goal, GoalPlanningStatus, GoalProgressEvent, GoalProgressSummary } from '../types';

const labels: Record<Dimension, string> = {
  exercise: '运动', diet: '饮食', sleep: '睡眠', appearance: '形象管理',
};

const icons: Record<Dimension, string> = {
  exercise: '↗', diet: '◒', sleep: '☾', appearance: '✦',
};

const weekdays = ['一', '二', '三', '四', '五', '六', '日'];

const statusMeta: Record<Goal['status'], { label: string; className: string }> = {
  active: { label: '进行中', className: 'border-cyan-300/15 bg-cyan-400/[0.08] text-cyan-200' },
  paused: { label: '已暂停', className: 'border-amber-300/15 bg-amber-400/[0.08] text-amber-200' },
  completed: { label: '已完成', className: 'border-emerald-300/15 bg-emerald-400/[0.08] text-emerald-200' },
};

type StatusFilter = 'all' | Goal['status'];

type GoalDraft = {
  content: string;
  goalType: Dimension;
  metric: string;
  target: string;
  current: string;
  deadline: string;
  recurrence: Goal['recurrence'];
  daysOfWeek: number[];
  preferredTime: string;
  durationMinutes: string;
  reminderEnabled: boolean;
  progressMode: Goal['progress_mode'];
};

const draftFromGoal = (goal: Goal): GoalDraft => ({
  content: goal.content,
  goalType: goal.goal_type,
  metric: goal.target_metric ?? '',
  target: goal.target_value == null ? '' : String(goal.target_value),
  current: goal.current_value == null ? '' : String(goal.current_value),
  deadline: goal.deadline ?? '',
  recurrence: goal.recurrence ?? 'flexible',
  daysOfWeek: goal.days_of_week ?? [],
  preferredTime: goal.preferred_time ?? '',
  durationMinutes: goal.duration_minutes == null ? '' : String(goal.duration_minutes),
  reminderEnabled: goal.reminder_enabled ?? false,
  progressMode: goal.progress_mode ?? 'sessions',
});

export default function Goals() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [content, setContent] = useState('');
  const [goalType, setGoalType] = useState<Dimension>('exercise');
  const [metric, setMetric] = useState('');
  const [target, setTarget] = useState('');
  const [deadline, setDeadline] = useState('');
  const [recurrence, setRecurrence] = useState<Goal['recurrence']>('flexible');
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>([]);
  const [preferredTime, setPreferredTime] = useState('');
  const [durationMinutes, setDurationMinutes] = useState('');
  const [reminderEnabled, setReminderEnabled] = useState(false);
  const [progressMode, setProgressMode] = useState<Goal['progress_mode']>('sessions');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingGoal, setEditingGoal] = useState<Goal | null>(null);
  const [editDraft, setEditDraft] = useState<GoalDraft | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<Goal | null>(null);
  const [timelineGoal, setTimelineGoal] = useState<Goal | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: goals = [], isLoading } = useQuery<Goal[]>({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals').then((response) => response.data),
  });

  const { data: progressSummaries = {} } = useQuery<Record<string, GoalProgressSummary>>({
    queryKey: ['goal-progress-summary'],
    queryFn: () => api.get('/goals/progress/summary').then((response) => response.data),
  });

  const { data: planningStatus } = useQuery<GoalPlanningStatus>({
    queryKey: ['goal-planning-status'],
    queryFn: () => api.get('/goals/planning-status').then((response) => response.data),
  });

  const { data: timeline = [], isLoading: timelineLoading } = useQuery<GoalProgressEvent[]>({
    queryKey: ['goal-progress-timeline', timelineGoal?.id],
    queryFn: () => api.get(`/goals/${timelineGoal?.id}/progress`).then((response) => response.data),
    enabled: Boolean(timelineGoal),
  });

  const visibleGoals = useMemo(
    () => statusFilter === 'all' ? goals : goals.filter((goal) => goal.status === statusFilter),
    [goals, statusFilter],
  );

  const counts = useMemo(() => ({
    all: goals.length,
    active: goals.filter((goal) => goal.status === 'active').length,
    paused: goals.filter((goal) => goal.status === 'paused').length,
    completed: goals.filter((goal) => goal.status === 'completed').length,
  }), [goals]);

  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['goals'] }),
    queryClient.invalidateQueries({ queryKey: ['goal-progress-summary'] }),
    queryClient.invalidateQueries({ queryKey: ['goal-planning-status'] }),
  ]);

  const createGoal = async () => {
    setNotice(null);
    try {
      await api.post('/goals', {
        content: content.trim(),
        goal_type: goalType,
        target_metric: metric.trim() || null,
        target_value: target ? Number(target) : null,
        current_value: 0,
        deadline: deadline || null,
        milestones: [],
        recurrence,
        days_of_week: recurrence === 'custom' || recurrence === 'weekly' ? daysOfWeek : [],
        preferred_time: preferredTime || null,
        duration_minutes: durationMinutes ? Number(durationMinutes) : null,
        reminder_enabled: reminderEnabled && Boolean(preferredTime),
        progress_mode: progressMode,
      });
      setContent(''); setMetric(''); setTarget(''); setDeadline('');
      setRecurrence('flexible'); setDaysOfWeek([]); setPreferredTime('');
      setDurationMinutes(''); setReminderEnabled(false); setCreating(false);
      setProgressMode('sessions');
      setNotice({ type: 'success', text: '目标已创建，并会参与后续任务规划。' });
      await refresh();
    } catch {
      setNotice({ type: 'error', text: '目标创建失败，请检查填写内容后重试。' });
    }
  };

  const updateGoal = async (goal: Goal, updates: Record<string, unknown>, successText = '目标状态已更新。') => {
    setBusyId(goal.id);
    setNotice(null);
    try {
      const { data: updatedGoal } = await api.put<Goal>(`/goals/${goal.id}`, updates);
      queryClient.setQueryData<Goal[]>(['goals'], (current = []) => (
        current.map((item) => item.id === updatedGoal.id ? updatedGoal : item)
      ));
      void refresh();
      setNotice({ type: 'success', text: successText });
      return true;
    } catch {
      setNotice({ type: 'error', text: '目标更新失败，请稍后重试。' });
      return false;
    } finally {
      setBusyId(null);
    }
  };

  const editGoal = (goal: Goal) => {
    setNotice(null);
    setEditingGoal(goal);
    setEditDraft(draftFromGoal(goal));
  };

  const saveGoalEdit = async () => {
    if (!editingGoal || !editDraft?.content.trim()) return;
    const saved = await updateGoal(editingGoal, {
      content: editDraft.content.trim(),
      goal_type: editDraft.goalType,
      target_metric: editDraft.metric.trim() || null,
      target_value: editDraft.target ? Number(editDraft.target) : null,
      current_value: editDraft.current ? Number(editDraft.current) : 0,
      deadline: editDraft.deadline || null,
      recurrence: editDraft.recurrence,
      days_of_week: editDraft.recurrence === 'custom' || editDraft.recurrence === 'weekly' ? editDraft.daysOfWeek : [],
      preferred_time: editDraft.preferredTime || null,
      duration_minutes: editDraft.durationMinutes ? Number(editDraft.durationMinutes) : null,
      reminder_enabled: editDraft.reminderEnabled && Boolean(editDraft.preferredTime),
      progress_mode: editDraft.progressMode,
    }, '目标内容和进度已保存。');
    if (saved) {
      setEditingGoal(null);
      setEditDraft(null);
    }
  };

  const deleteGoal = async (goal: Goal) => {
    setBusyId(goal.id);
    setNotice(null);
    try {
      await api.delete(`/goals/${goal.id}`);
      await refresh();
      setDeleteCandidate(null);
      setNotice({ type: 'success', text: '目标已永久删除。' });
    } catch {
      setNotice({ type: 'error', text: '目标删除失败，请稍后重试。' });
    } finally {
      setBusyId(null);
    }
  };

  const tabs: Array<{ value: StatusFilter; label: string }> = [
    { value: 'all', label: '全部' },
    { value: 'active', label: '进行中' },
    { value: 'paused', label: '已暂停' },
    { value: 'completed', label: '已完成' },
  ];

  const editIsValid = Boolean(
    editDraft?.content.trim()
    && (!editDraft.target || (Number.isFinite(Number(editDraft.target)) && Number(editDraft.target) > 0))
    && (!editDraft.current || (Number.isFinite(Number(editDraft.current)) && Number(editDraft.current) >= 0))
    && (!editDraft?.durationMinutes || (Number(editDraft.durationMinutes) >= 1 && Number(editDraft.durationMinutes) <= 600))
    && (!['custom', 'weekly'].includes(editDraft?.recurrence || '') || Boolean(editDraft?.daysOfWeek.length)),
  );

  return (
    <div className="relative h-full overflow-y-auto bg-[#050816] p-5 md:p-8">
      <div className="pointer-events-none absolute right-0 top-0 h-80 w-80 rounded-full bg-violet-500/[0.06] blur-[100px]" />
      <div className="relative mx-auto max-w-5xl">
        <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-[10px] uppercase tracking-[0.24em] text-cyan-300/60">Growth roadmap</p>
            <h1 className="mt-1 text-2xl font-bold text-white">成长目标</h1>
            <p className="mt-1.5 text-sm text-slate-500">目标会影响每日任务优先级，也可以直接在 Agent 对话中管理。</p>
          </div>
          <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }} type="button" onClick={() => setCreating((value) => !value)} className="rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 px-4 py-2.5 text-xs font-semibold text-slate-950 shadow-[0_12px_30px_rgba(34,211,238,.15)]">
            {creating ? '收起表单' : '＋ 新建目标'}
          </motion.button>
        </div>

        {planningStatus?.over_capacity && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="mb-5 rounded-2xl border border-amber-400/15 bg-amber-400/[0.055] p-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-amber-300">◷</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-amber-100">今日有 {planningStatus.queued_goal_count} 个目标正在排队</p>
                <p className="mt-1 text-xs leading-5 text-amber-100/55">今日容量为 {planningStatus.effective_budget} 项。系统会优先安排等待更久的目标，不会再让最新目标永久覆盖旧目标。</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {planningStatus.queued_goals.map((goal) => <span key={goal.id} className="max-w-full truncate rounded-full bg-slate-950/40 px-2.5 py-1 text-[10px] text-amber-200/70">{goal.content}</span>)}
                </div>
              </div>
            </div>
          </motion.div>
        )}

        <AnimatePresence>
          {notice && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              className={`mb-5 rounded-xl border px-4 py-3 text-xs ${notice.type === 'success' ? 'border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300' : 'border-rose-400/15 bg-rose-400/[0.06] text-rose-300'}`}>
              {notice.text}
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {creating && (
            <motion.div initial={{ opacity: 0, height: 0, y: -8 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -8 }} className="mb-6 overflow-hidden rounded-[24px] border border-cyan-300/15 bg-slate-900/75 shadow-2xl backdrop-blur-xl">
              <div className="border-b border-white/[0.06] px-5 py-4"><h2 className="text-sm font-medium text-white">创建可追踪目标</h2><p className="mt-1 text-[10px] text-slate-600">也可以在对话中说：“创建目标：每天晚上 8 点爬坡走 40 分钟”。</p></div>
              <div className="grid gap-3 p-5 md:grid-cols-2">
                <input value={content} onChange={(event) => setContent(event.target.value)} placeholder="例如：每天晚上 8 点在跑步机爬坡走 40 分钟" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none transition-colors focus:border-cyan-400/30 md:col-span-2" />
                <select value={goalType} onChange={(event) => setGoalType(event.target.value as Dimension)} className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30">
                  {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <input value={metric} onChange={(event) => setMetric(event.target.value)} placeholder="目标指标，如每周训练次数" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                <input value={target} onChange={(event) => setTarget(event.target.value)} type="number" placeholder="目标值（可选）" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                <input value={deadline} onChange={(event) => setDeadline(event.target.value)} type="date" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                <select value={recurrence} onChange={(event) => setRecurrence(event.target.value as Goal['recurrence'])} className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30">
                  <option value="flexible">灵活安排</option><option value="daily">每天</option><option value="weekly">每周指定日</option><option value="custom">自定义执行日</option>
                </select>
                <input aria-label="计划时间" value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} type="time" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                <input aria-label="计划时长" value={durationMinutes} onChange={(event) => setDurationMinutes(event.target.value)} min="1" max="600" type="number" placeholder="计划时长（分钟）" className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                <label className="flex items-center gap-2 rounded-xl border border-white/[0.06] bg-slate-950/50 px-3.5 py-3 text-xs text-slate-400"><input type="checkbox" checked={reminderEnabled} disabled={!preferredTime} onChange={(event) => setReminderEnabled(event.target.checked)} />执行前提醒</label>
                <select aria-label="进度记录方式" value={progressMode} onChange={(event) => setProgressMode(event.target.value as Goal['progress_mode'])} className="rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30 md:col-span-2"><option value="sessions">完成关联任务时自动累计</option><option value="manual">手动维护数值进度</option></select>
                {(recurrence === 'weekly' || recurrence === 'custom') && <div className="flex flex-wrap gap-2 md:col-span-2">{weekdays.map((day, index) => <button key={day} type="button" onClick={() => setDaysOfWeek((value) => value.includes(index) ? value.filter((item) => item !== index) : [...value, index].sort())} className={`h-9 w-9 rounded-lg text-xs ${daysOfWeek.includes(index) ? 'bg-cyan-400 text-slate-950' : 'bg-slate-950/70 text-slate-500'}`}>{day}</button>)}</div>}
                <div className="md:col-span-2"><button disabled={!content.trim() || ((recurrence === 'weekly' || recurrence === 'custom') && daysOfWeek.length === 0)} type="button" onClick={() => void createGoal()} className="rounded-xl bg-cyan-400 px-4 py-2.5 text-xs font-semibold text-slate-950 disabled:opacity-40">创建并纳入计划</button></div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {editingGoal && editDraft && (
            <motion.div role="dialog" aria-modal="true" aria-label="编辑成长目标" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
              onMouseDown={(event) => { if (event.target === event.currentTarget) { setEditingGoal(null); setEditDraft(null); } }}>
              <motion.div initial={{ opacity: 0, y: 18, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.98 }}
                className="w-full max-w-xl overflow-hidden rounded-[24px] border border-cyan-300/15 bg-slate-900 shadow-2xl">
                <div className="border-b border-white/[0.06] px-5 py-4">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-cyan-300/60">Goal editor</p>
                  <h2 className="mt-1 text-base font-semibold text-white">编辑成长目标</h2>
                  <p className="mt-1 text-[11px] text-slate-500">保存后会同步影响 Agent 的目标检索和每日任务规划。</p>
                </div>
                <div className="grid gap-3 p-5 md:grid-cols-2">
                  <label className="md:col-span-2">
                    <span className="mb-1.5 block text-[10px] text-slate-500">目标内容</span>
                    <textarea aria-label="目标内容" rows={3} value={editDraft.content} onChange={(event) => setEditDraft({ ...editDraft, content: event.target.value })}
                      className="w-full resize-none rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">目标维度</span>
                    <select aria-label="目标维度" value={editDraft.goalType} onChange={(event) => setEditDraft({ ...editDraft, goalType: event.target.value as Dimension })}
                      className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30">
                      {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">目标指标（可选）</span>
                    <input aria-label="目标指标" value={editDraft.metric} onChange={(event) => setEditDraft({ ...editDraft, metric: event.target.value })}
                      placeholder="例如：每周训练次数" className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">当前进度</span>
                    <input aria-label="当前进度" type="number" min="0" disabled={editDraft.progressMode === 'sessions'} value={editDraft.current} onChange={(event) => setEditDraft({ ...editDraft, current: event.target.value })}
                      className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">目标值（可选）</span>
                    <input aria-label="目标值" type="number" min="0.01" step="any" value={editDraft.target} onChange={(event) => setEditDraft({ ...editDraft, target: event.target.value })}
                      className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label className="md:col-span-2">
                    <span className="mb-1.5 block text-[10px] text-slate-500">进度记录方式</span>
                    <select aria-label="编辑进度记录方式" value={editDraft.progressMode} onChange={(event) => setEditDraft({ ...editDraft, progressMode: event.target.value as Goal['progress_mode'] })} className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30"><option value="sessions">完成关联任务时自动累计</option><option value="manual">手动维护数值进度</option></select>
                  </label>
                  <label className="md:col-span-2">
                    <span className="mb-1.5 block text-[10px] text-slate-500">截止日期（可选）</span>
                    <input aria-label="截止日期" type="date" value={editDraft.deadline} onChange={(event) => setEditDraft({ ...editDraft, deadline: event.target.value })}
                      className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">执行频率</span>
                    <select aria-label="执行频率" value={editDraft.recurrence} onChange={(event) => setEditDraft({ ...editDraft, recurrence: event.target.value as Goal['recurrence'] })} className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30">
                      <option value="flexible">灵活安排</option><option value="daily">每天</option><option value="weekly">每周指定日</option><option value="custom">自定义执行日</option>
                    </select>
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">计划时间</span>
                    <input aria-label="编辑计划时间" type="time" value={editDraft.preferredTime} onChange={(event) => setEditDraft({ ...editDraft, preferredTime: event.target.value })} className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label>
                    <span className="mb-1.5 block text-[10px] text-slate-500">计划时长（分钟）</span>
                    <input aria-label="编辑计划时长" type="number" min="1" max="600" value={editDraft.durationMinutes} onChange={(event) => setEditDraft({ ...editDraft, durationMinutes: event.target.value })} className="w-full rounded-xl border border-white/[0.06] bg-slate-950/70 px-3.5 py-3 text-sm text-white outline-none focus:border-cyan-400/30" />
                  </label>
                  <label className="flex items-center gap-2 self-end rounded-xl border border-white/[0.06] bg-slate-950/50 px-3.5 py-3 text-xs text-slate-400"><input type="checkbox" checked={editDraft.reminderEnabled} disabled={!editDraft.preferredTime} onChange={(event) => setEditDraft({ ...editDraft, reminderEnabled: event.target.checked })} />执行前提醒</label>
                  {(editDraft.recurrence === 'weekly' || editDraft.recurrence === 'custom') && <div className="flex flex-wrap gap-2 md:col-span-2">{weekdays.map((day, index) => <button key={day} type="button" onClick={() => setEditDraft({ ...editDraft, daysOfWeek: editDraft.daysOfWeek.includes(index) ? editDraft.daysOfWeek.filter((item) => item !== index) : [...editDraft.daysOfWeek, index].sort() })} className={`h-9 w-9 rounded-lg text-xs ${editDraft.daysOfWeek.includes(index) ? 'bg-cyan-400 text-slate-950' : 'bg-slate-950/70 text-slate-500'}`}>{day}</button>)}</div>}
                </div>
                <div className="flex justify-end gap-2 border-t border-white/[0.06] px-5 py-4">
                  <button type="button" onClick={() => { setEditingGoal(null); setEditDraft(null); }} className="rounded-xl border border-white/[0.08] px-4 py-2.5 text-xs text-slate-400 hover:text-white">取消</button>
                  <button type="button" disabled={!editIsValid || busyId === editingGoal.id} onClick={() => void saveGoalEdit()}
                    className="rounded-xl bg-cyan-400 px-4 py-2.5 text-xs font-semibold text-slate-950 disabled:opacity-40">{busyId === editingGoal.id ? '保存中…' : '保存修改'}</button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {deleteCandidate && (
            <motion.div role="dialog" aria-modal="true" aria-label="删除成长目标" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm">
              <motion.div initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.98 }}
                className="w-full max-w-md rounded-[22px] border border-rose-400/15 bg-slate-900 p-5 shadow-2xl">
                <h2 className="text-base font-semibold text-white">永久删除这个目标？</h2>
                <p className="mt-2 text-sm leading-6 text-slate-400">“{deleteCandidate.content}”将从目标规划中移除，此操作无法恢复。</p>
                <div className="mt-5 flex justify-end gap-2">
                  <button type="button" onClick={() => setDeleteCandidate(null)} className="rounded-xl border border-white/[0.08] px-4 py-2.5 text-xs text-slate-400 hover:text-white">取消</button>
                  <button type="button" disabled={busyId === deleteCandidate.id} onClick={() => void deleteGoal(deleteCandidate)} className="rounded-xl bg-rose-500/15 px-4 py-2.5 text-xs font-medium text-rose-300 disabled:opacity-40">确认删除</button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {timelineGoal && (
            <motion.div role="dialog" aria-modal="true" aria-label="目标执行记录" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) setTimelineGoal(null); }}>
              <motion.div initial={{ opacity: 0, y: 18, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.98 }} className="max-h-[75vh] w-full max-w-lg overflow-hidden rounded-[24px] border border-cyan-300/15 bg-slate-900 shadow-2xl">
                <div className="flex items-start justify-between border-b border-white/[0.06] px-5 py-4"><div><p className="text-[10px] uppercase tracking-[0.2em] text-cyan-300/60">Execution history</p><h2 className="mt-1 text-base font-semibold text-white">执行记录</h2><p className="mt-1 line-clamp-1 text-[11px] text-slate-500">{timelineGoal.content}</p></div><button type="button" onClick={() => setTimelineGoal(null)} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white">×</button></div>
                <div className="max-h-[55vh] space-y-2 overflow-y-auto p-5">
                  {timelineLoading && <p className="py-8 text-center text-xs text-slate-500">正在加载执行记录…</p>}
                  {!timelineLoading && timeline.length === 0 && <p className="py-8 text-center text-xs text-slate-500">完成关联任务后，记录会出现在这里。</p>}
                  {timeline.map((event) => {
                    const labels: Record<string, string> = {
                      task_completed: '完成关联任务',
                      task_completion_reverted: '撤销任务完成',
                      manual_progress: '手动更新进度',
                      created: '创建目标',
                      status_changed: '目标状态变更',
                      schedule_changed: '执行计划变更',
                      content_changed: '目标内容变更',
                      goal_updated: '目标设置变更',
                      target_completed: '达到目标值',
                      completion_reverted: '目标恢复进行中',
                    };
                    const positive = event.event_type === 'task_completed' || event.event_type === 'target_completed';
                    const reverted = event.event_type === 'task_completion_reverted' || event.event_type === 'completion_reverted';
                    const detail = event.metadata.task_title
                      || (typeof event.metadata.reason === 'string' && event.metadata.reason)
                      || `${event.previous_value ?? 0} → ${event.current_value ?? 0}`;
                    return <div key={event.id} className="flex gap-3 rounded-xl border border-white/5 bg-slate-950/40 p-3"><span className={`mt-1 h-2 w-2 flex-shrink-0 rounded-full ${positive ? 'bg-emerald-400' : reverted ? 'bg-amber-400' : 'bg-violet-400'}`} /><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-3"><span className="text-xs font-medium text-slate-300">{labels[event.event_type] || event.event_type}</span><span className="text-[9px] text-slate-600">{event.event_date}</span></div><p className="mt-1 text-[11px] text-slate-500">{detail}</p></div></div>;
                  })}
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mb-5 flex max-w-full gap-1 overflow-x-auto rounded-2xl border border-white/[0.06] bg-white/[0.025] p-1.5">
          {tabs.map((tab) => <button key={tab.value} type="button" onClick={() => setStatusFilter(tab.value)} className={`relative flex-shrink-0 rounded-xl px-3.5 py-2 text-[11px] transition-colors ${statusFilter === tab.value ? 'text-white' : 'text-slate-500 hover:text-slate-300'}`}>{statusFilter === tab.value && <motion.div layoutId="goal-status-tab" className="absolute inset-0 rounded-xl border border-cyan-300/15 bg-cyan-400/[0.08]" />}<span className="relative">{tab.label} <span className="ml-1 text-[9px] opacity-60">{counts[tab.value]}</span></span></button>)}
        </div>

        {isLoading ? (
          <div className="py-20 text-center text-sm text-slate-600">正在加载目标…</div>
        ) : visibleGoals.length === 0 ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-[24px] border border-dashed border-white/[0.08] bg-white/[0.02] py-16 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.04] text-xl text-slate-500">◎</div>
            <p className="mt-4 text-sm text-slate-400">这个分类还没有目标</p>
            <p className="mt-1 text-[10px] text-slate-600">暂停的目标会保留在“全部”和“已暂停”中，不会被删除。</p>
          </motion.div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {visibleGoals.map((goal, index) => {
              const progress = goal.target_value ? Math.min(100, 100 * (goal.current_value ?? 0) / goal.target_value) : 0;
              const status = statusMeta[goal.status];
              const weekly = progressSummaries[goal.id];
              return (
                <motion.article key={goal.id} layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} className="group relative overflow-hidden rounded-[22px] border border-white/[0.07] bg-slate-900/70 p-5 shadow-xl backdrop-blur-xl transition-colors hover:border-cyan-300/15">
                  <div className="absolute -right-8 -top-10 h-28 w-28 rounded-full bg-cyan-400/[0.05] blur-3xl" />
                  <div className="relative flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-400/10 text-sm text-cyan-200">{icons[goal.goal_type]}</span><span className="text-[10px] text-slate-400">{labels[goal.goal_type]}</span></div>
                    <span className={`rounded-full border px-2.5 py-1 text-[9px] ${status.className}`}>{status.label}</span>
                  </div>
                  <h2 className="relative mt-4 min-h-12 text-[15px] font-medium leading-6 text-white">{goal.content}</h2>
                  <div className="relative mt-2 flex items-center justify-between text-[9px] text-slate-600"><span>{goal.source === 'chat' ? '来自 Agent 对话' : '手动创建'}</span><span>{goal.deadline ?? '长期目标'}</span></div>
                  <div className="relative mt-3 flex flex-wrap gap-1.5 text-[9px]">
                    <span className="rounded-full bg-white/[0.04] px-2 py-1 text-slate-400">{goal.recurrence === 'daily' ? '每天' : !goal.recurrence || goal.recurrence === 'flexible' ? '灵活安排' : `周${(goal.days_of_week ?? []).map((day) => weekdays[day]).join('、')}`}</span>
                    {goal.preferred_time && <span className="rounded-full bg-cyan-400/[0.07] px-2 py-1 text-cyan-300">{goal.preferred_time}</span>}
                    {goal.duration_minutes && <span className="rounded-full bg-white/[0.04] px-2 py-1 text-slate-400">{goal.duration_minutes} 分钟</span>}
                    {goal.reminder_enabled && <span className="rounded-full bg-violet-400/[0.07] px-2 py-1 text-violet-300">提前 {goal.reminder_minutes_before} 分钟提醒</span>}
                  </div>
                  {weekly && <div className="relative mt-4 rounded-xl border border-cyan-300/10 bg-cyan-400/[0.035] p-3"><div className="flex items-center justify-between text-[10px]"><span className="text-slate-400">本周执行</span><span className="font-medium text-cyan-300">{weekly.completed}/{weekly.scheduled_to_date || weekly.scheduled_total} 次</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800"><motion.div initial={{ width: 0 }} animate={{ width: `${weekly.adherence ?? 0}%` }} className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400" /></div><div className="mt-2 flex justify-between text-[9px] text-slate-600"><span>{weekly.adherence == null ? '本周尚未到执行日' : `到期达成率 ${weekly.adherence}%`}</span><span>累计 {weekly.completed_sessions} 次</span></div></div>}
                  {goal.target_value != null && <div className="relative mt-4"><div className="flex justify-between text-[10px] text-slate-500"><span>{goal.target_metric || '目标进度'}</span><span>{goal.current_value ?? 0} / {goal.target_value}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800"><motion.div initial={{ width: 0 }} animate={{ width: `${progress}%` }} className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-500" /></div></div>}
                  <div className="relative mt-5 flex flex-wrap gap-2 border-t border-white/[0.055] pt-4">
                    <button type="button" onClick={() => setTimelineGoal(goal)} className="rounded-lg bg-cyan-400/[0.06] px-2.5 py-1.5 text-[10px] text-cyan-300 hover:bg-cyan-400/[0.1]">执行记录</button>
                    <button disabled={busyId === goal.id} type="button" onClick={() => editGoal(goal)} className="rounded-lg bg-white/[0.045] px-2.5 py-1.5 text-[10px] text-slate-400 hover:text-white">编辑</button>
                    {goal.status === 'active' && <button disabled={busyId === goal.id} type="button" onClick={() => void updateGoal(goal, { status: 'paused' })} className="rounded-lg bg-amber-400/[0.07] px-2.5 py-1.5 text-[10px] text-amber-300">暂停</button>}
                    {goal.status === 'paused' && <button disabled={busyId === goal.id} type="button" onClick={() => void updateGoal(goal, { status: 'active' })} className="rounded-lg bg-cyan-400/[0.07] px-2.5 py-1.5 text-[10px] text-cyan-300">恢复</button>}
                    {goal.status !== 'completed' && <button disabled={busyId === goal.id} type="button" onClick={() => void updateGoal(goal, { status: 'completed' })} className="rounded-lg bg-emerald-400/[0.07] px-2.5 py-1.5 text-[10px] text-emerald-300">完成</button>}
                    {goal.status === 'completed' && <button disabled={busyId === goal.id} type="button" onClick={() => void updateGoal(goal, { status: 'active' })} className="rounded-lg bg-cyan-400/[0.07] px-2.5 py-1.5 text-[10px] text-cyan-300">重新开始</button>}
                    <button disabled={busyId === goal.id} type="button" onClick={() => setDeleteCandidate(goal)} className="ml-auto rounded-lg px-2.5 py-1.5 text-[10px] text-slate-600 hover:bg-rose-400/[0.07] hover:text-rose-300">删除</button>
                  </div>
                </motion.article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
