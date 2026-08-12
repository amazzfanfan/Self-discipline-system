import type { CSSProperties } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { BehaviorMetrics, Dimension, UserScore } from '../types';

const DIMENSIONS: Array<{ key: Dimension; label: string; short: string; color: string }> = [
  { key: 'exercise', label: '运动状态', short: '运动', color: '#38bdf8' },
  { key: 'diet', label: '饮食习惯', short: '饮食', color: '#34d399' },
  { key: 'sleep', label: '睡眠状态', short: '睡眠', color: '#a78bfa' },
  { key: 'appearance', label: '形象管理', short: '形象', color: '#f472b6' },
];

interface GrowthCoreProps {
  scores?: UserScore[];
  metrics?: BehaviorMetrics;
}

export default function GrowthCore({ scores, metrics }: GrowthCoreProps) {
  const reducedMotion = useReducedMotion();
  const momentum = metrics?.overall.momentum;
  const scoreMap = new Map(scores?.map((item) => [item.dimension, item]));

  return (
    <div className="grid min-h-[300px] gap-7 p-6 md:grid-cols-[1fr_310px] md:items-center md:p-8">
      <div className="relative z-10">
        <div className="mb-5 flex items-center gap-2">
          <span className="core-live-dot" aria-hidden="true" />
          <p className="text-[10px] font-medium uppercase tracking-[0.26em] text-cyan-300/80">Growth Core · Live</p>
        </div>
        <h2 className="max-w-xl text-2xl font-semibold leading-tight text-white sm:text-3xl">
          让每一次行动形成
          <span className="bg-gradient-to-r from-cyan-300 via-blue-300 to-violet-300 bg-clip-text text-transparent">可见的成长动量</span>
        </h2>
        <p className="mt-3 max-w-xl text-xs leading-6 text-slate-500">
          中心数值表示行为成长动量；四项画像基线保持独立稳定，不会被一次打卡直接改写。
        </p>

        <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {DIMENSIONS.map((dimension, index) => {
            const score = scoreMap.get(dimension.key);
            const behavior = metrics?.dimensions[dimension.key];
            return (
              <motion.div
                key={dimension.key}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.07 }}
                className="core-metric-chip"
              >
                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: dimension.color, boxShadow: `0 0 12px ${dimension.color}` }} />
                  {dimension.short}
                </div>
                <div className="mt-2 flex items-end justify-between gap-2">
                  <span className="text-lg font-semibold text-slate-100">{score?.score.toFixed(1) ?? '—'}</span>
                  <span className="pb-0.5 text-[9px] text-slate-600">动量 {behavior?.momentum ?? '—'}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="growth-core-viewport" role="img" aria-label={`当前行为成长动量 ${momentum ?? '暂无数据'}`}>
        <div className="growth-core-shadow" aria-hidden="true" />
        <div className="growth-core-orbit growth-core-orbit-one" aria-hidden="true" />
        <div className="growth-core-orbit growth-core-orbit-two" aria-hidden="true" />
        <div className="growth-core-orbit growth-core-orbit-three" aria-hidden="true" />
        {DIMENSIONS.map((dimension, index) => (
          <span
            key={dimension.key}
            className={`growth-core-node growth-core-node-${index + 1}`}
            style={{ '--node-color': dimension.color } as CSSProperties}
            aria-hidden="true"
          />
        ))}
        <div className="growth-core-sphere-shell">
          <motion.div
            className="growth-core-sphere"
            animate={reducedMotion ? undefined : { y: [0, -7, 0], scale: [1, 1.018, 1] }}
            transition={{ repeat: Infinity, duration: 4.8, ease: 'easeInOut' }}
          >
            <div className="growth-core-sphere-inner">
              <span className="text-[9px] uppercase tracking-[0.2em] text-cyan-100/55">Momentum</span>
              <strong className="mt-1 text-4xl font-semibold tracking-tight text-white">{momentum == null ? '—' : momentum.toFixed(1)}</strong>
              <span className="mt-1 text-[10px] text-cyan-100/45">行为成长动量</span>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
