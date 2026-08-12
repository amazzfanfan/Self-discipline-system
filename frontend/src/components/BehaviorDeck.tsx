import type { CSSProperties } from 'react';
import { motion } from 'framer-motion';
import type { BehaviorMetrics, Dimension } from '../types';

const DIMENSIONS: Array<{ key: Dimension; label: string; color: string }> = [
  { key: 'exercise', label: '运动', color: '#3b82f6' },
  { key: 'diet', label: '饮食', color: '#10b981' },
  { key: 'sleep', label: '睡眠', color: '#8b5cf6' },
  { key: 'appearance', label: '形象', color: '#ec4899' },
];

interface BehaviorDeckProps {
  metrics?: BehaviorMetrics;
}

export default function BehaviorDeck({ metrics }: BehaviorDeckProps) {
  return (
    <div className="behavior-deck" role="img" aria-label="四个维度的行为成长动量立体图">
      <div className="behavior-deck-grid" aria-hidden="true" />
      <div className="relative z-10 grid grid-cols-4 gap-2 sm:gap-4">
        {DIMENSIONS.map((dimension, index) => {
          const metric = metrics?.dimensions[dimension.key];
          const value = metric?.momentum;
          const height = value == null ? 12 : Math.max(20, Math.round(value * 0.88));
          return (
            <motion.div
              key={dimension.key}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              className="behavior-pillar-slot"
            >
              <div
                className={`behavior-pillar ${value == null ? 'behavior-pillar-empty' : ''}`}
                style={{
                  '--pillar-height': `${height}px`,
                  '--pillar-color': dimension.color,
                } as CSSProperties}
                aria-hidden="true"
              >
                <span className="behavior-pillar-front" />
                <span className="behavior-pillar-side" />
                <span className="behavior-pillar-top" />
              </div>
              <div className="mt-4 text-center">
                <p className="text-[10px] text-slate-500">{dimension.label}</p>
                <p className="mt-1 text-sm font-semibold" style={{ color: dimension.color }}>{value ?? '—'}</p>
                <p className="mt-1 text-[8px] text-slate-700">{metric?.sample_count_7d ?? 0} 项样本</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
