import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import AgentTrace from '../components/AgentTrace';
import ChatInsightCards from '../components/ChatInsightCards';
import PrivateImage from '../components/PrivateImage';
import { useNotification } from '../components/notification-context';
import api from '../services/api';
import { getAccessToken, refreshAccessToken } from '../services/authSession';
import { useAuthStore } from '../stores/authStore';
import type { AgentMetrics, AgentRunMetadata, AgentTraceEvent, Conversation, PendingAction } from '../types';

interface ChatMessage extends Conversation {
  streaming?: boolean;
}

interface StreamPayload {
  type?: 'trace' | 'run' | 'content' | 'metrics' | 'error';
  trace?: AgentTraceEvent;
  content?: string;
  run_id?: string;
  metrics?: AgentMetrics;
  message?: string;
  pending_action?: PendingAction | null;
}

const quickPrompts = [
  { icon: '◎', title: '查看今日任务', prompt: '帮我查看今天有哪些任务，并告诉我优先做什么' },
  { icon: '↗', title: '记录成长数据', prompt: '我今天的体重是 70 公斤，帮我记录一下' },
  { icon: '◇', title: '制定行动计划', prompt: '结合我的目标和最近状态，帮我制定一个今天能完成的小计划' },
];

async function openAgentStream(content: string, signal: AbortSignal): Promise<Response> {
  const request = (token: string | null) => fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ content }),
    credentials: 'include',
    signal,
  });

  let response = await request(getAccessToken());
  if (response.status !== 401) return response;

  const token = await refreshAccessToken(signal);
  if (!token) return response;
  response = await request(token);
  return response;
}

function getRun(message: ChatMessage): AgentRunMetadata | undefined {
  return message.metadata?.agent_run;
}

function isInsightMessage(message: ChatMessage): boolean {
  return message.metadata?.message_type === 'profile_assessment'
    || message.metadata?.message_type === 'daily_tasks'
    || message.metadata?.message_type === 'skin_analysis'
    || message.content.includes('【状态基线】')
    || message.content.includes('今日任务已发布')
    || message.content.includes('【肤质分析报告】');
}

function PendingActionCard({ action }: { action: PendingAction }) {
  const [optimisticStatus, setStatus] = useState<PendingAction['status']>(action.status);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const queryClient = useQueryClient();
  const status = action.status === 'pending' ? optimisticStatus : action.status;
  const dimension = typeof action.arguments.dimension === 'string' ? action.arguments.dimension : '';
  const goalKeyword = typeof action.arguments.goal_keyword === 'string' ? action.arguments.goal_keyword : '';
  const replacementTitle = typeof action.arguments.title === 'string' ? action.arguments.title : '';
  const dimensionLabel: Record<string, string> = {
    exercise: '运动', diet: '饮食', sleep: '睡眠', appearance: '形象管理',
  };

  const decide = async (decision: 'approve' | 'reject') => {
    setBusy(true);
    setFeedback('');
    try {
      const response = await api.post<{
        success?: boolean;
        action_status?: PendingAction['status'];
        result?: { message?: string };
        reply?: string | null;
      }>(`/chat/actions/${action.action_id}/${decision}`);
      if (decision === 'reject') {
        setStatus('rejected');
      } else if (response.data.success) {
        setStatus('approved');
        setFeedback(response.data.reply ?? '操作已执行，相关页面已经同步。');
      } else {
        setStatus(response.data.action_status ?? 'failed');
        setFeedback(response.data.result?.message ?? '操作执行失败，请重新发起。');
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['chat-history'] }),
        queryClient.invalidateQueries({ queryKey: ['today-tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['behavior-metrics'] }),
        queryClient.invalidateQueries({ queryKey: ['goals'] }),
        queryClient.invalidateQueries({ queryKey: ['goal-progress-summary'] }),
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
        queryClient.invalidateQueries({ queryKey: ['weight-history'] }),
      ]);
    } catch {
      try {
        const current = await api.get<PendingAction>(`/chat/actions/${action.action_id}`);
        setStatus(current.data.status);
        setFeedback(current.data.status === 'expired' ? '该确认请求已过期，请重新发起。' : '该操作已经处理，页面状态已刷新。');
        await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
      } catch {
        setStatus('failed');
        setFeedback('无法执行该操作，请重新发起。');
      }
    } finally {
      setBusy(false);
    }
  };

  const statusLabel: Record<PendingAction['status'], string> = {
    pending: '等待你的明确确认',
    approved: '已确认并执行',
    rejected: '已取消',
    expired: '确认请求已过期',
    failed: '执行失败',
  };

  return (
    <div className="mb-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-3">
      <p className={`text-xs font-medium ${status === 'failed' || status === 'expired' ? 'text-rose-300' : status === 'approved' ? 'text-emerald-300' : 'text-amber-200'}`}>{statusLabel[status]}</p>
      <p className="mt-1 text-[11px] text-slate-500">
        {action.tool === 'skip_task'
          ? `跳过${dimensionLabel[dimension] ?? dimension}任务`
          : action.tool === 'delete_goal'
            ? `删除包含“${goalKeyword}”的目标`
            : action.tool === 'replace_today_task'
              ? `将${dimensionLabel[dimension] ?? dimension}任务替换为“${replacementTitle}”`
              : action.tool}
      </p>
      {status === 'pending' ? (
        <div className="mt-3 flex gap-2">
          <button disabled={busy} onClick={() => void decide('approve')}
            className="rounded-lg bg-amber-400 px-3 py-1.5 text-[11px] font-semibold text-slate-950 disabled:opacity-50">确认执行</button>
          <button disabled={busy} onClick={() => void decide('reject')}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-[11px] text-slate-400 disabled:opacity-50">取消</button>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-slate-400">{feedback || statusLabel[status]}</p>
      )}
    </div>
  );
}

export default function Chat() {
  const { addNotification } = useNotification();
  const user = useAuthStore((state) => state.user);
  const [input, setInput] = useState('');
  const [streamingMsg, setStreamingMsg] = useState<ChatMessage | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisSource, setAnalysisSource] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const temporaryId = useRef(0);
  const queryClient = useQueryClient();

  const { data: history } = useQuery<ChatMessage[]>({
    queryKey: ['chat-history'],
    queryFn: () => api.get<ChatMessage[]>('/chat/history').then((response) => response.data),
  });
  const messages = useMemo(() => history ?? [], [history]);
  const allMessages = streamingMsg ? [...messages, streamingMsg] : messages;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [allMessages.length, streamingMsg?.content, isThinking]);

  const updateStreamingRun = (updater: (run: AgentRunMetadata) => AgentRunMetadata) => {
    setStreamingMsg((previous) => {
      if (!previous) return previous;
      const current = getRun(previous) ?? { trace: [] };
      return {
        ...previous,
        metadata: { ...previous.metadata, agent_run: updater(current) },
      };
    });
  };

  const handleSend = async (preset?: string) => {
    const text = (preset ?? input).trim();
    if (!text || isThinking || streamingMsg) return;

    temporaryId.current += 1;
    const userMsg: ChatMessage = {
      id: `temp-user-${temporaryId.current}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    queryClient.setQueryData<ChatMessage[]>(['chat-history'], (old = []) => [...old, userMsg]);
    setInput('');
    setIsThinking(true);

    const abortController = new AbortController();
    abortRef.current = abortController;
    try {
      const response = await openAgentStream(text, abortController.signal);
      if (!response.ok) {
        let message = response.status === 409
          ? '上一条 Agent 请求仍在处理中，请稍后再试。'
          : response.status === 429
            ? '请求过于频繁，请稍后再试。'
            : 'Agent 服务暂时不可用，请稍后再试。';
        try {
          const payload = await response.json() as { detail?: string | { message?: string } };
          if (typeof payload.detail === 'string') message = payload.detail;
          else if (payload.detail?.message) message = payload.detail.message;
        } catch {
          // Preserve the status-specific fallback when the response is not JSON.
        }
        addNotification({
          type: response.status === 409 || response.status === 429 ? 'warning' : 'error',
          title: response.status === 409 ? 'Agent 正在处理中' : '请求未执行',
          message,
        });
        throw new Error(`Stream failed: ${response.status}`);
      }

      setIsThinking(false);
      temporaryId.current += 1;
      setStreamingMsg({
        id: `temp-ai-${temporaryId.current}`,
        role: 'system',
        content: '',
        created_at: new Date().toISOString(),
        streaming: true,
        metadata: { agent_run: { trace: [] } },
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream reader');
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === '[DONE]') continue;
          try {
            const payload = JSON.parse(raw) as StreamPayload;
            if (payload.type === 'trace' && payload.trace) {
              updateStreamingRun((run) => ({ ...run, trace: [...run.trace, payload.trace!] }));
            } else if (payload.type === 'run') {
              updateStreamingRun((run) => ({
                ...run,
                run_id: payload.run_id,
                metrics: payload.metrics,
                pending_action: payload.pending_action,
              }));
            } else if (payload.type === 'metrics') {
              updateStreamingRun((run) => ({ ...run, metrics: { ...run.metrics, ...payload.metrics } }));
            } else if (payload.type === 'content' && payload.content) {
              setStreamingMsg((previous) => previous ? { ...previous, content: previous.content + payload.content } : previous);
            } else if (payload.type === 'error' && payload.message) {
              setStreamingMsg((previous) => previous ? { ...previous, content: payload.message ?? 'Agent 运行失败' } : previous);
            }
          } catch {
            // Ignore a malformed SSE fragment; the next complete event remains readable.
          }
        }
      }

      setStreamingMsg(null);
      await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['scores'] }),
        queryClient.invalidateQueries({ queryKey: ['goals'] }),
        queryClient.invalidateQueries({ queryKey: ['goal-progress-summary'] }),
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
        queryClient.invalidateQueries({ queryKey: ['weight-history'] }),
      ]);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setIsThinking(false);
        setStreamingMsg(null);
        await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
        return;
      }
      setIsThinking(false);
      setStreamingMsg(null);
      await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
    } finally {
      abortRef.current = null;
    }
  };

  const handleSkinAnalyze = async (file: File) => {
    setIsAnalyzing(true);
    setAnalysisSource('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post<{
        source: string;
        source_display: string;
        error?: string | null;
      }>('/users/me/skin-analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAnalysisSource(response.data.source_display);
      await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
      addNotification({
        type: response.data.source === 'faceplusplus' ? 'success' : 'warning',
        title: response.data.source === 'faceplusplus' ? '肤质观察已完成' : '肤质结果暂不可用',
        message: response.data.source === 'faceplusplus'
          ? 'Face++ 结果已生成，原始照片已经删除。'
          : response.data.error || '请换一张清晰、光线均匀的正脸照片后重试。',
      });
    } catch {
      addNotification({
        type: 'error',
        title: '肤质分析未完成',
        message: '照片已安全处理，但分析服务暂时不可用，请稍后重试。',
      });
    } finally {
      setIsAnalyzing(false);
      setAnalysisSource('');
    }
  };

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-[#050816]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="aurora aurora-one" />
        <div className="aurora aurora-two" />
        <div className="agent-grid absolute inset-0 opacity-30" />
      </div>

      <header className="relative z-10 flex flex-shrink-0 items-center justify-between border-b border-white/[0.07] bg-slate-950/50 px-5 py-4 backdrop-blur-2xl md:px-8">
        <div className="flex items-center gap-3">
          <motion.div
            animate={{ boxShadow: ['0 0 0 0 rgba(34,211,238,0)', '0 0 26px 2px rgba(34,211,238,.18)', '0 0 0 0 rgba(34,211,238,0)'] }}
            transition={{ repeat: Infinity, duration: 3 }}
            className="agent-core-mini flex h-10 w-10 items-center justify-center rounded-2xl border border-cyan-400/20 bg-gradient-to-br from-cyan-400/20 to-violet-500/20 text-cyan-200"
          >
            ✦
          </motion.div>
          <div>
            <h1 className="text-sm font-semibold tracking-wide text-white md:text-base">System Agent</h1>
            <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
              规划 · 工具 · 记忆已连接
            </div>
          </div>
        </div>
        <div className="hidden items-center gap-2 sm:flex">
          {['state tools', 'memory', 'guarded'].map((label, index) => (
            <motion.span
              key={label}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              className="rounded-full border border-white/[0.07] bg-white/[0.035] px-2.5 py-1 text-[9px] uppercase tracking-[0.16em] text-slate-500"
            >
              {label}
            </motion.span>
          ))}
        </div>
      </header>

      <div className="relative z-10 flex-1 overflow-y-auto px-4 py-6 md:px-8 scrollbar-hide">
        <div className="mx-auto max-w-4xl space-y-5">
          {allMessages.length === 0 && !isThinking && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex min-h-[58vh] flex-col items-center justify-center">
              <motion.div
                initial={{ scale: 0.75, opacity: 0 }}
                animate={{ scale: 1, opacity: 1, y: [0, -7, 0] }}
                transition={{ scale: { duration: 0.5 }, opacity: { duration: 0.5 }, y: { repeat: Infinity, duration: 4 } }}
                className="agent-core-large relative mb-7 flex h-20 w-20 items-center justify-center rounded-[28px] border border-cyan-300/15 bg-gradient-to-br from-cyan-400/15 via-blue-500/10 to-violet-500/20 text-3xl text-cyan-200 shadow-[0_0_70px_rgba(34,211,238,.12)]"
              >
                ✦
                <div className="absolute inset-[-8px] rounded-[34px] border border-cyan-400/5" />
              </motion.div>
              <h2 className="bg-gradient-to-r from-white via-cyan-100 to-violet-200 bg-clip-text text-center text-2xl font-semibold text-transparent md:text-3xl">
                今天想推进什么？
              </h2>
              <p className="mt-3 max-w-md text-center text-sm leading-relaxed text-slate-500">
                我会先规划，再安全地调用任务、目标、评分和记忆工具，并把每一步展示给你。
              </p>
              <div className="mt-8 grid w-full max-w-2xl gap-3 md:grid-cols-3">
                {quickPrompts.map((item, index) => (
                  <motion.button
                    key={item.title}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.18 + index * 0.08 }}
                    whileHover={{ y: -4, scale: 1.015 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => void handleSend(item.prompt)}
                    className="group rounded-2xl border border-white/[0.07] bg-white/[0.035] p-4 text-left backdrop-blur-xl transition-colors hover:border-cyan-400/20 hover:bg-cyan-400/[0.045]"
                  >
                    <span className="text-lg text-cyan-300/80">{item.icon}</span>
                    <div className="mt-3 text-xs font-medium text-slate-300 group-hover:text-white">{item.title}</div>
                    <div className="mt-1.5 line-clamp-2 text-[10px] leading-relaxed text-slate-600">{item.prompt}</div>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}

          <AnimatePresence initial={false}>
            {allMessages.map((message) => {
              const run = getRun(message);
              const isUser = message.role === 'user';
              const isInsight = !isUser && isInsightMessage(message);
              return (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 14, scale: 0.985 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.98 }}
                  transition={{ type: 'spring', stiffness: 280, damping: 26 }}
                  className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/10 text-xs text-cyan-200">✦</div>
                  )}
                  <div className={`max-w-[88%] ${isInsight ? 'md:max-w-[88%]' : 'md:max-w-[76%]'} ${isUser ? 'order-first' : ''}`}>
                    <div className={`${isInsight ? '' : 'rounded-2xl px-4 py-3 shadow-xl'} ${isUser
                      ? 'rounded-br-md bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-blue-950/30'
                      : isInsight ? '' : 'rounded-bl-md border border-white/[0.08] bg-slate-900/75 text-slate-200 shadow-black/20 backdrop-blur-xl'}`}>
                      {!isUser && run?.trace && <AgentTrace trace={run.trace} metrics={run.metrics} live={message.streaming} />}
                      {!isUser && run?.pending_action && <PendingActionCard action={run.pending_action} />}
                      {isUser ? (
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                      ) : isInsight ? (
                        <ChatInsightCards message={message} />
                      ) : (
                        <div className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed">
                          <ReactMarkdown>{message.content || (message.streaming ? '正在组织回复…' : '')}</ReactMarkdown>
                          {message.streaming && message.content && <span className="ml-1 inline-block h-4 w-1 animate-pulse rounded-full bg-cyan-300" />}
                        </div>
                      )}
                    </div>
                    <div className={`mt-1.5 px-1 text-[9px] text-slate-700 ${isUser ? 'text-right' : 'text-left'}`}>
                      {new Date(message.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                  {isUser && (
                    <div className="relative mt-1 h-8 w-8 flex-shrink-0 overflow-hidden rounded-xl border border-blue-300/20 bg-gradient-to-br from-blue-500 to-violet-500">
                      <div className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold text-white">{user?.nickname?.slice(0, 1) ?? '我'}</div>
                      <PrivateImage src={user?.avatar_url} alt={user?.nickname ?? '我的头像'} className="absolute inset-0 h-full w-full object-cover" />
                    </div>
                  )}
                </motion.div>
              );
            })}

            {isThinking && (
              <motion.div key="thinking" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/10 text-xs text-cyan-200">✦</div>
                <div className="rounded-2xl rounded-bl-md border border-white/[0.08] bg-slate-900/75 px-4 py-3 backdrop-blur-xl">
                  <div className="flex items-center gap-2 text-[11px] text-slate-400">
                    <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.3, ease: 'linear' }} className="text-cyan-300">◌</motion.span>
                    正在启动 Agent 运行时
                  </div>
                </div>
              </motion.div>
            )}

            {isAnalyzing && (
              <motion.div key="analyzing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-emerald-400/15 bg-emerald-400/10 text-xs">◎</div>
                <div className="rounded-2xl border border-white/[0.08] bg-slate-900/75 px-4 py-3 text-xs text-slate-400 backdrop-blur-xl">
                  {analysisSource ? `正在使用 ${analysisSource} 分析…` : '正在安全分析肤质图片…'}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="relative z-10 flex-shrink-0 border-t border-white/[0.07] bg-slate-950/60 px-4 py-4 backdrop-blur-2xl md:px-8">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-end gap-2 rounded-[22px] border border-white/[0.09] bg-white/[0.045] p-2 shadow-[0_18px_60px_rgba(0,0,0,.28)] transition-all focus-within:border-cyan-400/25 focus-within:bg-white/[0.055]">
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleSkinAnalyze(file);
              event.target.value = '';
            }} />
            <motion.button
              type="button"
              whileHover={{ y: -1, scale: 1.015 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => fileInputRef.current?.click()}
              disabled={isThinking || Boolean(streamingMsg) || isAnalyzing}
              className="group relative flex h-10 flex-shrink-0 items-center gap-2 overflow-hidden rounded-2xl border border-emerald-300/20 bg-gradient-to-br from-emerald-400/[0.14] to-cyan-400/[0.07] px-3 text-emerald-100 shadow-[0_0_24px_rgba(52,211,153,.08)] transition-colors hover:border-emerald-300/35 hover:from-emerald-400/[0.2] hover:to-cyan-400/[0.1] disabled:opacity-40"
              title="上传正脸照片，使用 Face++ 进行肤质观察"
              aria-label="上传照片分析肤质"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 8.5h3l1.4-2h7.2l1.4 2h3v9.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
                <circle cx="12" cy="13.5" r="3.25" />
                <path d="M19 5v3M17.5 6.5h3" />
              </svg>
              <span className="hidden whitespace-nowrap text-[11px] font-medium sm:inline">上传照片分析肤质</span>
              <span className="whitespace-nowrap text-[10px] font-medium sm:hidden">肤质</span>
            </motion.button>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              rows={1}
              placeholder="描述目标，或让 Agent 查询并执行任务…"
              disabled={isThinking || Boolean(streamingMsg) || isAnalyzing}
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2.5 text-sm leading-5 text-white outline-none placeholder:text-slate-600 disabled:opacity-50"
            />
            {streamingMsg ? (
              <motion.button
                type="button"
                whileTap={{ scale: 0.94 }}
                onClick={() => abortRef.current?.abort()}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-rose-500/15 text-xs text-rose-300"
                title="停止"
              >
                ■
              </motion.button>
            ) : (
              <motion.button
                type="button"
                whileHover={input.trim() ? { scale: 1.06, rotate: -3 } : undefined}
                whileTap={input.trim() ? { scale: 0.93 } : undefined}
                onClick={() => void handleSend()}
                disabled={isThinking || isAnalyzing || !input.trim()}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-blue-600 text-sm font-bold text-slate-950 shadow-[0_0_24px_rgba(34,211,238,.2)] disabled:from-slate-700 disabled:to-slate-800 disabled:text-slate-500 disabled:shadow-none"
              >
                ↗
              </motion.button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center text-[9px] tracking-wide text-slate-700">
            <span className="text-emerald-300/55">上传清晰正脸照进行 Face++ 日常肤质观察 · 原图分析后删除</span>
            <span>写操作受 Schema 校验与安全策略保护 · 跳过任务需要明确确认</span>
          </div>
        </div>
      </div>
    </div>
  );
}
