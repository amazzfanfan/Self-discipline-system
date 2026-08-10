import { afterEach, describe, expect, it, vi } from 'vitest';
import { getAccessToken, refreshAccessToken, setAccessToken } from './authSession';

describe('authSession', () => {
  afterEach(() => {
    setAccessToken(null);
    vi.unstubAllGlobals();
  });

  it('keeps access tokens in memory and shares concurrent refreshes', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'memory-token' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const [first, second] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);

    expect(first).toBe('memory-token');
    expect(second).toBe('memory-token');
    expect(getAccessToken()).toBe('memory-token');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('clears authentication when refresh is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    setAccessToken('old-token');
    const token = await refreshAccessToken();
    expect(token).toBeNull();
  });
});
