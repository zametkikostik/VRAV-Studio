"use client";

import { statusToProgress, useJobProgress } from "@/hooks/use-job-progress";

interface JobProgressBarProps {
  jobId: string | null;
  title?: string;
}

export default function JobProgressBar({ jobId, title = "Render progress" }: JobProgressBarProps) {
  const { job, error, isPolling, progress, isTerminal } = useJobProgress(jobId);

  if (!jobId) return null;

  const pct = job ? statusToProgress(job.status) : progress;
  const status = job?.status || "connecting\u2026";
  const failed =
    job?.status === "failed" || job?.status === "cancelled" || job?.status === "canceled";
  const ok = job?.status === "succeeded";

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <strong>{title}</strong>
        <span className="muted" style={{ fontSize: 12 }}>
          {isPolling && !isTerminal ? "live" : isTerminal ? "done" : "\u2026"}
        </span>
      </div>
      <p className="muted" style={{ margin: "0 0 8px", fontSize: 13 }}>
        Job <code>{jobId}</code>
        {job ? (
          <>
            {" "}\u00b7{" "}
            <strong style={{ color: failed ? "var(--danger)" : ok ? "var(--accent2)" : "var(--text)" }}>
              {status}
            </strong>
            {job.type ? ` \u00b7 ${job.type}` : ""}
          </>
        ) : null}
      </p>
      <div
        style={{
          height: 10,
          borderRadius: 6,
          background: "var(--border)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: failed ? "var(--danger)" : ok ? "var(--accent2)" : "var(--accent)",
            transition: "width 0.4s ease",
          }}
        />
      </div>
      {job?.error && (
        <p className="error" style={{ marginTop: 8, fontSize: 13 }}>
          {job.error}
        </p>
      )}
      {error && !job && (
        <p className="error" style={{ marginTop: 8, fontSize: 13 }}>
          {error}
        </p>
      )}
    </div>
  );
}
