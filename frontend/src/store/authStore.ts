import { create } from "zustand";
import { api, clearToken, setToken } from "@/api/client";
import type { components } from "@/api/schema";

type User = components["schemas"]["UserResponse"];

interface AuthState {
  user: User | null;
  token: string | null;
  // true while we are validating a stored token on startup
  isInitializing: boolean;

  initAuth: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const storedToken = localStorage.getItem("token");

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: storedToken,
  // Block protected routes until we know the stored token is valid
  isInitializing: !!storedToken,

  initAuth: async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      set({ isInitializing: false });
      return;
    }
    try {
      const { data, error } = await api.GET("/auth/me");
      if (error || !data) {
        clearToken();
        set({ user: null, token: null });
      } else {
        set({ user: data });
      }
    } catch {
      clearToken();
      set({ user: null, token: null });
    } finally {
      set({ isInitializing: false });
    }
  },

  login: async (email, password) => {
    const { data, error } = await api.POST("/auth/login", {
      body: { email, password },
    });
    if (error || !data) throw new Error("Login failed");
    setToken(data.access_token);
    set({ token: data.access_token });
    const { data: user } = await api.GET("/auth/me");
    set({ user: user ?? null });
  },

  register: async (email, password, displayName) => {
    const { data, error } = await api.POST("/auth/register", {
      body: { email, password, display_name: displayName },
    });
    if (error || !data) throw new Error("Registration failed");
    setToken(data.access_token);
    set({ token: data.access_token });
    const { data: user } = await api.GET("/auth/me");
    set({ user: user ?? null });
  },

  logout: () => {
    clearToken();
    set({ user: null, token: null });
  },

  refreshUser: async () => {
    const { data } = await api.GET("/auth/me");
    set({ user: data ?? null });
  },
}));
