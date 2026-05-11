import { useState, useRef, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import api from '../services/api';

interface Message {
  id: string;
  role: 'system' | 'user';
  content: string;
  created_at: string;
  streaming?: boolean;
}

export default function Chat() {
  const [input, setInput] = useState('');
  const [streamingMsg, setStreamingMsg] = useState<Message | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisSource, setAnalysisSource] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: history } = useQuery({
    queryKey: ['chat-history'],
    queryFn: () => api.get('/chat/history').then((r) => r.data),
  });

  const messages: Message[] = history || [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMsg, isThinking]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;

    const userMsg: Message = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    queryClient.setQueryData(['chat-history'], (old: Message[] = []) => [...old, userMsg]);
    setInput('');
    setIsThinking(true);

    try {
      const token = localStorage.getItem('access_token');
      const abortController = new AbortController();
      abortRef.current = abortController;

      const response = await fetch(`/api/chat/stream?content=${encodeURIComponent(text)}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        signal: abortController.signal,
      });

      if (!response.ok) throw new Error('Stream failed');

      setIsThinking(false);
      const aiMsg: Message = {
        id: `temp-ai-${Date.now()}`,
        role: 'system',
        content: '',
        created_at: new Date().toISOString(),
        streaming: true,
      };
      setStreamingMsg(aiMsg);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') continue;
          try {
            const parsed = JSON.parse(data);
            if (parsed.content) {
              fullContent += parsed.content;
              setStreamingMsg((prev) => prev ? { ...prev, content: fullContent } : null);
            }
          } catch { /* skip malformed chunks */ }
        }
      }

      setStreamingMsg(null);
      await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setIsThinking(false);
      setStreamingMsg(null);
      queryClient.invalidateQueries({ queryKey: ['chat-history'] });
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

      const response = await api.post('/users/me/skin-analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const data = response.data;
      setAnalysisSource(data.source_display);

      // 刷新聊天记录
      await queryClient.invalidateQueries({ queryKey: ['chat-history'] });
    } catch (err) {
      console.error('肤质分析失败:', err);
    } finally {
      setIsAnalyzing(false);
      setAnalysisSource('');
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleSkinAnalyze(file);
    }
    // 清除 input 值，允许重复选择同一文件
    e.target.value = '';
  };

  const allMessages = streamingMsg ? [...messages, streamingMsg] : messages;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-slate-900/80 backdrop-blur-sm border-b border-slate-800 px-6 py-4 flex-shrink-0">
        <h1 className="text-lg font-bold text-white flex items-center gap-2">
          <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
          系统对话
        </h1>
        <p className="text-slate-500 text-xs mt-0.5">与系统交流，报告任务、记录数据、肤质分析</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-6 py-4 space-y-4">
        {allMessages.length === 0 && !isThinking && (
          <div className="flex flex-col items-center justify-center h-full text-slate-600">
            <div className="text-5xl mb-4 opacity-30">⚡</div>
            <p className="text-sm">发送消息开始与系统对话</p>
            <p className="text-xs mt-1 text-slate-700">你可以报告任务完成、记录体重、肤质分析或日常聊天</p>
          </div>
        )}
        <AnimatePresence>
          {allMessages.map((msg) => (
            <motion.div key={msg.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'system' && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center text-sm flex-shrink-0">
                  ⚡
                </div>
              )}
              <div className={`max-w-[70%] rounded-2xl px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-slate-800/80 text-slate-200 rounded-bl-sm border border-slate-700/50'
              }`}>
                <div className="text-xs text-slate-400 mb-1">
                  {msg.role === 'system' ? '系统' : '你'} · {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                </div>
                {msg.role === 'system' ? (
                  <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown>{msg.content || '...'}</ReactMarkdown>
                    {msg.streaming && <span className="inline-block w-1.5 h-4 bg-blue-400 ml-0.5 animate-pulse" />}
                  </div>
                ) : (
                  <div className="text-sm whitespace-pre-wrap leading-relaxed">
                    {msg.content || '...'}
                  </div>
                )}
              </div>
            </motion.div>
          ))}

          {isThinking && (
            <motion.div key="thinking" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center text-sm flex-shrink-0">
                ⚡
              </div>
              <div className="bg-slate-800/80 border border-slate-700/50 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </motion.div>
          )}

          {isAnalyzing && (
            <motion.div key="analyzing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center text-sm flex-shrink-0">
                🔍
              </div>
              <div className="bg-slate-800/80 border border-slate-700/50 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  <span className="text-sm text-slate-400 ml-1">
                    {analysisSource ? `正在使用 ${analysisSource} 分析...` : '正在分析肤质...'}
                  </span>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-slate-900/80 backdrop-blur-sm border-t border-slate-800 px-6 py-4 flex-shrink-0">
        <div className="flex gap-3">
          {/* 肤质分析按钮 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileSelect}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isThinking || !!streamingMsg || isAnalyzing}
            className="px-4 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-700 text-white rounded-xl font-medium transition-colors flex items-center gap-2"
            title="上传照片进行肤质分析"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span className="hidden sm:inline">肤质分析</span>
          </button>

          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="输入消息... (报告任务完成、记录体重、日常聊天)"
            disabled={isThinking || !!streamingMsg || isAnalyzing}
            className="flex-1 px-4 py-3 bg-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <button onClick={handleSend} disabled={isThinking || !!streamingMsg || isAnalyzing || !input.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-xl font-medium transition-colors">
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
