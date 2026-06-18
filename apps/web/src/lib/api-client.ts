import type { ApiError } from "@maintainer-os/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 500;

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  init?: RequestInit,
  attempt = 0,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...init?.headers,
    },
    ...init,
  });

  if (res.status >= 500 && attempt < MAX_RETRIES) {
    const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt);
    await new Promise((r) => setTimeout(r, delay));
    return request<T>(path, init, attempt + 1);
  }

  if (!res.ok) {
    const text = await res.text();
    let detail: string;
    try {
      detail = (JSON.parse(text) as ApiError).detail ?? text;
    } catch {
      detail = text;
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, headers?: HeadersInit) =>
    request<T>(path, { headers }),
  post: <T>(path: string, body: unknown, headers?: HeadersInit) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body), headers }),
  put: <T>(path: string, body: unknown, headers?: HeadersInit) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body), headers }),
  patch: <T>(path: string, body: unknown, headers?: HeadersInit) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body), headers }),
  delete: <T>(path: string, headers?: HeadersInit) =>
    request<T>(path, { method: "DELETE", headers }),
};
