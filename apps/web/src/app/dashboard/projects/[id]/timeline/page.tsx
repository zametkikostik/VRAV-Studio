"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import TimelineViewer from "@/components/TimelineViewer";
import { TimelineDefinition } from "@/types/timeline";

function mockTimeline(projectId: string): TimelineDefinition {
  return {
    version: "1.0",
    project_id: projectId,
    source_asset_ids: ["asset-1", "asset-2", "audio-1"],
    clips: [
      { asset_id: "asset-1", track_type: "video", timeline_start_ms: 0, duration_ms: 5000 },
      { asset_id: "asset-2", track_type: "video", timeline_start_ms: 5000, duration_ms: 5000, effects: { xfade_ms: 500 } },
      { asset_id: "audio-1", track_type: "audio", timeline_start_ms: 0, duration_ms: 10000, effects: { volume: 0.5 } },
      { asset_id: "overlay-1", track_type: "overlay", timeline_start_ms: 1500, duration_ms: 3000, effects: { text: "VRAV Studio" } },
    ],
    notes: "Mock timeline under /dashboard.",
  };
}

export default function DashboardTimelinePage() {
  const params = useParams();
  const projectId = String(params.id || "unknown");
  const timeline: TimelineDefinition = mockTimeline(projectId);

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0 }}>Timeline Editor</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>Project ID: {projectId}</p>
        </div>
        <Link href="/projects">
          <button type="button" className="secondary">All projects</button>
        </Link>
      </div>
      <TimelineViewer timeline={timeline} />
    </div>
  );
}
