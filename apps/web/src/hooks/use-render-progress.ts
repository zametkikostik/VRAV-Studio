"use client";

import { useEffect, useRef, useState } from "react";
import { TOKEN_KEY } from "@/lib/api-client";

export interface RenderProgress {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  message?: string;
  output_url?: string;
  error?: string;
  backend_status?: string;
  type?: string;
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

function wsBase(): string {
  return apiBase().replace(/^http/, "ws");
}

export function useRenderProgress(jobId: string | null) {
  const [progress, setProgress] = useState<RenderProgress>({
    job_id: jobId || "",
    status: "queued",
    progress: 0,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!jobId) {
      setProgress({ job_id: "", status: "queued", progress: 0 });
      return;
    }

    let closed = false;
    const token =
      typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";

    function apply(data: RenderProgress) {
      if (!closed) setProgress(data);
    }

    async function pollOnce() {
      try {
        const res = await fetch(`${apiBase()}/jobs/${jobId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const job = await res.json();
        const status = String(job.status || "").toLowerCase();
        let ui: RenderProgress["status"] = "queued";
        let pct = 10;
        let message = status;
        if (status === "running") {
          ui = "processing";
          pct = 55;
          message = "Rendering / processing";
        } else if (status === "succeeded") {
          ui = "completed";
          pct = 100;
          message = "Completed";
        } else if (status === "failed" || status === "cancelled" || status === "canceled") {
          ui = "failed";
          pct = 100;
          message = job.error || "Failed";
        }
        apply({
          job_id: jobId!,
          status: ui,
          progress: pct,
          message,
          error: job.error || undefined,
          output_url: ui === "completed" ? `/jobs/${jobId}/export` : undefined,
          backend_status: status,
          type: job.type,
        });
        if (ui === "completed" || ui === "failed") return;
        if (!closed) pollRef.current = setTimeout(pollOnce, 2000);
      } catch {
        if (!closed) pollRef.current = setTimeout(pollOnce, 3000);
      }
    }

    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = `${wsBase()}/ws/jobs/${jobId}/progress${qs}`;
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(url);
      wsRef.current = ws;
    } catch {
      pollOnce();
      return () => {
        closed = true;
        if (pollRef.current) clearTimeout(pollRef.current);
      };
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as RenderProgress;
        apply({
          job_id: data.job_id || jobId,
          status: data.status,
          progress: data.progress ?? 0,
          message: data.message,
          output_url: data.output_url,
          error: data.error,
          backend_status: data.backend_status,
          type: data.type,
        });
        if (data.status === "completed" || data.status === "failed") ws?.close();
      } catch {
        /* ignore */
      }
    };

    ws.onerror = () => {
      if (!closed) pollOnce();
    };

    return () => {
      closed = true;
      if (pollRef.current) clearTimeout(pollRef.current);
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.close();
      wsRef.current = null;
    };
  }, [jobId]);

  return progress;
}
