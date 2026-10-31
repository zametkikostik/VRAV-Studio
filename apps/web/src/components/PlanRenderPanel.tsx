"use client";

import { useState } from "react";
import { session, timelines, Timeline } from "@/lib/api";
import { editingApi as editing, jobsApi as jobs } from "@/lib/editingApi";

type Props = {
  projectId: string;
  timeline: Timeline | null;
  onTimelineUpdated: (tl: Timeline) => void;
  onError: (msg: string) => void;
  onMsg: (msg: string) => void;
};

export function PlanRenderPanel({
  projectId,
  timeline,
  onTimelineUpdated,
  onError,
  onMsg,
}: Props) {
  const [brief, setBrief] = useState("Edit the video clips with short cuts");
  const [planJson, setPlanJson] = useState<object | null>(null);
  const [planSource, setPlanSource] = useState("");
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [renderStatus, setRenderStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function onGeneratePlan() {
    const token = session.getToken();
    if (!token) return;
    setBusy(true);
    try {
      const res = await editing.generate(token, {
        project_id: projectId,
        brief,
        mode: "heuristics",
        model: "mock/default",
      });
      setPlanJson(res.plan);
      setPlanSource(res.source);
      onMsg(`Plan ready (${res.source})`);
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onApplyPlan() {
    const token = session.getToken();
    if (!token || !timeline || !planJson) {
      onError("Need timeline and generated plan");
      return;
    }
    setBusy(true);
    try {
      const res = await editing.apply(token, {
        project_id: projectId,
        timeline_id: timeline.id,
        plan: planJson,
        replace_video_track: true,
      });
      onMsg(`Applied ${res.clip_count} clips, duration ${res.duration_ms}ms`);
      const tl = await timelines.get(token, timeline.id);
      onTimelineUpdated(tl);
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRenderTimeline() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !timeline || !org) {
      onError("Need org, project, timeline");
      return;
    }
    setBusy(true);
    setRenderStatus("starting");
    try {
      const job = await jobs.renderTimeline(token, {
        organization_id: org.id,
        project_id: projectId,
        timeline_id: timeline.id,
      });
      setRenderJobId(job.id);
      setRenderStatus(job.status);
      onMsg(`Render job ${job.id}: ${job.status}`);
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const j = await jobs.get(token, job.id);
        setRenderStatus(j.status);
        if (j.status === "succeeded" || j.status === "failed") {
          onMsg(`Render ${j.status}${j.error ? ": " + j.error : ""}`);
          break;
        }
      }
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDownload() {
    const token = session.getToken();
    if (!token || !renderJobId) return;
    const res = await fetch(jobs.exportUrl(renderJobId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      onError(`Export ${res.status}`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `export-${renderJobId}.mp4`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="mb-4 rounded-lg border border-zinc-700 bg-zinc-900/50 p-4">
      <h2 className="mb-2 text-sm font-semibold text-zinc-200">AI plan → render</h2>
      <textarea
        className="mb-2 w-full rounded border border-zinc-600 bg-zinc-950 p-2 text-sm text-zinc-100"
        rows={2}
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        placeholder="Editing brief..."
      />
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={onGeneratePlan}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Generate plan
        </button>
        <button type="button" disabled={busy || !planJson} onClick={onApplyPlan}
          className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Apply to timeline
        </button>
        <button type="button" disabled={busy || !timeline} onClick={onRenderTimeline}
          className="rounded bg-amber-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Render timeline
        </button>
        {renderJobId && renderStatus === "succeeded" && (
          <button type="button" className="rounded border border-zinc-500 px-3 py-1.5 text-sm text-zinc-200"
            onClick={onDownload}>
            Download export
          </button>
        )}
      </div>
      {planSource && <p className="mt-2 text-xs text-zinc-400">Plan source: {planSource}</p>}
      {renderStatus && <p className="text-xs text-zinc-400">Render: {renderStatus}</p>}
    </section>
  );
}
