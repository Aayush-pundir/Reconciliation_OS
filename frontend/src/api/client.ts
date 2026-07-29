import type { ModuleSchema, RunDetail, RunListPage, RunResultPage, User } from "@/types";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

const TOKEN_KEY = "recon_os_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail ?? message;
    } catch {
      /* ignore */
    }
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/auth/me"),

  listModules: () => request<ModuleSchema[]>("/modules"),

  createRun: (moduleKey: string, options: Record<string, unknown>, files: Record<string, File[]>) => {
    const form = new FormData();
    form.set("module_key", moduleKey);
    form.set("options", JSON.stringify(options));
    for (const [slot, fileList] of Object.entries(files)) {
      for (const f of fileList) form.append(slot, f);
    }
    return request<RunDetail>("/runs", { method: "POST", body: form });
  },

  listRuns: (params: { module_key?: string; status?: string; q?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") search.set(k, String(v));
    const qs = search.toString();
    return request<RunListPage>(`/runs${qs ? `?${qs}` : ""}`);
  },

  getRun: (id: string) => request<RunDetail>(`/runs/${id}`),

  getResults: (id: string, params: { kind?: string; sheet_name?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") search.set(k, String(v));
    const qs = search.toString();
    return request<RunResultPage>(`/runs/${id}/results${qs ? `?${qs}` : ""}`);
  },

  listSheets: (id: string) => request<string[]>(`/runs/${id}/sheets`),

  downloadReportUrl: (id: string) => `/api/runs/${id}/report`,

  rerun: (id: string) => request<RunDetail>(`/runs/${id}/rerun`, { method: "POST" }),
};

export { ApiError };
