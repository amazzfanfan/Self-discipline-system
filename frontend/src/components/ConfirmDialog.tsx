import { AnimatePresence, motion } from 'framer-motion';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  busy?: boolean;
  tone?: 'danger' | 'warning';
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  busy = false,
  tone = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmClass = tone === 'danger'
    ? 'bg-rose-500/15 text-rose-300 hover:bg-rose-500/20'
    : 'bg-amber-400/15 text-amber-200 hover:bg-amber-400/20';

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label={title}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
          onMouseDown={(event) => { if (!busy && event.target === event.currentTarget) onCancel(); }}
        >
          <motion.div
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            className="w-full max-w-md rounded-[22px] border border-white/[0.08] bg-slate-900 p-5 shadow-2xl"
          >
            <h2 className="text-base font-semibold text-white">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" disabled={busy} onClick={onCancel}
                className="rounded-xl border border-white/[0.08] px-4 py-2.5 text-xs text-slate-400 hover:text-white disabled:opacity-40">
                取消
              </button>
              <button type="button" disabled={busy} onClick={onConfirm}
                className={`rounded-xl px-4 py-2.5 text-xs font-medium disabled:opacity-40 ${confirmClass}`}>
                {busy ? '处理中…' : confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
