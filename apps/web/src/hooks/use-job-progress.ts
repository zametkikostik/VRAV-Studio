"use client";

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";

export interface JobStatus {
  id: string;
  organization_id: string;
  project_id: string | null;
  type: string;
  status: string;
  error: string | null;
  created_at?: string | null;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "canceled"]);

/** Map job status to 0–100 progress for the bar. */
export function statusToProgress(status: string): number {
  switch (status) {
    case "pending":
    case "queued":
      return 10;
    case "running":
      return 55;
    case "succeeded":
      return 100;
    case "failed":
    case "cancelled":
    case "canceled":
      return 100;
    default:
      return 5;
  }
}

/**
 * Poll GET /jobs/{id} until terminal status.
 * Backend has no dedicated job WebSocket; collab WS is for timeline rooms.
 * Polling every `intervalMs` is the production-safe progress channel.
 */
export function useJobProgress(jobId: string | null, opts?: { intervalMs?: number }) {
  const intervalMs = opts?.intervalMs ?? 2000;
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    if (!jobId) {
      setJob(null);
      setError(null);
      setIsPolling(false);
      return;
    }

    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      if (stopped.current || !jobId) return;
      setIsPolling(true);
      try {
        const { data } = await apiClient.get<JobStatus>(`/jobs/${jobId}`);
        if (stopped.current) return;
        setJob(data);
        setError(null);
        if (!TERMINAL.has(data.status)) {
          timer = setTimeout(tick, intervalMs);
        } else {
          setIsPolling(false);
        }
      } catch (e: unknown) {
        if (stopped.current) return;
        const ax = e as { response?: { data?: { detail?: string } }; message?: string };
        setError(ax.response?.data?.detail || ax.message || "Failed to fetch job");
        setIsPolling(false);
        timer = setTimeout(tick, intervalMs * 2);
      }
    }

    tick();
    return () => {
      stopped.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, intervalMs]);

  return {
    job,
    error,
    isPolling,
    progress: job ? statusToProgress(job.status) : 0,
    isTerminal: job ? TERMINAL.has(job.status) : false,
  };
}
