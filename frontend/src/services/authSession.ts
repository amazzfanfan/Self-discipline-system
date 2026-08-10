let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export async function refreshAccessToken(signal?: AbortSignal): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      signal,
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const data = await response.json() as { access_token: string };
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function revokeSession(): Promise<void> {
  setAccessToken(null);
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
  } catch {
    // The local session is already cleared; server-side expiry remains the fallback.
  }
}
