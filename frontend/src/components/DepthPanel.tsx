import type { CSSProperties, MouseEvent, ReactNode } from 'react';
import { motion, useMotionValue, useReducedMotion, useSpring } from 'framer-motion';

interface DepthPanelProps {
  children: ReactNode;
  className?: string;
  wrapperClassName?: string;
  glow?: string;
  interactive?: boolean;
}

export default function DepthPanel({
  children,
  className = '',
  wrapperClassName = '',
  glow = 'rgba(34, 211, 238, 0.16)',
  interactive = true,
}: DepthPanelProps) {
  const reducedMotion = useReducedMotion();
  const rawRotateX = useMotionValue(0);
  const rawRotateY = useMotionValue(0);
  const rotateX = useSpring(rawRotateX, { stiffness: 180, damping: 24, mass: 0.55 });
  const rotateY = useSpring(rawRotateY, { stiffness: 180, damping: 24, mass: 0.55 });

  const handleMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!interactive || reducedMotion) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    rawRotateX.set(y * -3.2);
    rawRotateY.set(x * 4.2);
  };

  const reset = () => {
    rawRotateX.set(0);
    rawRotateY.set(0);
  };

  return (
    <div
      className={`depth-stage ${wrapperClassName}`}
      style={{ '--depth-glow': glow } as CSSProperties}
      onMouseMove={handleMove}
      onMouseLeave={reset}
    >
      <motion.div
        className={`depth-panel ${className}`}
        style={{ rotateX, rotateY, transformPerspective: 1100 }}
      >
        <span className="depth-panel-highlight" aria-hidden="true" />
        {children}
      </motion.div>
    </div>
  );
}
