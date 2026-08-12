import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { hasBackgroundPushSubscription, isWithinQuietHours } from '../services/pushNotifications';
import type { NotificationInboxResponse, UserNotification, UserProfile } from '../types';
import { useNotification } from './notification-context';

const kindIcon: Record<UserNotification['kind'], string> = {
  task_reminder: '◷',
  daily_tasks: '✓',
  weekly_review: '↗',
  system: '✦',
};

export default function NotificationInbox() {
  const [open, setOpen] = useState(false);
  const knownIds = useRef<Set<string> | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addNotification } = useNotification();
  const { data } = useQuery<NotificationInboxResponse>({
    queryKey: ['notifications'],
    queryFn: () => api.get('/notifications').then((response) => response.data),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
  });
  const { data: profile } = useQuery<UserProfile>({
    queryKey: ['profile'],
    queryFn: () => api.get('/users/me/profile').then((response) => response.data),
  });

  useEffect(() => {
    if (!data) return;
    if (knownIds.current === null) {
      knownIds.current = new Set(data.items.map((item) => item.id));
      return;
    }
    const incoming = data.items.filter((item) => !item.read_at && !knownIds.current?.has(item.id));
    const quiet = isWithinQuietHours(
      profile?.notification_quiet_start,
      profile?.notification_quiet_end,
    );
    for (const item of incoming) {
      if (!quiet) addNotification({ type: 'info', title: item.title, message: item.message, duration: 8000 });
      if (
        !quiet
        &&
        profile?.notification_settings?.browser_notifications
        && !hasBackgroundPushSubscription()
        && 'Notification' in window
        && window.Notification.permission === 'granted'
      ) {
        new window.Notification(item.title, { body: item.message, tag: item.id });
      }
      if (item.kind === 'daily_tasks' || item.payload.assessment_id) {
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ['today-tasks'] }),
          queryClient.invalidateQueries({ queryKey: ['tasks'] }),
          queryClient.invalidateQueries({ queryKey: ['chat-history'] }),
          queryClient.invalidateQueries({ queryKey: ['latest-assessment'] }),
        ]);
      }
    }
    for (const item of data.items) knownIds.current.add(item.id);
  }, [
    addNotification,
    data,
    profile?.notification_quiet_end,
    profile?.notification_quiet_start,
    profile?.notification_settings?.browser_notifications,
    queryClient,
  ]);

  const markRead = async (item: UserNotification) => {
    if (!item.read_at) await api.post(`/notifications/${item.id}/read`);
    await queryClient.invalidateQueries({ queryKey: ['notifications'] });
    setOpen(false);
    if (item.payload.link) navigate(item.payload.link);
  };

  const markAllRead = async () => {
    await api.post('/notifications/read-all');
    await queryClient.invalidateQueries({ queryKey: ['notifications'] });
  };

  return (
    <div className="absolute right-5 top-4 z-40">
      <button type="button" aria-label="通知中心" onClick={() => setOpen((value) => !value)}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-white/8 bg-slate-950/80 text-slate-400 shadow-xl backdrop-blur-xl transition hover:border-cyan-400/20 hover:text-cyan-300">
        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022 23.85 23.85 0 005.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
        {Boolean(data?.unread_count) && (
          <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }}
            className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-slate-950 bg-cyan-400 px-1 text-[9px] font-bold text-slate-950">
            {Math.min(data?.unread_count || 0, 99)}
          </motion.span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.98 }}
            className="absolute right-0 mt-2 w-[min(380px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/8 bg-slate-950/95 shadow-2xl shadow-black/40 backdrop-blur-2xl">
            <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">提醒中心</h2>
                <p className="mt-0.5 text-[10px] text-slate-600">未读 {data?.unread_count || 0} 条</p>
              </div>
              {Boolean(data?.unread_count) && <button onClick={() => void markAllRead()} className="text-[10px] text-cyan-400 hover:text-cyan-300">全部已读</button>}
            </div>
            <div className="max-h-[420px] overflow-y-auto p-2">
              {!data?.items.length && <p className="py-10 text-center text-xs text-slate-600">暂时没有提醒</p>}
              {data?.items.map((item) => (
                <button key={item.id} type="button" onClick={() => void markRead(item)}
                  className={`mb-1 flex w-full gap-3 rounded-xl p-3 text-left transition hover:bg-white/[0.04] ${item.read_at ? 'opacity-55' : 'bg-cyan-400/[0.035]'}`}>
                  <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${item.read_at ? 'bg-slate-800 text-slate-500' : 'bg-cyan-400/10 text-cyan-300'}`}>{kindIcon[item.kind] || '✦'}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 text-xs font-medium text-slate-200">
                      {item.title}{!item.read_at && <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />}
                    </span>
                    <span className="mt-1 block line-clamp-2 text-[11px] leading-4 text-slate-500">{item.message}</span>
                    <span className="mt-1.5 block text-[9px] text-slate-700">{new Date(item.created_at).toLocaleString('zh-CN')}</span>
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
