import { useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { NotificationContext } from './notification-context';
import type { NotificationMessage } from './notification-context';

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<NotificationMessage[]>([]);

  const removeNotification = useCallback((id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  const addNotification = useCallback((notification: Omit<NotificationMessage, 'id'>) => {
    const id = crypto.randomUUID();
    const newNotification = { ...notification, id };
    setNotifications(prev => [...prev, newNotification]);

    // Auto remove after duration
    const duration = notification.duration || 5000;
    setTimeout(() => {
      removeNotification(id);
    }, duration);
  }, [removeNotification]);

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, removeNotification }}>
      {children}
      <NotificationContainer notifications={notifications} removeNotification={removeNotification} />
    </NotificationContext.Provider>
  );
}

function NotificationContainer({ 
  notifications, 
  removeNotification 
}: { 
  notifications: NotificationMessage[];
  removeNotification: (id: string) => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      <AnimatePresence>
        {notifications.map(notification => (
          <NotificationItem 
            key={notification.id} 
            notification={notification}
            onClose={() => removeNotification(notification.id)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}

function NotificationItem({ 
  notification, 
  onClose 
}: { 
  notification: NotificationMessage;
  onClose: () => void;
}) {
  const typeConfig = {
    success: {
      bg: 'bg-emerald-900/90 border-emerald-700',
      icon: '✓',
      iconBg: 'bg-emerald-500',
    },
    warning: {
      bg: 'bg-yellow-900/90 border-yellow-700',
      icon: '⚠',
      iconBg: 'bg-yellow-500',
    },
    error: {
      bg: 'bg-red-900/90 border-red-700',
      icon: '✕',
      iconBg: 'bg-red-500',
    },
    info: {
      bg: 'bg-blue-900/90 border-blue-700',
      icon: 'ℹ',
      iconBg: 'bg-blue-500',
    },
  };

  const config = typeConfig[notification.type];

  return (
    <motion.div
      initial={{ opacity: 0, x: 100, scale: 0.9 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.9 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`${config.bg} border rounded-xl p-4 shadow-2xl backdrop-blur-sm`}
    >
      <div className="flex items-start gap-3">
        <div className={`${config.iconBg} w-6 h-6 rounded-full flex items-center justify-center text-white text-xs flex-shrink-0`}>
          {config.icon}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium text-sm">{notification.title}</h4>
          <p className="text-slate-300 text-xs mt-1">{notification.message}</p>
        </div>
        <button 
          onClick={onClose}
          className="text-slate-400 hover:text-white transition-colors flex-shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </motion.div>
  );
}
