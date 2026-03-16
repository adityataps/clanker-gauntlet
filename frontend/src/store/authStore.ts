import { create } from "zustand";
import { api, clearToken, setToken } from "@/api/client";
import type { components } from "@/api/schema";

type User = components["schemas"]["UserResponse"];

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("token"),
  isLoading: false,

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const { data, error } = await api.POST("/auth/login", {
        body: { email, password },
      });
      if (error || !data) throw new Error("Login failed");
      setToken(data.access_token);
      set({ token: data.access_token });

      const { data: user } = await api.GET("/auth/me");
      set({ user: user ?? null });
    } finally {
      set({ isLoading: false });
    }
  },

  register: async (email, password, displayName) => {
    set({ isLoading: true });
    try {
      const { data, error } = await api.POST("/auth/register", {
        body: { email, password, display_name: displayName },
      });
      if (error || !data) throw new Error("Registration failed");
      setToken(data.access_token);
      set({ token: data.access_token });

      const { data: user } = await api.GET("/auth/me");
      set({ user: user ?? null });
    } finally {
      set({ isLoading: false });
    }
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
