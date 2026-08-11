import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import type { Conversation, Dimension } from '../types';

const dimensionMeta: Record<Dimension, { label: string; icon: string; color: string }> = {
  exercise: { label: '运动状态', icon: '↗', color: 'from-cyan-400 to-blue-500' },
  diet: { label: '饮食习惯', icon: '◒', color: 'from-emerald-400 to-teal-500' },
  sleep: { label: '睡眠状态', icon: '☾', color: 'from-violet-400 to-indigo-500' },
  appearance: { label: '形象管理', icon: '✦', color: 'from-fuchsia-400 to-violet-500' },
};

const labelToDimension: Record<string, Dimension> = {
  运动: 'exercise', 运动状态: 'exercise', 饮食: 'diet', 饮食习惯: 'diet',
  睡眠: 'sleep', 睡眠状态: 'sleep', 形象: 'appearance', 形象管理: 'appearance',
};

interface ProfileCardData {
  scores: Partial<Record<Dimension, number>>;
  focus?: Dimension;
  skinType?: string;
  skinScore?: number;
  issues: string[];
  suggestions: string[];
}

interface DailyTaskData {
  greeting: string;
  tasks: Array<{ dimension: Dimension; title: string; difficulty: string }>;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function profileFromMetadata(message: Conversation): ProfileCardData | null {
  const metadata = message.metadata;
  if (metadata?.message_type !== 'profile_assessment') return null;
  const assessment = objectValue(metadata.assessment);
  const rawScores = objectValue(assessment?.scores);
  const skin = objectValue(metadata.skin_analysis);
  const scores: Partial<Record<Dimension, number>> = {};
  (Object.keys(dimensionMeta) as Dimension[]).forEach((dimension) => {
    const value = rawScores?.[dimension];
    if (typeof value === 'number') scores[dimension] = value;
  });
  const focus = typeof assessment?.focus_dimension === 'string'
    ? assessment.focus_dimension as Dimension
    : undefined;
  return {
    scores,
    focus,
    skinType: typeof skin?.skin_type_name === 'string' ? skin.skin_type_name : undefined,
    skinScore: typeof skin?.skin_score === 'number' ? skin.skin_score : undefined,
    issues: stringList(skin?.issues),
    suggestions: stringList(metadata.care_suggestions),
  };
}

function profileFromLegacyContent(content: string): ProfileCardData | null {
  if (!content.includes('【状态基线】')) return null;
  const scores: Partial<Record<Dimension, number>> = {};
  for (const match of content.matchAll(/(?:^|\n)[-•]?\s*(运动状态|饮食习惯|睡眠状态|形象管理)[：:]\s*(\d+(?:\.\d+)?)/g)) {
    scores[labelToDimension[match[1]]] = Number(match[2]);
  }
  const focusMatch = content.match(/优先关注[：:]?\s*(运动状态|饮食习惯|睡眠状态|形象管理)/);
  const skinType = content.match(/皮肤类型[：:]\s*([^\n]+)/)?.[1]?.trim();
  const skinScore = Number(content.match(/肤质评分[：:]\s*(\d+(?:\.\d+)?)/)?.[1]);
  const issuesText = content.match(/观察项[：:]\s*([^\n]+)/)?.[1] ?? '';
  const adviceBlock = content.split('【日常护理建议】')[1] ?? '';
  const suggestions = adviceBlock
    .split('\n')
    .map((line) => line.replace(/^\s*\d+[.、]\s*/, '').trim())
    .filter(Boolean);
  return {
    scores,
    focus: focusMatch ? labelToDimension[focusMatch[1]] : undefined,
    skinType,
    skinScore: Number.isFinite(skinScore) ? skinScore : undefined,
    issues: issuesText.split(/[,，、]/).map((item) => item.trim()).filter(Boolean),
    suggestions,
  };
}

function tasksFromMetadata(message: Conversation): DailyTaskData | null {
  const metadata = message.metadata;
  if (metadata?.message_type !== 'daily_tasks' || !Array.isArray(metadata.tasks)) return null;
  const tasks = metadata.tasks.flatMap((value) => {
    const task = objectValue(value);
    if (!task || typeof task.dimension !== 'string' || typeof task.title !== 'string') return [];
    return [{
      dimension: task.dimension as Dimension,
      title: task.title,
      difficulty: typeof task.difficulty === 'string' ? task.difficulty : 'medium',
    }];
  });
  return {
    greeting: typeof metadata.greeting === 'string' ? metadata.greeting : '今日任务已发布',
    tasks,
  };
}

function tasksFromLegacyContent(content: string): DailyTaskData | null {
  if (!content.includes('今日任务已发布')) return null;
  const tasks: DailyTaskData['tasks'] = [];
  for (const match of content.matchAll(/\*\*【(运动|饮食|睡眠|形象管理)】\*\*\s*(.+?)（(简单|中等|困难)）/g)) {
    tasks.push({
      dimension: labelToDimension[match[1]],
      title: match[2].trim(),
      difficulty: ({ 简单: 'easy', 中等: 'medium', 困难: 'hard' } as Record<string, string>)[match[3]],
    });
  }
  const greeting = content.match(/^(.+?)！今日任务已发布/)?.[1] ?? '今日任务已发布';
  return tasks.length ? { greeting, tasks } : null;
}

function ScoreCard({ dimension, score, focus }: { dimension: Dimension; score: number; focus: boolean }) {
  const meta = dimensionMeta[dimension];
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative overflow-hidden rounded-2xl border p-3.5 ${focus ? 'border-violet-400/30 bg-violet-400/[0.08]' : 'border-white/[0.07] bg-white/[0.035]'}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-slate-400">{meta.icon} {meta.label}</span>
        {focus && <span className="rounded-full bg-violet-400/15 px-2 py-0.5 text-[8px] text-violet-200">优先关注</span>}
      </div>
      <div className="mt-2 flex items-end gap-1"><span className="text-2xl font-semibold text-white">{score.toFixed(1)}</span><span className="pb-1 text-[9px] text-slate-600">/ 100</span></div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-800">
        <motion.div initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ duration: 0.75 }} className={`h-full rounded-full bg-gradient-to-r ${meta.color}`} />
      </div>
    </motion.div>
  );
}

function ProfileAssessmentCard({ data }: { data: ProfileCardData }) {
  return (
    <div className="overflow-hidden rounded-[24px] border border-cyan-300/15 bg-slate-950/85 shadow-[0_24px_80px_rgba(2,8,23,.45)]">
      <div className="relative overflow-hidden border-b border-white/[0.07] px-5 py-5">
        <div className="absolute -right-10 -top-16 h-40 w-40 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative flex items-center justify-between gap-4">
          <div><p className="text-[9px] uppercase tracking-[0.24em] text-cyan-300/70">Initial portrait</p><h3 className="mt-1 text-lg font-semibold text-white">你的初始状态画像</h3><p className="mt-1 text-[11px] text-slate-500">结构化问卷 · 固定评分规则 · 可持续追踪</p></div>
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-400/10 text-xl text-cyan-200">◇</div>
        </div>
      </div>
      <div className="p-4 md:p-5">
        <div className="grid grid-cols-2 gap-2.5">
          {(Object.entries(data.scores) as Array<[Dimension, number]>).map(([dimension, score]) => (
            <ScoreCard key={dimension} dimension={dimension} score={score} focus={data.focus === dimension} />
          ))}
        </div>
        {data.skinScore != null && (
          <div className="mt-3 rounded-2xl border border-emerald-300/15 bg-gradient-to-br from-emerald-400/[0.07] to-cyan-400/[0.04] p-4">
            <div className="flex items-start justify-between gap-4">
              <div><p className="text-[9px] uppercase tracking-[0.18em] text-emerald-300/70">Face++ skin insight</p><h4 className="mt-1 text-sm font-medium text-white">{data.skinType ?? '肤质'} · 日常观察</h4></div>
              <div className="text-right"><span className="text-2xl font-semibold text-emerald-200">{Math.round(data.skinScore)}</span><span className="text-[9px] text-slate-500"> /100</span></div>
            </div>
            {data.issues.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{data.issues.map((issue) => <span key={issue} className="rounded-full border border-white/[0.07] bg-black/10 px-2.5 py-1 text-[9px] text-slate-300">{issue}</span>)}</div>}
            <p className="mt-3 text-[9px] leading-relaxed text-slate-600">仅用于日常护理参考，不属于医学诊断，也不参与运动、饮食与睡眠评分。</p>
          </div>
        )}
        {data.suggestions.length > 0 && (
          <div className="mt-3 rounded-2xl border border-violet-300/10 bg-violet-400/[0.035] p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-medium text-violet-100"><span className="text-violet-300">✦</span> AI 日常护理建议</div>
            <div className="space-y-2.5">{data.suggestions.slice(0, 3).map((suggestion, index) => <div key={`${index}-${suggestion}`} className="flex gap-3 text-[11px] leading-relaxed text-slate-300"><span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-lg bg-violet-400/10 text-[9px] text-violet-300">{index + 1}</span><span>{suggestion}</span></div>)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function DailyTasksCard({ data }: { data: DailyTaskData }) {
  const difficultyLabel: Record<string, string> = { easy: '轻量', medium: '适中', hard: '进阶' };
  return (
    <div className="overflow-hidden rounded-[24px] border border-violet-300/15 bg-slate-950/85 shadow-[0_24px_80px_rgba(2,8,23,.4)]">
      <div className="flex items-center justify-between border-b border-white/[0.07] bg-gradient-to-r from-violet-500/[0.12] to-cyan-400/[0.06] px-5 py-4">
        <div><p className="text-[9px] uppercase tracking-[0.2em] text-violet-300/70">Daily mission</p><h3 className="mt-1 text-base font-semibold text-white">{data.greeting}，今日任务已发布</h3></div>
        <motion.div animate={{ rotate: [0, 8, -8, 0] }} transition={{ delay: 0.4, duration: 0.8 }} className="text-2xl">🚀</motion.div>
      </div>
      <div className="space-y-2.5 p-4">
        {data.tasks.map((task, index) => {
          const meta = dimensionMeta[task.dimension] ?? dimensionMeta.exercise;
          return <motion.div key={`${task.dimension}-${task.title}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * 0.08 }} className="group flex gap-3 rounded-2xl border border-white/[0.065] bg-white/[0.03] p-3.5 transition-colors hover:border-cyan-300/15 hover:bg-cyan-300/[0.035]">
            <div className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${meta.color} text-sm text-slate-950 shadow-lg`}>{meta.icon}</div>
            <div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-medium text-slate-400">{meta.label}</span><span className="rounded-full bg-white/[0.05] px-2 py-0.5 text-[8px] text-slate-500">{difficultyLabel[task.difficulty] ?? task.difficulty}</span></div><p className="mt-1.5 text-xs leading-relaxed text-slate-200">{task.title}</p></div>
          </motion.div>;
        })}
        <div className="flex items-center justify-between px-1 pt-2"><p className="text-[9px] text-slate-600">完成后在对话中告诉我，我会真实记录进度。</p><Link to="/tasks" className="text-[10px] font-medium text-cyan-300 hover:text-cyan-200">查看任务 →</Link></div>
      </div>
    </div>
  );
}

export default function ChatInsightCards({ message }: { message: Conversation }) {
  const profile = profileFromMetadata(message) ?? profileFromLegacyContent(message.content);
  if (profile) return <ProfileAssessmentCard data={profile} />;
  const tasks = tasksFromMetadata(message) ?? tasksFromLegacyContent(message.content);
  if (tasks) return <DailyTasksCard data={tasks} />;
  return null;
}
