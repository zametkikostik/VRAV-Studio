"use client";

import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Keys aligned with existing session helpers in lib/api.ts */
export const TOKEN_KEY = "vrav_access";
export const REFRESH_KEY = "vrav_refresh";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json", Accept: "application/json" },
});

apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (typeof window !== "undefined" && error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
      if (!window.location.pathname.startsWith("/auth") && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/auth/login";
      }
    }
    return Promise.reject(error);
  }
);
