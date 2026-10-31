/** Standalone editing + jobs clients. */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(token?: string | null): HeadersInit {
  const h: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function api<T>(path: string, opts: RequestInit & { token?: string | null } = {}): Promise<T> {
  const { token, ...rest } = opts;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: { ...authHeaders(token), ...(rest.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const editingApi = {
  generate: (token: string, body: { project_id: string; brief: string; mode?: string; model?: string }) =>
    api<{ plan: object; source: string }>("/editing/plans/generate", {
      method: "POST",
      token,
      body: JSON.stringify(body),
    }),
  apply: (
    token: string,
    body: { project_id: string; timeline_id: string; plan: object; replace_video_track?: boolean }
  ) =>
    api<{ timeline_id: string; duration_ms: number; clip_count: number }>("/editing/plans/apply", {
      method: "POST",
      token,
      body: JSON.stringify(body),
    }),
  fromBrief: (token: string, project_id: string, brief: string) =>
    api<{ plan: object; source: string }>("/editing/plans/from-brief", {
      method: "POST",
      token,
      body: JSON.stringify({ project_id, brief }),
    }),
};

export const jobsApi = {
  renderTimeline: (
    token: string,
    body: {
      organization_id: string;
      project_id: string;
      timeline_id: string;
      width?: number;
      height?: number;
      fps?: number;
    }
  ) =>
    api<{ id: string; status: string; type: string; error?: string | null }>("/jobs/render/timeline", {
      method: "POST",
      token,
      body: JSON.stringify(body),
    }),
  get: (token: string, jobId: string) =>
    api<{ id: string; status: string; type: string; error?: string | null }>(`/jobs/${jobId}`, { token }),
  exportUrl: (jobId: string) => `${API_BASE}/jobs/${jobId}/export`,
};
