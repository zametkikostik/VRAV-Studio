"use client";

import { create } from "zustand";
import { jwtDecode } from "jwt-decode";
import { REFRESH_KEY, TOKEN_KEY } from "@/lib/api-client";

interface JwtPayload {
  sub?: string;
  exp?: number;
}

interface User {
  id: string;
  email?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  login: (tokens: { access: string; refresh?: string }) => void;
  logout: () => void;
  checkAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,

  login: (tokens) => {
    if (typeof window === "undefined") return;
    let user: User | null = null;
    try {
      const payload = jwtDecode<JwtPayload>(tokens.access);
      user = { id: String(payload.sub || "") };
    } catch {
      user = null;
    }
    localStorage.setItem(TOKEN_KEY, tokens.access);
    if (tokens.refresh) localStorage.setItem(REFRESH_KEY, tokens.refresh);
    set({
      user,
      accessToken: tokens.access,
      refreshToken: tokens.refresh || null,
      isAuthenticated: Boolean(user?.id),
    });
  },

  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
    }
    set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
  },

  checkAuth: () => {
    if (typeof window === "undefined") return;
    const token = localStorage.getItem(TOKEN_KEY);
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!token) {
      set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
      return;
    }
    try {
      const payload = jwtDecode<JwtPayload>(token);
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        localStorage.removeItem(TOKEN_KEY);
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
        return;
      }
      set({
        user: { id: String(payload.sub || "") },
        accessToken: token,
        refreshToken: refresh,
        isAuthenticated: true,
      });
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
    }
  },
}));
