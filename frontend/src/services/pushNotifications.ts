import api from './api';

const SUBSCRIBED_KEY = 'system-agent-web-push-subscribed';

export interface PushConfig {
  enabled: boolean;
  public_key: string | null;
}

function applicationServerKey(value: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) output[index] = raw.charCodeAt(index);
  return output;
}

export async function getPushConfig(): Promise<PushConfig> {
  return api.get('/notifications/push/config').then((response) => response.data);
}

export async function enableWebPush(): Promise<{ background: boolean }> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { background: false };
  }
  const config = await getPushConfig();
  if (!config.enabled || !config.public_key) return { background: false };

  const registration = await navigator.serviceWorker.register('/sw.js');
  await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey(config.public_key),
    });
  }
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error('浏览器没有返回完整的通知订阅信息');
  }
  await api.post('/notifications/push/subscriptions', {
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  });
  window.localStorage.setItem(SUBSCRIBED_KEY, '1');
  return { background: true };
}

export async function disableWebPush(): Promise<void> {
  if (!('serviceWorker' in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration('/sw.js');
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    try {
      await api.delete('/notifications/push/subscriptions', {
        data: { endpoint: subscription.endpoint },
      });
    } finally {
      await subscription.unsubscribe();
    }
  }
  window.localStorage.removeItem(SUBSCRIBED_KEY);
}

export function hasBackgroundPushSubscription(): boolean {
  return window.localStorage.getItem(SUBSCRIBED_KEY) === '1';
}

export function isWithinQuietHours(
  start?: string | null,
  end?: string | null,
  now = new Date(),
): boolean {
  if (!start || !end || start === end) return false;
  const toMinutes = (value: string) => {
    const [hours, minutes] = value.split(':').map(Number);
    return hours * 60 + minutes;
  };
  const current = now.getHours() * 60 + now.getMinutes();
  const startMinutes = toMinutes(start);
  const endMinutes = toMinutes(end);
  return startMinutes < endMinutes
    ? current >= startMinutes && current < endMinutes
    : current >= startMinutes || current < endMinutes;
}
