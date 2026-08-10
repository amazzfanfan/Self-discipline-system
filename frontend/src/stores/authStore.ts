import { create } from 'zustand';
import api from '../services/api';
import { refreshAccessToken, revokeSession, setAccessToken } from '../services/authSession';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  initialized: boolean;
  bootstrap: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, nickname: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  initialized: false,

  bootstrap: async () => {
    const token = await refreshAccessToken();
    if (!token) {
      set({ initialized: true, isAuthenticated: false, user: null });
      return;
    }
    try {
      await get().fetchUser();
      set({ initialized: true, isAuthenticated: true });
    } catch {
      setAccessToken(null);
      set({ initialized: true, isAuthenticated: false, user: null });
    }
  },

  login: async (email, password) => {
    const { data } = await api.post<{ access_token: string }>('/auth/login', { email, password });
    setAccessToken(data.access_token);
    await get().fetchUser();
    set({ isAuthenticated: true, initialized: true });
  },

  register: async (email, password, nickname) => {
    await api.post('/auth/register', { email, password, nickname });
    await get().login(email, password);
  },

  logout: async () => {
    set({ user: null, isAuthenticated: false, initialized: true });
    await revokeSession();
  },

  fetchUser: async () => {
    const { data } = await api.get<User>('/users/me');
    set({ user: data });
  },
}));
