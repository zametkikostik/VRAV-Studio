# Web plan → render wiring

## Files
- `apps/web/src/lib/editingApi.ts` — HTTP clients
- `apps/web/src/components/PlanRenderPanel.tsx` — UI
- Project page should render:

```tsx
import { PlanRenderPanel } from "@/components/PlanRenderPanel";

<PlanRenderPanel
  projectId={projectId}
  timeline={timeline}
  onTimelineUpdated={setTimeline}
  onError={setError}
  onMsg={setMsg}
/>
```

## Prerequisites
1. User logged in (`session` token)
2. Org selected (`session.setOrg`)
3. Project open with at least one video asset
4. Timeline exists (create via timelines UI if needed)
5. API up with FFmpeg on PATH for inline render

## API sequence
`editingApi.generate` → `editingApi.apply` → `jobsApi.renderTimeline` → poll `jobsApi.get` → `jobsApi.exportUrl` + Bearer download
