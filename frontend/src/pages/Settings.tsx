import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import ConfirmDialog from '../components/ConfirmDialog';
import { useNotification } from '../components/notification-context';
import { useAuthStore } from '../stores/authStore';
import type { UserProfile } from '../types';

function Toggle({ enabled, onClick }: { enabled: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={`relative h-6 w-11 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-slate-700'}`}>
      <motion.span animate={{ x: enabled ? 21 : 3 }} transition={{ type: 'spring', stiffness: 450, damping: 30 }}
        className="absolute left-0 top-1 h-4 w-4 rounded-full bg-white" />
    </button>
  );
}

export default function Settings() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addNotification } = useNotification();
  const logout = useAuthStore((state) => state.logout);
  const [message, setMessage] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [confirmAction, setConfirmAction] = useState<'memories' | 'account' | null>(null);
  const [busyAction, setBusyAction] = useState(false);
  const { data: profile } = useQuery<UserProfile>({
    queryKey: ['profile'],
    queryFn: () => api.get('/users/me/profile').then((response) => response.data),
  });

  const savePreferences = async (updates: Record<string, unknown>) => {
    try {
      await api.patch('/users/me/preferences', updates);
      await queryClient.invalidateQueries({ queryKey: ['profile'] });
      setMessage('设置已保存');
    } catch {
      addNotification({ type: 'error', title: '保存失败', message: '设置未改变，请稍后重试。' });
    }
  };

  const notificationSettings = profile?.notification_settings ?? {};

  const exportData = async () => {
    try {
      const { data } = await api.get('/users/me/data-export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `system-agent-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('数据导出完成');
    } catch {
      addNotification({ type: 'error', title: '导出失败', message: '暂时无法导出数据，请稍后重试。' });
    }
  };

  const clearMemories = async () => {
    setBusyAction(true);
    try {
      const { data } = await api.delete('/users/me/memories');
      setMessage(`已删除 ${data.deleted} 条长期记忆`);
      setConfirmAction(null);
    } catch {
      addNotification({ type: 'error', title: '清理失败', message: '长期记忆没有被删除，请稍后重试。' });
    } finally {
      setBusyAction(false);
    }
  };

  const deleteAccount = async () => {
    if (!deletePassword) return;
    setBusyAction(true);
    try {
      await api.delete('/users/me', { data: { password: deletePassword } });
      await logout();
      navigate('/register');
    } catch {
      addNotification({ type: 'error', title: '账号删除失败', message: '密码可能不正确，账号和数据均未删除。' });
      setConfirmAction(null);
    } finally {
      setBusyAction(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">设置与隐私</h1>
          <p className="mt-1 text-sm text-slate-500">控制任务节奏、Agent 记忆和个人数据</p>
        </div>

        {message && <div className="mb-4 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.06] px-4 py-3 text-xs text-emerald-300">{message}</div>}

        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          className="mb-5 rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-base font-semibold text-slate-200">计划偏好</h2>
          <div className="mb-5">
            <p className="text-sm text-slate-400">每日任务预算</p>
            <p className="mt-1 text-xs text-slate-600">Check-in 的可用时间可能进一步减少当天任务量</p>
            <div className="mt-3 flex gap-2">
              {[1, 2, 3, 4].map((value) => <button key={value} type="button"
                onClick={() => void savePreferences({ daily_task_budget: value })}
                className={`h-9 w-12 rounded-lg text-sm ${profile?.daily_task_budget === value ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-500'}`}>{value}</button>)}
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-white/5 pt-4">
            <div>
              <p className="text-sm text-slate-400">长期记忆</p>
              <p className="mt-1 text-xs text-slate-600">关闭后不再写入或召回个人记忆</p>
            </div>
            <Toggle enabled={profile?.memory_enabled !== 0}
              onClick={() => void savePreferences({ memory_enabled: profile?.memory_enabled === 0 })} />
          </div>
        </motion.section>

        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }}
          className="mb-5 rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-base font-semibold text-slate-200">通知设置</h2>
          {[['daily_tasks', '每日任务提醒'], ['weekly_review', '每周复盘提醒']].map(([key, label]) => (
            <div key={key} className="flex items-center justify-between border-b border-white/5 py-3 last:border-0">
              <span className="text-sm text-slate-400">{label}</span>
              <Toggle enabled={Boolean(notificationSettings[key])} onClick={() => void savePreferences({
                notification_settings: { ...notificationSettings, [key]: !notificationSettings[key] },
              })} />
            </div>
          ))}
        </motion.section>

        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}
          className="mb-5 rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-2 text-base font-semibold text-slate-200">我的数据</h2>
          <p className="mb-4 text-xs leading-5 text-slate-600">可以导出全部画像、任务、对话、记忆和 Agent 运行记录。</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void exportData()} className="rounded-xl bg-cyan-400/10 px-4 py-2 text-xs text-cyan-300">导出 JSON</button>
            <button type="button" onClick={() => setConfirmAction('memories')} className="rounded-xl bg-amber-400/10 px-4 py-2 text-xs text-amber-300">清空长期记忆</button>
          </div>
        </motion.section>

        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}
          className="rounded-2xl border border-rose-400/15 bg-rose-400/[0.035] p-6">
          <h2 className="text-base font-semibold text-rose-200">删除账号</h2>
          <p className="mt-2 text-xs leading-5 text-slate-600">永久删除照片、画像、任务、对话、长期记忆和所有评估记录，无法恢复。</p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <input type="password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} placeholder="输入当前密码确认"
              className="flex-1 rounded-xl border border-white/5 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-rose-400/30" />
            <button type="button" onClick={() => setConfirmAction('account')} disabled={!deletePassword}
              className="rounded-xl bg-rose-500/15 px-4 py-2.5 text-xs font-medium text-rose-300 disabled:opacity-40">永久删除</button>
          </div>
        </motion.section>

        <p className="py-8 text-center text-xs text-slate-700">System Agent v9.0 · Face++ 仅用于肤质观察</p>
      </div>
      <ConfirmDialog
        open={confirmAction === 'memories'}
        title="清空全部长期记忆？"
        description="对话记录不会被删除，但 Agent 后续将无法再召回现有长期记忆。"
        confirmLabel="确认清空"
        tone="warning"
        busy={busyAction}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => void clearMemories()}
      />
      <ConfirmDialog
        open={confirmAction === 'account'}
        title="永久删除账号和全部数据？"
        description="照片、画像、任务、目标、对话和长期记忆都会永久删除，且无法恢复。"
        confirmLabel="永久删除"
        busy={busyAction}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => void deleteAccount()}
      />
    </div>
  );
}
