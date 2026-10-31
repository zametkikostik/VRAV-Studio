/**
 * Snippet merged into apps/web/src/lib/api.ts on main branch development.
 * Copy `editing` and `jobs` exports into api.ts if missing after pull.
 */
export const editingSnippet = `
export const editing = {
  generate: (token, body) => api("/editing/plans/generate", { method: "POST", token, body: JSON.stringify(body) }),
  apply: (token, body) => api("/editing/plans/apply", { method: "POST", token, body: JSON.stringify(body) }),
  fromBrief: (token, project_id, brief) =>
    api("/editing/plans/from-brief", { method: "POST", token, body: JSON.stringify({ project_id, brief }) }),
};

export const jobs = {
  renderTimeline: (token, body) =>
    api("/jobs/render/timeline", { method: "POST", token, body: JSON.stringify(body) }),
  get: (token, jobId) => api(`/jobs/${jobId}`, { token }),
  exportUrl: (jobId) => `${API_BASE}/jobs/${jobId}/export`,
};
`;
