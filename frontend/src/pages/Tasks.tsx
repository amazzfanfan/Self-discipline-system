import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import api from '../services/api';
import { useNotification } from '../components/notification-context';
import type { Task } from '../types';

const dimensionLabels: Record<string, string> = {
  exercise: '🏃 运动',
  diet: '🥗 饮食',
  sleep: '😴 睡眠',
  appearance: '✨ 形象管理',
};

const difficultyLabels: Record<Task['difficulty'], string> = {
  easy: '简单',
  medium: '适中',
  hard: '较难',
};

type ScheduleMode = 'later' | 'reschedule' | 'excuse';

function localDateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function tomorrowKey() {
  const value = new Date();
  value.setDate(value.getDate() + 1);
  return localDateKey(value);
}

function toDateTimeLocal(value: Date) {
  const hours = String(value.getHours()).padStart(2, '0');
  const minutes = String(value.getMinutes()).padStart(2, '0');
  return `${localDateKey(value)}T${hours}:${minutes}`;
}

function getStatus(task: Task) {
  if (task.disposition === 'snoozed') return { text: '稍后再做', color: 'bg-cyan-400/10 text-cyan-300 border-cyan-400/20' };
  if (task.disposition === 'excused') return { text: '今日免做', color: 'bg-amber-400/10 text-amber-300 border-amber-400/20' };
  if (task.disposition === 'rescheduled') return { text: '已改期', color: 'bg-violet-400/10 text-violet-300 border-violet-400/20' };
  if (task.disposition === 'expired') return { text: '已过期', color: 'bg-rose-400/10 text-rose-300 border-rose-400/20' };
  if (task.disposition === 'skipped') return { text: '已跳过', color: 'bg-rose-400/10 text-rose-300 border-rose-400/20' };
  return {
    pending: { text: '待完成', color: 'bg-slate-700/60 text-slate-300 border-white/5' },
    in_progress: { text: '进行中', color: 'bg-blue-400/10 text-blue-300 border-blue-400/20' },
    completed: { text: '已完成', color: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/20' },
    failed: { text: '未完成', color: 'bg-rose-400/10 text-rose-300 border-rose-400/20' },
    deferred: { text: '已调整', color: 'bg-amber-400/10 text-amber-300 border-amber-400/20' },
  }[task.status];
}

function scheduleDetail(task: Task) {
  if (task.disposition === 'snoozed' && task.deferred_until) {
    return `将在 ${new Date(task.deferred_until).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} 自动恢复为待完成`;
  }
  if (task.disposition === 'excused') return task.disposition_reason || '今天不计入完成率，可随时恢复';
  if (task.disposition === 'rescheduled') {
    return `${task.original_scheduled_date ? `从 ${task.original_scheduled_date} ` : ''}改期至 ${task.scheduled_date}`;
  }
  if (task.disposition === 'expired') return '到期时仍未完成，已计入行为完成率';
  if (task.disposition === 'skipped') return '由你主动跳过，已计入行为完成率';
  return null;
}

export default function Tasks() {
  const [filter, setFilter] = useState('all');
  const [selectedDate, setSelectedDate] = useState(() => localDateKey(new Date()));
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [mode, setMode] = useState<ScheduleMode>('later');
  const [customTime, setCustomTime] = useState('');
  const [customDate, setCustomDate] = useState(tomorrowKey());
  const [reason, setReason] = useState('');
  const queryClient = useQueryClient();
  const { addNotification } = useNotification();

  const { data: tasks, isLoading, isError } = useQuery<Task[]>({
    queryKey: ['tasks', filter, selectedDate],
    queryFn: () => api.get('/tasks', { params: {
      ...(filter !== 'all' ? { dimension: filter } : {}),
      start_date: selectedDate,
      end_date: selectedDate,
    } }).then((r) => r.data),
  });

  const now = new Date();
  const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
  const canSnoozeOneHour = localDateKey(oneHourLater) === localDateKey(now);
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 0, 0);
  const canSnoozeToday = endOfToday > now;
  const tonight = new Date();
  tonight.setHours(20, 0, 0, 0);
  const canChooseTonight = tonight > now;
  const selectedIsToday = selectedTask?.scheduled_date === localDateKey(now);

  const filteredTasks = useMemo(() => tasks || [], [tasks]);
  const calendarDays = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const value = new Date();
    value.setDate(value.getDate() + index - 2);
    return { key: localDateKey(value), day: value.toLocaleDateString('zh-CN', { weekday: 'short' }), date: value.getDate() };
  }), []);

  const refreshTasks = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['today-tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['behavior-metrics'] }),
      queryClient.invalidateQueries({ queryKey: ['weekly-review'] }),
      queryClient.invalidateQueries({ queryKey: ['goals'] }),
      queryClient.invalidateQueries({ queryKey: ['goal-progress-summary'] }),
    ]);
  };

  const runTaskAction = async (taskId: string, request: () => Promise<unknown>, successMessage: string) => {
    setBusyId(taskId);
    try {
      await request();
      await refreshTasks();
      addNotification({ type: 'success', title: '任务已更新', message: successMessage, duration: 3500 });
      setSelectedTask(null);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      addNotification({ type: 'error', title: '操作失败', message: detail || '任务状态未改变，请稍后重试。' });
    } finally {
      setBusyId(null);
    }
  };

  const openSchedule = (task: Task) => {
    setSelectedTask(task);
    setMode(task.scheduled_date === localDateKey(now) && canSnoozeToday ? 'later' : 'reschedule');
    setCustomTime(toDateTimeLocal(canSnoozeOneHour ? oneHourLater : endOfToday));
    setCustomDate(tomorrowKey());
    setReason('');
  };

  const scheduleTask = (task: Task, payload: Record<string, unknown>, message: string) => runTaskAction(
    task.id,
    () => api.post(`/tasks/${task.id}/schedule`, payload),
    message,
  );

  const submitSchedule = async () => {
    if (!selectedTask) return;
    if (mode === 'later') {
      const wakeAt = new Date(customTime);
      if (Number.isNaN(wakeAt.getTime())) {
        addNotification({ type: 'error', title: '请选择时间', message: '需要一个今天晚于当前时刻的提醒时间。' });
        return;
      }
      await scheduleTask(selectedTask, { mode, deferred_until: wakeAt.toISOString(), reason: reason || undefined }, '已设置稍后提醒，到点会自动回到待完成。');
    } else if (mode === 'reschedule') {
      await scheduleTask(selectedTask, { mode, target_date: customDate, reason: reason || undefined }, `任务已改期至 ${customDate}。`);
    } else {
      await scheduleTask(selectedTask, { mode, reason: reason || undefined }, '已设为今日免做，不计入完成率。');
    }
  };

  const resumeTask = (task: Task) => runTaskAction(task.id, () => api.post(`/tasks/${task.id}/resume`), '已恢复为待完成。');

  const completeTask = (task: Task) => runTaskAction(task.id, () => api.post(`/tasks/${task.id}/complete`), '完成记录和连续打卡已同步。');

  const reopenTask = (task: Task) => runTaskAction(task.id, () => api.post(`/tasks/${task.id}/reopen`), '完成记录已撤销，任务和目标进度已恢复。');

  const feedbackTask = (taskId: string, feedback: 'too_easy' | 'just_right' | 'too_hard' | 'not_suitable') => runTaskAction(
    taskId,
    () => api.post(`/tasks/${taskId}/feedback`, { feedback }),
    '难度反馈已记录，将用于后续任务调整。',
  );

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-3xl">
        <div className="mb-6">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.24em] text-cyan-400">Adaptive Schedule</p>
          <h1 className="text-2xl font-bold text-white">任务列表</h1>
          <p className="mt-2 text-sm text-slate-500">任务做不了时，可以稍后提醒、改到未来日期，或仅今天免做。</p>
        </div>

        <div className="mb-6 flex flex-wrap gap-2">
          {['all', 'exercise', 'diet', 'sleep', 'appearance'].map((value) => (
            <button key={value} onClick={() => setFilter(value)}
              className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                filter === value ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/15' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}>
              {value === 'all' ? '全部' : dimensionLabels[value]}
            </button>
          ))}
        </div>

        <div className="mb-6 grid grid-cols-7 gap-1.5 rounded-2xl border border-white/5 bg-slate-900/40 p-2">
          {calendarDays.map((day) => <button key={day.key} type="button" onClick={() => setSelectedDate(day.key)} className={`rounded-xl px-1 py-2 text-center transition ${selectedDate === day.key ? 'bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-950/30' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}><span className="block text-[9px]">{day.day}</span><span className="mt-1 block text-sm font-semibold">{day.date}</span></button>)}
        </div>

        <div className="space-y-3">
          {isLoading && <p className="py-8 text-center text-sm text-slate-500">正在加载任务…</p>}
          {isError && <p className="py-8 text-center text-sm text-rose-300">任务加载失败，请刷新页面重试。</p>}
          {!isLoading && !isError && filteredTasks.length === 0 && <p className="py-8 text-center text-slate-500">暂无任务</p>}
          {filteredTasks.map((task, index) => {
            const status = getStatus(task);
            const detail = scheduleDetail(task);
            const actionable = task.status === 'pending' || task.status === 'in_progress';
            const adaptation = task.adaptation_metadata;
            const adaptationReasons = Array.isArray(adaptation?.reasons) ? adaptation.reasons as string[] : [];
            const signals = adaptation?.signals as { adherence?: number; adjustment_rate?: number; too_hard?: number; too_easy?: number } | undefined;
            return (
              <motion.article key={task.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }} whileHover={{ y: -2 }}
                className={`task-depth-card task-depth-${task.dimension} lift-surface group overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-4 transition-colors hover:border-slate-700`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium leading-6 text-white">{task.title}</div>
                    <div className="mt-1 text-sm text-slate-500">
                      {dimensionLabels[task.dimension]} · {difficultyLabels[task.difficulty]}
                      {task.estimated_minutes ? ` · ${task.estimated_minutes} 分钟` : ''}
                    </div>
                    {task.why && task.why.length > 0 ? (
                      <div className="mt-3 rounded-xl border border-cyan-400/10 bg-cyan-400/[0.035] px-3 py-2.5">
                        <ul className="space-y-1 text-xs leading-5 text-slate-400">
                          {task.why.map((item) => <li key={item} className="flex gap-1.5"><span className="text-cyan-400">·</span><span>{item}</span></li>)}
                        </ul>
                      </div>
                    ) : task.rationale ? <p className="mt-2 text-xs leading-5 text-slate-600">{task.rationale}</p> : null}
                    {String(adaptation?.version || '').startsWith('adaptive-v2') && (
                      <details className="mt-2 text-[10px] text-slate-600">
                        <summary className="cursor-pointer select-none text-cyan-400/70">查看自适应依据</summary>
                        <div className="mt-2 rounded-lg border border-white/5 bg-slate-950/40 px-3 py-2 leading-5">
                          {adaptationReasons.length > 0 && <p>{adaptationReasons.join(' · ')}</p>}
                          <p className="text-slate-700">
                            近期完成率 {Math.round((signals?.adherence ?? 0.6) * 100)}% · 调整率 {Math.round((signals?.adjustment_rate ?? 0) * 100)}%
                            {(signals?.too_hard || 0) > 0 ? ` · 太难反馈 ${signals?.too_hard}` : ''}
                            {(signals?.too_easy || 0) > 0 ? ` · 太简单反馈 ${signals?.too_easy}` : ''}
                          </p>
                        </div>
                      </details>
                    )}
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-600"><span>{task.scheduled_date}{task.scheduled_time ? ` · ${task.scheduled_time}` : ''}</span>{task.goal_id && <span className="text-cyan-400/70">来自成长目标</span>}</div>
                  </div>
                  <span className={`flex-shrink-0 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs ${status.color}`}>{status.text}</span>
                </div>

                {detail && (
                  <div className="mt-3 flex items-start gap-2 rounded-xl border border-white/5 bg-white/[0.025] px-3 py-2 text-xs leading-5 text-slate-400">
                    <span className="mt-0.5 text-cyan-400">◷</span><span>{detail}</span>
                  </div>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
                  {actionable && (
                    <button type="button" disabled={busyId === task.id} onClick={() => void completeTask(task)}
                      className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-[11px] font-medium text-emerald-300 transition hover:bg-emerald-400/15 disabled:opacity-50">
                      标记完成
                    </button>
                  )}
                  {actionable && (
                    <button type="button" disabled={busyId === task.id} onClick={() => openSchedule(task)}
                      className="rounded-lg border border-cyan-400/20 bg-cyan-400/5 px-3 py-1.5 text-[11px] text-cyan-300 transition hover:bg-cyan-400/10 disabled:opacity-50">
                      调整安排
                    </button>
                  )}
                  {task.status === 'deferred' && task.scheduled_date === localDateKey(now) && (
                    <button type="button" disabled={busyId === task.id} onClick={() => void resumeTask(task)}
                      className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-3 py-1.5 text-[11px] text-emerald-300 transition hover:bg-emerald-400/10 disabled:opacity-50">
                      现在继续做
                    </button>
                  )}
                  {task.status === 'completed' && task.scheduled_date === localDateKey(now) && (
                    <button type="button" disabled={busyId === task.id} onClick={() => void reopenTask(task)}
                      className="rounded-lg border border-amber-400/15 bg-amber-400/5 px-3 py-1.5 text-[11px] text-amber-300 transition hover:bg-amber-400/10 disabled:opacity-50">
                      撤销完成
                    </button>
                  )}
                  <span className="ml-auto text-[10px] text-slate-600">难度反馈</span>
                  {([
                    ['too_easy', '太简单'], ['just_right', '正合适'], ['too_hard', '太难'], ['not_suitable', '不适合'],
                  ] as const).map(([value, label]) => (
                    <button key={value} type="button" disabled={busyId === task.id} onClick={() => void feedbackTask(task.id, value)}
                      className={`rounded-lg px-2 py-1 text-[10px] transition ${task.user_feedback === value ? 'bg-cyan-400/15 text-cyan-300' : 'bg-slate-800 text-slate-500 hover:text-slate-300'}`}>{label}</button>
                  ))}
                </div>
              </motion.article>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {selectedTask && (
          <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={() => setSelectedTask(null)}>
            <motion.div initial={{ opacity: 0, y: 22, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.98 }}
              onMouseDown={(event) => event.stopPropagation()}
              className="w-full max-w-xl overflow-hidden rounded-2xl border border-cyan-400/15 bg-slate-900 shadow-2xl shadow-cyan-950/30">
              <div className="border-b border-white/5 bg-gradient-to-r from-cyan-400/5 to-violet-400/5 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-cyan-400">Adjust schedule</p>
                    <h2 className="mt-2 text-lg font-semibold text-white">这项任务怎么安排？</h2>
                    <p className="mt-2 line-clamp-2 text-sm leading-5 text-slate-400">{selectedTask.title}</p>
                  </div>
                  <button onClick={() => setSelectedTask(null)} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white">×</button>
                </div>
              </div>

              <div className="p-5">
                <div className="grid grid-cols-3 gap-2">
                  {selectedIsToday && (
                    <button onClick={() => setMode('later')} className={`rounded-xl border p-3 text-left transition ${mode === 'later' ? 'border-cyan-400/35 bg-cyan-400/10 text-cyan-200' : 'border-white/5 bg-slate-950/40 text-slate-400'}`}>
                      <span className="block text-sm font-medium">稍后再做</span><span className="mt-1 block text-[10px] opacity-70">到点自动恢复</span>
                    </button>
                  )}
                  <button onClick={() => setMode('reschedule')} className={`rounded-xl border p-3 text-left transition ${mode === 'reschedule' ? 'border-violet-400/35 bg-violet-400/10 text-violet-200' : 'border-white/5 bg-slate-950/40 text-slate-400'}`}>
                    <span className="block text-sm font-medium">改到别天</span><span className="mt-1 block text-[10px] opacity-70">移动任务日期</span>
                  </button>
                  {selectedIsToday && (
                    <button onClick={() => setMode('excuse')} className={`rounded-xl border p-3 text-left transition ${mode === 'excuse' ? 'border-amber-400/35 bg-amber-400/10 text-amber-200' : 'border-white/5 bg-slate-950/40 text-slate-400'}`}>
                      <span className="block text-sm font-medium">今日免做</span><span className="mt-1 block text-[10px] opacity-70">不计入完成率</span>
                    </button>
                  )}
                </div>

                {mode === 'later' && selectedIsToday && (
                  <div className="mt-5 space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <button disabled={!canSnoozeOneHour} onClick={() => void scheduleTask(selectedTask, { mode: 'later', deferred_until: oneHourLater.toISOString() }, '一小时后会自动恢复为待完成。')}
                        className="rounded-xl border border-white/5 bg-slate-950/50 p-3 text-left text-sm text-slate-300 transition hover:border-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-35">1 小时后</button>
                      <button disabled={!canChooseTonight} onClick={() => void scheduleTask(selectedTask, { mode: 'later', deferred_until: tonight.toISOString() }, '今晚 20:00 会自动恢复为待完成。')}
                        className="rounded-xl border border-white/5 bg-slate-950/50 p-3 text-left text-sm text-slate-300 transition hover:border-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-35">今晚 20:00</button>
                    </div>
                    <label className="block text-xs text-slate-500">自定义今天的提醒时间
                      <input type="datetime-local" min={toDateTimeLocal(now)} max={toDateTimeLocal(endOfToday)} value={customTime} onChange={(event) => setCustomTime(event.target.value)}
                        className="mt-2 w-full rounded-xl border border-white/5 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-cyan-400/30" />
                    </label>
                  </div>
                )}

                {mode === 'reschedule' && (
                  <div className="mt-5">
                    <label className="block text-xs text-slate-500">新的任务日期
                      <input type="date" min={tomorrowKey()} value={customDate} onChange={(event) => setCustomDate(event.target.value)}
                        className="mt-2 w-full rounded-xl border border-white/5 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-violet-400/30" />
                    </label>
                  </div>
                )}

                {mode === 'excuse' && (
                  <div className="mt-5 rounded-xl border border-amber-400/10 bg-amber-400/5 p-3 text-xs leading-5 text-amber-100/70">
                    今天将不再提醒，也不会算作完成或未完成。若这类情况经常出现，系统会降低后续任务难度。
                  </div>
                )}

                <label className="mt-4 block text-xs text-slate-500">原因（选填）
                  <input value={reason} maxLength={200} onChange={(event) => setReason(event.target.value)} placeholder="例如：今晚临时加班"
                    className="mt-2 w-full rounded-xl border border-white/5 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-200 outline-none placeholder:text-slate-700 focus:border-cyan-400/30" />
                </label>

                <div className="mt-5 flex justify-end gap-2">
                  <button onClick={() => setSelectedTask(null)} className="rounded-xl px-4 py-2 text-sm text-slate-500 hover:text-slate-300">取消</button>
                  <button disabled={busyId === selectedTask.id} onClick={() => void submitSchedule()}
                    className="rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-950/30 transition hover:brightness-110 disabled:opacity-50">
                    {busyId === selectedTask.id ? '正在保存…' : '确认安排'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
