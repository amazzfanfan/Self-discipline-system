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

interface SkinAnalysisData {
  source: string;
  sourceDisplay: string;
  skinType: string;
  skinScore?: number;
  scoreLabel: string;
  issues: string[];
  suggestions: string[];
  suggestionsError?: string;
  error?: string;
  cached?: boolean;
  photoRetained: boolean;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function skinFromMetadata(message: Conversation): SkinAnalysisData | null {
  if (message.metadata?.message_type !== 'skin_analysis') return null;
  const skin = objectValue(message.metadata.skin_analysis);
  if (!skin) return null;
  return {
    source: typeof skin.source === 'string' ? skin.source : 'unavailable',
    sourceDisplay: typeof skin.source_display === 'string' ? skin.source_display : 'Face++',
    skinType: typeof skin.skin_type_name === 'string' ? skin.skin_type_name : '暂未确认',
    skinScore: typeof skin.skin_score === 'number' ? skin.skin_score : undefined,
    scoreLabel: typeof skin.score_label === 'string' ? skin.score_label : '日常肤质状态分（系统换算）',
    issues: stringList(skin.issues),
    suggestions: stringList(skin.suggestions),
    suggestionsError: typeof skin.suggestions_error === 'string' ? skin.suggestions_error : undefined,
    error: typeof skin.error === 'string' ? skin.error : undefined,
    cached: skin.cached === true,
    photoRetained: skin.photo_retained === true,
  };
}

function skinFromLegacyContent(content: string): SkinAnalysisData | null {
  if (!content.includes('【肤质分析报告】')) return null;
  const sourceDisplay = content.match(/分析方式[：:]\s*([^\n]+)/)?.[1]?.trim() ?? 'Face++';
  const scoreMatch = content.match(/(?:肤质评分|日常肤质状态分（系统换算）)[：:]\s*(\d+(?:\.\d+)?)/);
  const issueText = content.match(/存在问题[：:]\s*([^\n]+)/)?.[1] ?? '';
  const adviceBlock = content.split('【护理建议】')[1] ?? '';
  const suggestions = adviceBlock
    .split('\n')
    .map((line) => line.replace(/^\s*\d+[.、]\s*/, '').trim())
    .filter((line) => line && !line.includes('暂时不可用') && !line.includes('暂未生成'));
  const source = sourceDisplay.includes('外部API')
    ? 'faceplusplus'
    : sourceDisplay.includes('不完整') ? 'faceplusplus_incomplete' : 'unavailable';
  const fallbackError = content
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.includes('未获得') || line.includes('字段不完整'));
  return {
    source,
    sourceDisplay,
    skinType: content.match(/皮肤类型[：:]\s*([^\n]+)/)?.[1]?.trim() ?? '暂未确认',
    skinScore: scoreMatch ? Number(scoreMatch[1]) : undefined,
    scoreLabel: content.includes('系统换算') ? '日常肤质状态分（系统换算）' : '日常肤质状态分（历史系统换算）',
    issues: issueText.split(/[,，、]/).map((item) => item.trim()).filter(Boolean),
    suggestions,
    error: fallbackError,
    photoRetained: false,
  };
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
  const skinScore = Number(content.match(/(?:肤质评分|日常肤质状态分（系统换算）)[：:]\s*(\d+(?:\.\d+)?)/)?.[1]);
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
              <div className="text-right"><span className="text-2xl font-semibold text-emerald-200">{Math.round(data.skinScore)}</span><span className="text-[9px] text-slate-500"> /100</span><p className="mt-0.5 text-[8px] text-slate-600">系统换算</p></div>
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

function SkinAnalysisCard({ data }: { data: SkinAnalysisData }) {
  const available = data.source === 'faceplusplus' && data.skinScore != null;
  return (
    <div className="w-[min(680px,82vw)] overflow-hidden rounded-[24px] border border-emerald-300/15 bg-slate-950/90 shadow-[0_24px_90px_rgba(2,8,23,.48)]">
      <div className="relative overflow-hidden border-b border-white/[0.07] bg-gradient-to-r from-emerald-400/[0.12] via-cyan-400/[0.07] to-transparent px-5 py-4">
        <div className="absolute -right-10 -top-20 h-44 w-44 rounded-full bg-emerald-300/10 blur-3xl" />
        <div className="relative flex items-center justify-between gap-4">
          <div>
            <p className="text-[9px] uppercase tracking-[0.22em] text-emerald-300/70">Face++ skin insight</p>
            <h3 className="mt-1 text-base font-semibold text-white">肤质日常观察</h3>
            <p className="mt-1 text-[10px] text-slate-500">{data.sourceDisplay}{data.cached === true ? ' · 同图结果复用' : data.cached === false ? ' · 本次实时分析' : ' · 历史分析记录'}</p>
          </div>
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-emerald-300/20 bg-emerald-400/10 text-emerald-200">
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
              <path d="M8.5 10.5h.01M15.5 10.5h.01M9 15c1.6 1.25 4.4 1.25 6 0" />
            </svg>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-5">
        {available ? (
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <div className="rounded-2xl border border-white/[0.065] bg-white/[0.03] p-4">
              <p className="text-[10px] text-slate-500">肤质类型</p>
              <p className="mt-1.5 text-lg font-semibold text-white">{data.skinType}</p>
              <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                {data.issues.length ? `Face++ 标记了 ${data.issues.length} 项日常观察点` : 'Face++ 本次未标记明显问题'}
              </p>
            </div>
            <div className="min-w-[150px] rounded-2xl border border-emerald-300/15 bg-emerald-400/[0.055] p-4 sm:text-right">
              <p className="text-[9px] leading-relaxed text-emerald-200/65">{data.scoreLabel}</p>
              <div className="mt-2 flex items-end gap-1 sm:justify-end"><span className="text-3xl font-semibold text-emerald-100">{Math.round(data.skinScore!)}</span><span className="pb-1 text-[10px] text-slate-500">/100</span></div>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-amber-300/15 bg-amber-400/[0.055] p-4">
            <p className="text-xs font-medium text-amber-100">本次没有生成状态分</p>
            <p className="mt-1.5 text-[10px] leading-relaxed text-slate-400">{data.error || 'Face++ 服务暂时不可用，请稍后重试。'}</p>
          </div>
        )}

        {available && data.issues.length > 0 && (
          <div className="mt-3 rounded-2xl border border-white/[0.06] bg-white/[0.025] p-4">
            <p className="text-[10px] font-medium text-slate-300">观察项</p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">{data.issues.map((issue) => <span key={issue} className="rounded-full border border-amber-300/10 bg-amber-400/[0.07] px-2.5 py-1 text-[9px] text-amber-100/80">{issue}</span>)}</div>
          </div>
        )}

        {data.suggestions.length > 0 && (
          <div className="mt-3 rounded-2xl border border-violet-300/10 bg-violet-400/[0.035] p-4">
            <p className="text-[10px] font-medium text-violet-100">✦ AI 个性化护理建议</p>
            <div className="mt-3 space-y-2.5">{data.suggestions.map((suggestion, index) => <div key={`${index}-${suggestion}`} className="flex gap-3 text-[11px] leading-relaxed text-slate-300"><span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-lg bg-violet-400/10 text-[9px] text-violet-300">{index + 1}</span><span>{suggestion}</span></div>)}</div>
          </div>
        )}

        {data.suggestionsError && data.issues.length > 0 && (
          <p className="mt-3 rounded-xl border border-amber-300/10 bg-amber-400/[0.04] px-3 py-2 text-[9px] leading-relaxed text-amber-100/65">{data.suggestionsError}</p>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-3 text-[9px] leading-relaxed text-slate-600">
          <span>仅供日常护理参考，不属于医学诊断。</span>
          <span className="text-emerald-300/55">{data.photoRetained ? '原图按隐私设置保存' : '原图已在分析后删除'}</span>
        </div>
      </div>
    </div>
  );
}

export default function ChatInsightCards({ message }: { message: Conversation }) {
  const skin = skinFromMetadata(message) ?? skinFromLegacyContent(message.content);
  if (skin) return <SkinAnalysisCard data={skin} />;
  const profile = profileFromMetadata(message) ?? profileFromLegacyContent(message.content);
  if (profile) return <ProfileAssessmentCard data={profile} />;
  const tasks = tasksFromMetadata(message) ?? tasksFromLegacyContent(message.content);
  if (tasks) return <DailyTasksCard data={tasks} />;
  return null;
}
