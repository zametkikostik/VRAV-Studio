const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type TokenPair = {
  access_token: string;
  refresh_token?: string;
  token_type: string;
};

function authHeaders(token?: string | null): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export async function api<T>(
  path: string,
  opts: RequestInit & { token?: string | null; json?: boolean } = {}
): Promise<T> {
  const { token, json = true, ...rest } = opts;
  const headers: Record<string, string> = { ...authHeaders(token) };
  if (rest.headers && typeof rest.headers === "object" && !Array.isArray(rest.headers)) {
    for (const [k, v] of Object.entries(rest.headers as Record<string, unknown>)) {
      if (typeof v === "string") headers[k] = v;
    }
  }
  if (json && rest.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...rest, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const auth = {
  register: (email: string, password: string, full_name?: string) =>
    api<TokenPair>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    api<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: (token: string) => api<{ id: string; email: string; full_name?: string }>("/auth/me", { token }),
  refresh: (refresh_token: string) =>
    api<TokenPair>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    }),
};

export const orgs = {
  list: (token: string) => api<Array<{ id: string; name: string; slug: string }>>("/organizations", { token }),
  create: (token: string, name: string, slug: string) =>
    api<{ id: string; name: string; slug: string }>("/organizations", {
      method: "POST",
      token,
      body: JSON.stringify({ name, slug }),
    }),
};

export type Project = { id: string; name: string; organization_id: string; description?: string | null; status?: string };
export type Asset = {
  id: string;
  project_id: string;
  scene_id?: string | null;
  type: string;
  storage_key: string;
  filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
};
export type Scene = { id: string; project_id: string; name: string; order_index?: number };

export const projects = {
  list: (token: string, organization_id: string) =>
    api<Project[]>(`/projects?organization_id=${encodeURIComponent(organization_id)}`, { token }),
  create: (token: string, body: { organization_id: string; name: string; description?: string }) =>
    api<Project>("/projects", { method: "POST", token, body: JSON.stringify(body) }),
  get: (token: string, id: string) => api<Project>(`/projects/${id}`, { token }),
};

export const assets = {
  list: (token: string, project_id: string) =>
    api<Asset[]>(`/projects/${project_id}/assets`, { token }),
};

export const editing = {
  generate: (token: string, body: object) =>
    api("/editing/plans/generate", { method: "POST", token, body: JSON.stringify(body) }),
  apply: (token: string, body: object) =>
    api("/editing/plans/apply", { method: "POST", token, body: JSON.stringify(body) }),
  fromBrief: (token: string, project_id: string, brief: string) =>
    api("/editing/plans/from-brief", {
      method: "POST",
      token,
      body: JSON.stringify({ project_id, brief }),
    }),
};

export const jobs = {
  renderTimeline: (token: string, body: object) =>
    api("/jobs/render/timeline", { method: "POST", token, body: JSON.stringify(body) }),
  get: (token: string, jobId: string) => api(`/jobs/${jobId}`, { token }),
  exportUrl: (jobId: string) => `${API_BASE}/jobs/${jobId}/export`,
};

const TOKEN_KEY = "vrav_access";
const REFRESH_KEY = "vrav_refresh";
const ORG_KEY = "vrav_org";

export const session = {
  save(tokens: TokenPair) {
    if (typeof window === "undefined") return;
    localStorage.setItem(TOKEN_KEY, tokens.access_token);
    if (tokens.refresh_token) localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  },
  getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },
  getRefresh() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(REFRESH_KEY);
  },
  clear() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(ORG_KEY);
  },
  setOrg(org: { id: string; name: string; slug: string }) {
    localStorage.setItem(ORG_KEY, JSON.stringify(org));
  },
  getOrg(): { id: string; name: string; slug: string } | null {
    const raw = localStorage.getItem(ORG_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  },
};

export { API_BASE };
