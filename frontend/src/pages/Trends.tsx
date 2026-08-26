import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { motion } from 'framer-motion';
import api from '../services/api';
import BehaviorDeck from '../components/BehaviorDeck';
import DepthPanel from '../components/DepthPanel';
import type { BehaviorMetrics, Dimension, ScoreHistory, UserScore, WeightHistoryResponse } from '../types';

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
  const queryClient = useQueryClient();
  const [weightInput, setWeightInput] = useState('');
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

  const { data: weightHistory } = useQuery<WeightHistoryResponse>({
    queryKey: ['weight-history'],
    queryFn: () => api.get('/weight/history?limit=90').then((response) => response.data),
  });

  const recordWeight = useMutation({
    mutationFn: (weight_kg: number) => api.post('/weight', { weight_kg }),
    onSuccess: async () => {
      setWeightInput('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['weight-history'] }),
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
        queryClient.invalidateQueries({ queryKey: ['goals'] }),
        queryClient.invalidateQueries({ queryKey: ['goal-progress-summary'] }),
      ]);
    },
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
  const weightDelta = weightHistory?.summary.change_7d;
  const formatDelta = (value: number | null | undefined) => value == null ? '样本不足' : `${value > 0 ? '+' : ''}${value.toFixed(1)} kg`;

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

        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="mb-5">
          <DepthPanel className="rounded-[24px] p-5 lg:p-6" glow="rgba(16, 185, 129, 0.12)" interactive={false}>
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-emerald-300/60">Weight Trend</p>
                <h2 className="mt-1 text-base font-semibold text-slate-200">体重记录与平滑趋势</h2>
                <p className="mt-1 text-[10px] text-slate-600">聊天、个人画像与这里的记录会同步到同一份每日数据；体重目标也会自动更新。</p>
              </div>
              <form
                className="flex items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const value = Number(weightInput);
                  if (value > 20 && value < 300) recordWeight.mutate(value);
                }}
              >
                <input aria-label="今日体重" type="number" min="20.1" max="299.9" step="0.1" value={weightInput} onChange={(event) => setWeightInput(event.target.value)} placeholder="今日体重 kg" className="w-32 rounded-xl border border-white/[0.07] bg-slate-950/60 px-3 py-2 text-xs text-white outline-none focus:border-emerald-400/30" />
                <button type="submit" disabled={recordWeight.isPending || !weightInput} className="rounded-xl bg-emerald-400 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-40">{recordWeight.isPending ? '保存中' : '记录'}</button>
              </form>
            </div>
            <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4">
              {[
                ['最新体重', weightHistory?.summary.latest_kg == null ? '—' : `${weightHistory.summary.latest_kg.toFixed(1)} kg`],
                ['近 7 天变化', formatDelta(weightDelta)],
                ['7 日记录均值', weightHistory?.summary.average_7d == null ? '—' : `${weightHistory.summary.average_7d.toFixed(1)} kg`],
                ['记录样本', `${weightHistory?.summary.sample_count ?? 0} 天`],
              ].map(([label, value]) => <div key={label} className="rounded-xl border border-white/[0.055] bg-slate-950/30 p-3"><p className="text-[9px] text-slate-600">{label}</p><p className="mt-1 text-sm font-medium text-emerald-200">{value}</p></div>)}
            </div>
            {(weightHistory?.records.length ?? 0) < 2 ? (
              <div className="flex min-h-[150px] items-center justify-center rounded-2xl border border-dashed border-white/[0.07] bg-slate-950/20 px-6 text-center text-xs text-slate-500">至少记录两天后，这里会显示体重趋势；系统不会根据单日波动下结论。</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={weightHistory?.records ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="recorded_at" tickFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })} stroke="#64748b" fontSize={11} />
                  <YAxis domain={['dataMin - 2', 'dataMax + 2']} stroke="#64748b" fontSize={11} width={38} />
                  <Tooltip labelFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString('zh-CN')} contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12 }} formatter={(value) => [`${Number(value).toFixed(1)} kg`, '体重']} />
                  <Line type="monotone" dataKey="weight_kg" name="体重" stroke="#34d399" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
            {recordWeight.isError && <p className="mt-3 text-[10px] text-rose-300">记录失败，请检查数值后重试。</p>}
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
