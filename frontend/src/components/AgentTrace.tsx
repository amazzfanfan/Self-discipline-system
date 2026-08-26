import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { AgentMetrics, AgentTraceEvent } from '../types';

interface AgentTraceProps {
  trace: AgentTraceEvent[];
  metrics?: AgentMetrics;
  live?: boolean;
}

const traceStyle: Record<AgentTraceEvent['type'], { icon: string; color: string; ring: string }> = {
  status: { icon: '✦', color: 'text-cyan-300', ring: 'bg-cyan-400/15 border-cyan-400/25' },
  plan: { icon: '◇', color: 'text-violet-300', ring: 'bg-violet-400/15 border-violet-400/25' },
  tool_call: { icon: '↗', color: 'text-blue-300', ring: 'bg-blue-400/15 border-blue-400/25' },
  tool_result: { icon: '✓', color: 'text-emerald-300', ring: 'bg-emerald-400/15 border-emerald-400/25' },
  guardrail: { icon: '!', color: 'text-amber-300', ring: 'bg-amber-400/15 border-amber-400/25' },
  error: { icon: '×', color: 'text-rose-300', ring: 'bg-rose-400/15 border-rose-400/25' },
};

function formatDuration(durationMs: number) {
  if (durationMs < 1) return '<1ms';
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

export default function AgentTrace({ trace, metrics, live = false }: AgentTraceProps) {
  const [expanded, setExpanded] = useState(live);
  if (!trace.length) return null;

  const toolCount = metrics?.tool_calls ?? trace.filter((item) => item.type === 'tool_call').length;
  const duration = (metrics?.planning_duration_ms ?? 0) + (metrics?.response_duration_ms ?? 0);
  const hasDuration = metrics?.planning_duration_ms != null || metrics?.response_duration_ms != null;

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-white/8 bg-slate-950/45">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-white/[0.035]"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            {live && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-60" />}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${live ? 'bg-cyan-400' : 'bg-emerald-400'}`} />
          </span>
          <span className="text-[11px] font-semibold tracking-wide text-slate-300">
            {live ? 'AGENT 正在执行' : 'AGENT 执行轨迹'}
          </span>
          <span className="truncate text-[10px] text-slate-600">
            {trace.at(-1)?.title}
          </span>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2 text-[10px] text-slate-500">
          {metrics?.workflow_enabled && toolCount > 1 && <span className="rounded-full border border-violet-400/15 bg-violet-400/[0.06] px-2 py-0.5 text-violet-300">多工具工作流</span>}
          {toolCount > 0 && <span>{toolCount} 次工具</span>}
          {hasDuration && (
            <span title="从 Agent 开始规划到回复生成完成，不含网络传输和前端渲染">
              Agent 后端耗时 {formatDuration(duration)}
            </span>
          )}
          <motion.span animate={{ rotate: expanded ? 180 : 0 }} className="text-slate-600">⌄</motion.span>
        </div>
      </button>

      {metrics?.partial_failure && (
        <div className="border-t border-amber-400/10 bg-amber-400/[0.04] px-3 py-2 text-[10px] text-amber-200/80">工作流在部分步骤完成后停止，请以展开后的逐步结果为准。</div>
      )}

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="border-t border-white/5 px-3 py-3">
              {trace.map((item, index) => {
                const style = traceStyle[item.type];
                return (
                  <motion.div
                    key={`${item.type}-${item.step}-${index}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(index * 0.04, 0.2) }}
                    className="relative flex gap-2.5 pb-3 last:pb-0"
                  >
                    {index < trace.length - 1 && (
                      <div className="absolute left-[11px] top-6 h-[calc(100%-18px)] w-px bg-gradient-to-b from-slate-700 to-transparent" />
                    )}
                    <div className={`relative z-10 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg border text-[11px] ${style.ring} ${style.color}`}>
                      {item.type === 'tool_call' && live && index === trace.length - 1 ? (
                        <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>↻</motion.span>
                      ) : style.icon}
                    </div>
                    <div className="min-w-0 pt-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-[11px] font-medium ${style.color}`}>{item.title}</span>
                        {item.tool && <code className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-slate-500">{item.tool}</code>}
                        {item.duration_ms != null && (
                          <span className="text-[9px] text-slate-600">工具耗时 {formatDuration(item.duration_ms)}</span>
                        )}
                      </div>
                      {item.detail && <p className="mt-1 break-words text-[10px] leading-relaxed text-slate-500">{item.detail}</p>}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
