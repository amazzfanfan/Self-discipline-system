import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { motion } from 'framer-motion';
import api from '../services/api';
import BehaviorDeck from '../components/BehaviorDeck';
import DepthPanel from '../components/DepthPanel';
import type { BehaviorMetrics, Dimension, ScoreHistory, UserScore } from '../types';

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

  const { data: behaviorMetrics } = useQuery<BehaviorMetrics>({
    queryKey: ['behavior-metrics'],
    queryFn: () => api.get('/behavior/metrics').then((response) => response.data),
  });

  // Build chart data
  const chartData = [...(history ?? [])].reverse().map((h, i) => ({
    index: i + 1,
    [h.dimension]: h.delta,
    date: new Date(h.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
  }));

  const trackedDimensions = (Object.entries(DIM_LABELS) as Array<[Dimension, string]>).map(([dimension, label]) => ({
    dimension,
    label,
    metric: behaviorMetrics?.dimensions[dimension],
  }));
  const populatedDimensions = trackedDimensions.filter((item) => item.metric?.momentum != null);
  const focusDimension = [...populatedDimensions]
    .sort((a, b) => (a.metric?.momentum ?? 0) - (b.metric?.momentum ?? 0))[0];
  const confidenceLabels = { none: '等待样本', low: '低', medium: '中', high: '高' };

  return (
    <div className="h-full overflow-y-auto p-6 scrollbar-hide">
      <div className="mx-auto max-w-5xl">
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.25em] text-cyan-400">Behavior Observatory</p>
          <h1 className="text-2xl font-bold text-white">状态基线与行为趋势</h1>
          <p className="mt-2 text-sm text-slate-500">把稳定画像与可变化的执行表现分开观察，避免一次行为制造虚假的评分波动。</p>
        </motion.div>

        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          {scores?.map((score, index) => {
            const metric = behaviorMetrics?.dimensions[score.dimension];
            return (
              <motion.div key={score.dimension} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }}
                className="lift-surface rounded-2xl border border-white/[0.07] bg-slate-900/75 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-500">{DIM_LABELS[score.dimension]}</span>
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: DIM_COLORS[score.dimension] }} />
                </div>
                <div className="mt-3 text-2xl font-semibold" style={{ color: DIM_COLORS[score.dimension] }}>{score.score.toFixed(1)}</div>
                <div className="mt-2 flex items-center justify-between text-[9px] text-slate-600">
                  <span>稳定基线</span><span>动量 {metric?.momentum ?? '—'}</span>
                </div>
              </motion.div>
            );
          })}
        </div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mb-5">
          <DepthPanel className="rounded-[26px]" glow="rgba(139, 92, 246, 0.15)">
            <div className="grid gap-6 p-5 md:grid-cols-[0.78fr_1.22fr] md:p-7">
              <div className="flex flex-col justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-violet-300/75">Execution Depth</p>
                  <h2 className="mt-2 text-xl font-semibold text-white">行为成长甲板</h2>
                  <p className="mt-2 text-xs leading-5 text-slate-500">柱体高度只表达行为动量，不代表健康程度或能力评分。</p>
                </div>
                <div className="mt-6 grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-white/[0.06] bg-slate-950/35 p-3">
                    <p className="text-[9px] text-slate-600">近 7 天完成率</p>
                    <p className="mt-1 text-xl font-semibold text-cyan-300">{behaviorMetrics?.overall.adherence_7d == null ? '—' : `${behaviorMetrics.overall.adherence_7d}%`}</p>
                  </div>
                  <div className="rounded-xl border border-white/[0.06] bg-slate-950/35 p-3">
                    <p className="text-[9px] text-slate-600">数据置信度</p>
                    <p className="mt-1 text-xl font-semibold text-violet-300">{confidenceLabels[behaviorMetrics?.overall.confidence ?? 'none']}</p>
                  </div>
                </div>
                <p className="mt-4 text-[10px] leading-5 text-slate-600">
                  {populatedDimensions.length >= 2 && focusDimension
                    ? `当前可优先关注：${focusDimension.label}。建议结合任务难度反馈继续积累样本。`
                    : populatedDimensions.length === 1
                      ? `当前仅${populatedDimensions[0].label}形成有效样本，其他维度积累数据后再进行横向比较。`
                      : '完成或明确跳过任务后，这里会逐步形成可靠的行为趋势。'}
                </p>
              </div>
              <BehaviorDeck metrics={behaviorMetrics} />
            </div>
          </DepthPanel>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
          <DepthPanel className="rounded-[24px] p-5 lg:p-6" glow="rgba(59, 130, 246, 0.11)" interactive={false}>
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-600">Baseline History</p>
                <h2 className="mt-1 text-base font-semibold text-slate-200">评分变动历史</h2>
              </div>
              <span className="rounded-full border border-white/[0.06] bg-white/[0.025] px-3 py-1 text-[9px] text-slate-600">规则重评时更新</span>
            </div>
            {chartData.length === 0 ? (
              <div className="flex min-h-[150px] flex-col items-center justify-center rounded-2xl border border-dashed border-white/[0.07] bg-slate-950/20 px-6 text-center">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl border border-cyan-400/10 bg-cyan-400/[0.04] text-cyan-400/50">◇</div>
                <p className="text-sm text-slate-400">稳定基线暂未发生重评变化</p>
                <p className="mt-2 max-w-lg text-[10px] leading-5 text-slate-600">日常完成、跳过与改期只进入上方行为甲板；重新填写结构化问卷后才会留下新的基线记录。</p>
              </div>
            ) : <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12 }} />
                <Legend />
                {Object.entries(DIM_COLORS).map(([dimension, color]) => (
                  <Line key={dimension} name={DIM_LABELS[dimension]} type="monotone" dataKey={dimension} stroke={color} strokeWidth={2} connectNulls dot={{ r: 3 }} />
                ))}
              </LineChart>
            </ResponsiveContainer>}
          </DepthPanel>
        </motion.div>
      </div>
    </div>
  );
}
