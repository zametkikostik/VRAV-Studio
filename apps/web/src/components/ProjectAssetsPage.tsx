"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import AssetUploader from "@/components/AssetUploader";
import {
  Asset,
  useAnalyzeAsset,
  useAssets,
  useTranscribeAsset,
} from "@/hooks/use-assets";
import { useJobProgress } from "@/hooks/use-job-progress";
import { apiClient } from "@/lib/api-client";

function AuthThumb({
  projectId,
  assetId,
  filename,
  title,
}: {
  projectId: string;
  assetId: string;
  filename: string;
  title: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    apiClient
      .get(`/projects/${projectId}/assets/${assetId}/keyframes/${filename}`, {
        responseType: "blob",
      })
      .then((r) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(r.data);
        setSrc(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [projectId, assetId, filename]);
  if (!src) return null;
  return (
    <img
      src={src}
      alt={title}
      title={title}
      style={{ width: 48, height: 32, objectFit: "cover", borderRadius: 4 }}
    />
  );
}

function iconFor(type: string) {
  if (type === "video") return "🎬";
  if (type === "audio") return "🎵";
  if (type === "image") return "🖼️";
  return "📄";
}

function formatSize(bytes: number | null) {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(ms: number | null | undefined) {
  if (ms == null) return "—";
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.floor(s % 60)}s`;
}

function AssetRow({
  asset,
  projectId,
  onJob,
}: {
  asset: Asset;
  projectId: string;
  onJob: (jobId: string | null) => void;
}) {
  const analyze = useAnalyzeAsset(projectId);
  const transcribe = useTranscribeAsset(projectId);
  const busy = analyze.isPending || transcribe.isPending;
  const canTranscribe = asset.type === "video" || asset.type === "audio";
  const canAnalyze =
    asset.type === "video" || asset.type === "audio" || asset.type === "image";

  return (
    <tr style={{ borderBottom: "1px solid var(--border)", verticalAlign: "top" }}>
      <td style={{ padding: "10px 14px" }}>
        <span style={{ marginRight: 8 }}>{iconFor(asset.type)}</span>
        {asset.filename || asset.id.slice(0, 8)}
        {asset.probe_status && (
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            probe: {asset.probe_status}
            {asset.transcription_status
              ? ` · transcript: ${asset.transcription_status}`
              : ""}
          </div>
        )}
        {asset.transcript && (
          <div style={{ fontSize: 12, marginTop: 6, maxWidth: 360 }} className="muted">
            {(asset.transcript || "").slice(0, 160)}
            {(asset.transcript || "").length > 160 ? "…" : ""}
          </div>
        )}
        {asset.keyframes && asset.keyframes.length > 0 && (
          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
            {asset.keyframes.slice(0, 4).map((k) => (
              <AuthThumb
                key={k.filename}
                projectId={projectId}
                assetId={asset.id}
                filename={k.filename}
                title={`${k.timestamp_ms} ms`}
              />
            ))}
          </div>
        )}
      </td>
      <td style={{ padding: "10px 14px" }} className="muted">
        {asset.type}
      </td>
      <td style={{ padding: "10px 14px" }} className="muted">
        {formatSize(asset.size_bytes)}
      </td>
      <td style={{ padding: "10px 14px" }} className="muted">
        {formatDuration(asset.duration_ms)}
        {asset.width && asset.height ? (
          <div style={{ fontSize: 12 }}>
            {asset.width}×{asset.height}
            {asset.fps != null ? ` @ ${Number(asset.fps).toFixed(1)}fps` : ""}
          </div>
        ) : null}
        {(asset.video_codec || asset.audio_codec) && (
          <div style={{ fontSize: 12 }}>
            {[asset.video_codec, asset.audio_codec].filter(Boolean).join(" / ")}
          </div>
        )}
      </td>
      <td style={{ padding: "10px 14px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {canAnalyze && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() =>
                analyze.mutate(asset.id, {
                  onSuccess: (job) => onJob(job.id),
                  onError: () => onJob(null),
                })
              }
            >
              Analyze
            </button>
          )}
          {canTranscribe && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() =>
                transcribe.mutate(asset.id, {
                  onSuccess: (job) => onJob(job.id),
                  onError: () => onJob(null),
                })
              }
            >
              Transcribe
            </button>
          )}
          {analyze.isError && (
            <span style={{ color: "crimson", fontSize: 12 }}>Analyze failed</span>
          )}
          {transcribe.isError && (
            <span style={{ color: "crimson", fontSize: 12 }}>
              Transcribe failed (provider may be unavailable)
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function ProjectAssetsPage() {
  const params = useParams();
  const projectId = String(params?.id || "");
  const { data: assets, isLoading, error, refetch } = useAssets(projectId);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { job, error: jobError, isTerminal } = useJobProgress(activeJobId);

  useEffect(() => {
    if (isTerminal && job?.status === "succeeded") {
      refetch();
    }
  }, [isTerminal, job?.status, refetch]);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Link href="/dashboard" className="muted">
          ← Dashboard
        </Link>
      </div>
      <h1 style={{ marginBottom: 8 }}>Project assets</h1>
      <p className="muted" style={{ marginBottom: 16 }}>
        Upload media, run analysis, then use AI plan generation with real metadata.
      </p>
      <AssetUploader projectId={projectId} />
      {activeJobId && (
        <div className="card" style={{ marginTop: 16, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Job status</div>
          <div className="muted" style={{ fontSize: 14 }}>
            {job ? `${job.type} · ${job.status}` : "polling…"}
            {job?.error ? ` — ${job.error}` : ""}
            {jobError ? ` — ${jobError}` : ""}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Status labels only — not a real progress percentage.
          </p>
        </div>
      )}
      {isLoading && <p className="muted">Loading assets…</p>}
      {error && (
        <p style={{ color: "crimson" }}>Failed to load assets. Check login and project access.</p>
      )}
      {assets && assets.length === 0 && (
        <div className="card" style={{ marginTop: 16, padding: 16 }}>
          <p className="muted">No assets yet. Upload video/audio/images above.</p>
        </div>
      )}
      {assets && assets.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden", marginTop: 16 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "10px 14px" }}>Name</th>
                <th style={{ padding: "10px 14px" }}>Type</th>
                <th style={{ padding: "10px 14px" }}>Size</th>
                <th style={{ padding: "10px 14px" }}>Tech</th>
                <th style={{ padding: "10px 14px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => (
                <AssetRow
                  key={asset.id}
                  asset={asset}
                  projectId={projectId}
                  onJob={setActiveJobId}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
