"use client";

import { useRenderProgress } from "@/hooks/use-render-progress";
import { TOKEN_KEY } from "@/lib/api-client";

interface RenderProgressProps {
  jobId: string | null;
  onReset: () => void;
}

export default function RenderProgressUI({ jobId, onReset }: RenderProgressProps) {
  const progressData = useRenderProgress(jobId);
  if (!jobId) return null;

  const barColor =
    progressData.status === "completed"
      ? "var(--accent2)"
      : progressData.status === "failed"
        ? "var(--danger)"
        : "var(--accent)";

  const statusText =
    progressData.status === "queued"
      ? "Queued (waiting for worker)\u2026"
      : progressData.status === "processing"
        ? `Processing: ${progressData.message || "Rendering\u2026"}`
        : progressData.status === "completed"
          ? "Render completed successfully!"
          : `Failed: ${progressData.error || "Unknown error"}`;

  async function downloadExport() {
    const token = localStorage.getItem(TOKEN_KEY);
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const res = await fetch(`${base}/jobs/${jobId}/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      alert(`Download failed: ${res.status}`);
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `export-${jobId}.mp4`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <span className="muted" style={{ fontSize: 13 }}>
          Job <code>{jobId}</code>
        </span>
        <strong style={{ fontSize: 14 }}>{Math.round(progressData.progress)}%</strong>
      </div>
      <div
        style={{
          width: "100%",
          height: 12,
          borderRadius: 8,
          background: "var(--border)",
          overflow: "hidden",
          marginBottom: 10,
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.min(100, Math.max(0, progressData.progress))}%`,
            background: barColor,
            transition: "width 0.45s ease",
          }}
        />
      </div>
      <p className="muted" style={{ margin: "0 0 12px", fontSize: 14 }}>
        {statusText}
      </p>
      <div className="row" style={{ gap: 8 }}>
        {progressData.status === "completed" && (
          <button type="button" onClick={downloadExport}>
            Download Video
          </button>
        )}
        {(progressData.status === "completed" || progressData.status === "failed") && (
          <button type="button" className="secondary" onClick={onReset}>
            Generate Another
          </button>
        )}
        {progressData.status !== "completed" && progressData.status !== "failed" && (
          <button type="button" className="secondary" disabled>
            Please wait\u2026
          </button>
        )}
      </div>
    </div>
  );
}
