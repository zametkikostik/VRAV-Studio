"use client";

import {
  formatMs,
  timelineDurationMs,
  TimelineClip,
  TimelineDefinition,
  TrackType,
} from "@/types/timeline";

interface TimelineViewerProps {
  timeline: TimelineDefinition;
}

const TRACK_ORDER: TrackType[] = ["video", "audio", "overlay"];
const TRACK_LABEL: Record<TrackType, string> = {
  video: "Video",
  audio: "Audio",
  overlay: "Overlay",
};
const TRACK_STYLE: Record<TrackType, { bg: string; border: string }> = {
  video: { bg: "rgba(108,140,255,0.85)", border: "#6c8cff" },
  audio: { bg: "rgba(61,214,198,0.85)", border: "#3dd6c6" },
  overlay: { bg: "rgba(255,193,7,0.85)", border: "#ffc107" },
};

export default function TimelineViewer({ timeline }: TimelineViewerProps) {
  const totalMs = Math.max(timelineDurationMs(timeline), 1000);
  const byTrack = TRACK_ORDER.reduce<Record<TrackType, TimelineClip[]>>(
    (acc, t) => {
      acc[t] = timeline.clips.filter((c) => c.track_type === t);
      return acc;
    },
    { video: [], audio: [], overlay: [] }
  );
  const tickSec = totalMs > 60000 ? 10 : 5;
  const tickCount = Math.ceil(totalMs / 1000 / tickSec) + 1;

  return (
    <div className="card" style={{ overflowX: "auto", background: "#0e1118" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <strong>Timeline v{timeline.version}</strong>
          <span className="muted" style={{ marginLeft: 8, fontSize: 13 }}>
            {formatMs(totalMs)} total
            {timeline.output
              ? ` · ${timeline.output.width || 1280}×${timeline.output.height || 720} @ ${timeline.output.fps || 30}fps`
              : ""}
          </span>
        </div>
        <span className="muted" style={{ fontSize: 12 }}>
          {timeline.clips.length} clip(s)
        </span>
      </div>
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          paddingBottom: 6,
          marginBottom: 12,
          marginLeft: 88,
          minWidth: Math.max(480, tickCount * 64),
        }}
      >
        {Array.from({ length: tickCount }).map((_, i) => (
          <div
            key={i}
            style={{
              width: 64,
              fontSize: 11,
              color: "var(--muted)",
              borderLeft: "1px solid var(--border)",
              paddingLeft: 4,
            }}
          >
            {formatMs(i * tickSec * 1000)}
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gap: 10, minWidth: Math.max(480, tickCount * 64) + 88 }}>
        {TRACK_ORDER.map((trackType) => {
          const clips = byTrack[trackType];
          if (!clips.length && trackType !== "video") return null;
          return (
            <div key={trackType} className="row" style={{ alignItems: "stretch", gap: 8 }}>
              <div
                className="muted"
                style={{
                  width: 80,
                  flexShrink: 0,
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  textAlign: "right",
                  paddingTop: 14,
                }}
              >
                {TRACK_LABEL[trackType]}
              </div>
              <div
                style={{
                  flex: 1,
                  height: 44,
                  background: "var(--panel)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  position: "relative",
                }}
              >
                {clips.map((clip, idx) => {
                  const left = (clip.timeline_start_ms / totalMs) * 100;
                  const width = Math.max((clip.duration_ms / totalMs) * 100, 1.5);
                  const style = TRACK_STYLE[clip.track_type];
                  const label =
                    clip.track_type === "overlay" && typeof clip.effects?.text === "string"
                      ? String(clip.effects.text).slice(0, 18)
                      : clip.asset_id.slice(0, 8);
                  return (
                    <div
                      key={`${clip.asset_id}-${clip.timeline_start_ms}-${idx}`}
                      title={`asset ${clip.asset_id} ${clip.duration_ms}ms`}
                      style={{
                        position: "absolute",
                        top: 4,
                        bottom: 4,
                        left: `${left}%`,
                        width: `${width}%`,
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        overflow: "hidden",
                        padding: "0 6px",
                        whiteSpace: "nowrap",
                        color: "#0b0d12",
                      }}
                    >
                      {label}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {timeline.notes && (
        <div
          className="card"
          style={{
            marginTop: 16,
            borderColor: "rgba(255,193,7,0.35)",
            background: "rgba(255,193,7,0.08)",
            fontSize: 14,
          }}
        >
          <strong>AI note:</strong> {timeline.notes}
        </div>
      )}
    </div>
  );
}
