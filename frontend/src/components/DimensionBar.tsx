import { motion } from 'framer-motion';

const COLORS = {
  exercise: { bar: 'from-blue-500 to-blue-400', text: 'text-blue-400', icon: '🏃' },
  diet: { bar: 'from-emerald-500 to-emerald-400', text: 'text-emerald-400', icon: '🥗' },
  sleep: { bar: 'from-violet-500 to-violet-400', text: 'text-violet-400', icon: '😴' },
  appearance: { bar: 'from-pink-500 to-pink-400', text: 'text-pink-400', icon: '✨' },
};

interface Props {
  dimension: string;
  score: number;
  streak: number;
  threshold: number;
}

export default function DimensionBar({ dimension, score, streak, threshold }: Props) {
  const colors = COLORS[dimension as keyof typeof COLORS] || COLORS.exercise;

  return (
    <div className="mb-4">
      <div className="flex justify-between items-center mb-1">
        <span className={`${colors.text} text-sm`}>{colors.icon} {dimension}</span>
        <span className="text-slate-300 text-sm">{score.toFixed(1)}</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <motion.div
          className={`h-full bg-gradient-to-r ${colors.bar} rounded-full`}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </div>
      <div className="text-xs text-slate-500 mt-1">连续 {streak}/{threshold} 天</div>
    </div>
  );
}
