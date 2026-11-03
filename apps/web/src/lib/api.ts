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
  const headers: Record<string, string> = {
    ...authHeaders(token),
  };
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
export type Clip = {
  id: string;
  track_id: string;
  asset_id?: string | null;
  start_ms: number;
  duration_ms: number;
  metadata?: Record<string, unknown> | null;
};
export type Track = {
  id: string;
  name: string;
  track_type: string;
  order_index: number;
  clips: Clip[];
};
export type Timeline = {
  id: string;
  project_id: string;
  name: string;
  duration_ms: number;
  fps: number;
  tracks: Track[];
};

export const projects = {
  list: (token: string, orgId: string) => api<Project[]>(`/organizations/${orgId}/projects`, { token }),
  create: (token: string, organization_id: string, name: string) =>
    api<Project>("/projects", { method: "POST", token, body: JSON.stringify({ organization_id, name }) }),
  get: (token: string, projectId: string) => api<Project>(`/projects/${projectId}`, { token }),
};

export const assets = {
  list: (token: string, projectId: string) => api<Asset[]>(`/projects/${projectId}/assets`, { token }),
  upload: async (token: string, projectId: string, file: File, assetType = "other") => {
    const form = new FormData();
    form.append("file", file);
    form.append("asset_type", assetType);
    const res = await fetch(`${API_BASE}/projects/${projectId}/assets/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json() as Promise<Asset>;
  },
};

export const scenes = {
  list: (token: string, projectId: string) => api<Scene[]>(`/projects/${projectId}/scenes`, { token }),
  create: (token: string, projectId: string, name: string) =>
    api<Scene>(`/projects/${projectId}/scenes`, { method: "POST", token, body: JSON.stringify({ name }) }),
};

export const timelines = {
  list: (token: string, projectId: string) => api<Timeline[]>(`/projects/${projectId}/timelines`, { token }),
  create: (token: string, projectId: string, name = "Main") =>
    api<Timeline>(`/projects/${projectId}/timelines`, { method: "POST", token, body: JSON.stringify({ name, fps: 30 }) }),
  get: (token: string, timelineId: string) => api<Timeline>(`/timelines/${timelineId}`, { token }),
  addTrack: (token: string, timelineId: string, track_type: string, name: string, order_index = 0) =>
    api<Track>(`/timelines/${timelineId}/tracks`, {
      method: "POST",
      token,
      body: JSON.stringify({ name, track_type, order_index }),
    }),
  addClip: (token: string, trackId: string, body: { asset_id?: string; start_ms: number; duration_ms: number }) =>
    api<Clip>(`/tracks/${trackId}/clips`, { method: "POST", token, body: JSON.stringify(body) }),
  updateClip: (token: string, clipId: string, body: { start_ms?: number; duration_ms?: number; asset_id?: string }) =>
    api<Clip>(`/clips/${clipId}`, { method: "PATCH", token, body: JSON.stringify(body) }),
  deleteClip: (token: string, clipId: string) => api<void>(`/clips/${clipId}`, { method: "DELETE", token }),
};

export function assetContentUrl(projectId: string, assetId: string) {
  return `${API_BASE}/projects/${projectId}/assets/${assetId}/content`;
}

export const billing = {
  credits: (token: string, orgId: string) =>
    api<{ balance: string; reserved: string; available: string }>(`/billing/credits/${orgId}`, { token }),
  topup: (token: string, organization_id: string, amount: string) =>
    api<{ balance: string }>("/billing/credits/topup", {
      method: "POST",
      token,
      body: JSON.stringify({ organization_id, amount }),
    }),
  plans: (token: string) => api<Array<{ id: string; name: string }>>("/billing/plans", { token }),
};

export const ai = {
  providers: (token: string) =>
    api<Array<{ id: string; capabilities: Record<string, boolean> }>>("/ai/providers", { token }),
  chat: (
    token: string,
    body: { model: string; organization_id: string; messages: Array<{ role: string; content: string }> }
  ) =>
    api<{ content: string | null; provider: string | null; usage: { cost_credits: number | null } }>(
      "/ai/chat",
      { method: "POST", token, body: JSON.stringify(body) }
    ),
  saveConnection: (token: string, organization_id: string, provider_id: string, api_key: string) =>
    api<{ key_hint: string }>("/ai/connections", {
      method: "POST",
      token,
      body: JSON.stringify({ organization_id, provider_id, api_key }),
    }),
  listConnections: (token: string, organization_id: string) =>
    api<Array<{ id: string; provider_id: string; key_hint: string }>>(
      `/ai/connections?organization_id=${organization_id}`,
      { token }
    ),
};

export const collab = {
  createSession: (token: string, project_id: string) =>
    api<{ session_id: string; room_id: string }>("/collab/sessions", {
      method: "POST",
      token,
      body: JSON.stringify({ project_id }),
    }),
  postEvent: (token: string, sessionId: string, event_type: string, payload?: object) =>
    api<{ event_id: number }>(`/collab/sessions/${sessionId}/events`, {
      method: "POST",
      token,
      body: JSON.stringify({ event_type, payload }),
    }),
  listEvents: (token: string, sessionId: string, after_id = 0) =>
    api<Array<{ id: number; event_type: string; payload?: object; user_id: string }>>(
      `/collab/sessions/${sessionId}/events?after_id=${after_id}`,
      { token }
    ),
};

export const licenses = {
  issue: (token: string, organization_id: string) =>
    api<{ license_key: string }>("/licenses/issue", {
      method: "POST",
      token,
      body: JSON.stringify({ organization_id, max_installations: 3 }),
    }),
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
