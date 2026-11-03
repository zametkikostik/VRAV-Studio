/** Mirrors apps/api TimelineDefinition / EditingPlan (milliseconds). */

export type TrackType = "video" | "audio" | "overlay";

export interface TimelineClip {
  id?: string | null;
  asset_id: string;
  track_type: TrackType;
  track_name?: string | null;
  source_in_ms?: number;
  source_out_ms?: number | null;
  timeline_start_ms: number;
  duration_ms: number;
  effects?: Record<string, unknown>;
}

export interface TimelineSubtitle {
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface TimelineOutput {
  width?: number;
  height?: number;
  fps?: number;
  video_codec?: string;
  audio_codec?: string;
  container?: string;
}

export interface TimelineDefinition {
  version: string;
  project_id: string;
  source_asset_ids?: string[];
  clips: TimelineClip[];
  subtitles?: TimelineSubtitle[];
  output?: TimelineOutput;
  notes?: string | null;
}

export function timelineDurationMs(timeline: TimelineDefinition): number {
  if (!timeline.clips.length) return 0;
  return Math.max(...timeline.clips.map((c) => c.timeline_start_ms + c.duration_ms));
}

export function formatMs(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
