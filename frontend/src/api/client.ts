/**
 * Typed API client backed by openapi-fetch.
 *
 * Usage:
 *   import { api } from "@/api/client";
 *   const { data, error } = await api.GET("/auth/me");
 *
 * The client automatically injects the Authorization header from
 * localStorage if a token is present. Call `setToken(token)` after
 * login and `clearToken()` on logout.
 */

import createClient from "openapi-fetch";
import type { paths } from "./schema";

let _token: string | null = localStorage.getItem("token");

export function setToken(token: string) {
  _token = token;
  localStorage.setItem("token", token);
}

export function clearToken() {
  _token = null;
  localStorage.removeItem("token");
}

export function getToken(): string | null {
  return _token;
}

export const api = createClient<paths>({
  baseUrl: "/api",
  headers: {},
});

// Inject Authorization header on every request if token is present.
api.use({
  onRequest({ request }) {
    if (_token) {
      request.headers.set("Authorization", `Bearer ${_token}`);
    }
    return request;
  },
});
