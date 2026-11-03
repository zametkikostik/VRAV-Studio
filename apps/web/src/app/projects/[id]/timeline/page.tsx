"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import TimelineViewer from "@/components/TimelineViewer";
import { TimelineDefinition } from "@/types/timeline";

function mockTimeline(projectId: string): TimelineDefinition {
  return {
    version: "1.0",
    project_id: projectId,
    source_asset_ids: ["asset-1", "asset-2", "asset-3", "audio-1"],
    clips: [
      { asset_id: "asset-1", track_type: "video", timeline_start_ms: 0, duration_ms: 5000, source_in_ms: 0 },
      { asset_id: "asset-2", track_type: "video", timeline_start_ms: 5000, duration_ms: 5000, source_in_ms: 0, effects: { xfade_ms: 500 } },
      { asset_id: "asset-3", track_type: "video", timeline_start_ms: 10000, duration_ms: 5000, source_in_ms: 0 },
      { asset_id: "audio-1", track_type: "audio", timeline_start_ms: 0, duration_ms: 15000, effects: { volume: 0.5 } },
      { asset_id: "overlay-1", track_type: "overlay", timeline_start_ms: 2000, duration_ms: 3000, effects: { text: "Welcome to Bulgaria!" } },
    ],
    subtitles: [{ start_ms: 2000, end_ms: 5000, text: "Welcome to Bulgaria!" }],
    output: { width: 1280, height: 720, fps: 30 },
    notes: "Mock AI plan.",
  };
}

export default function ProjectTimelinePage() {
  const params = useParams();
  const projectId = String(params.id || "unknown");
  const timeline = mockTimeline(projectId);

  return (
    <AppShell>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0 }}>Timeline Editor</h1>
          <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
            Project: <code>{projectId}</code>
          </p>
        </div>
        <Link href={`/projects/${projectId}`}>
          <button type="button" className="secondary">Back to project</button>
        </Link>
      </div>
      <TimelineViewer timeline={timeline} />
    </AppShell>
  );
}
