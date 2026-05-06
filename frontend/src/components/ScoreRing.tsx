import { motion } from 'framer-motion';

interface Props {
  score: number;
  label?: string;
}

export default function ScoreRing({ score, label = '综合评分' }: Props) {
  const circumference = 2 * Math.PI * 45;
  const progress = (score / 100) * circumference;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="120" height="120" className="-rotate-90">
        <circle cx="60" cy="60" r="45" stroke="#1e293b" strokeWidth="8" fill="none" />
        <motion.circle
          cx="60" cy="60" r="45" stroke="url(#gradient)" strokeWidth="8" fill="none"
          strokeLinecap="round" strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - progress }}
          transition={{ duration: 1.5, ease: "easeOut" }}
        />
        <defs>
          <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-bold text-white">{score.toFixed(1)}</div>
        <div className="text-xs text-slate-400">{label}</div>
      </div>
    </div>
  );
}
