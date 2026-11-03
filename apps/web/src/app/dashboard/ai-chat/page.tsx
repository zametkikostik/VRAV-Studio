"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useProjects } from "@/hooks/use-projects";
import { useGenerateVideo } from "@/hooks/use-ai-generation";

export default function AIChatPage() {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [lastResult, setLastResult] = useState<{
    job_id: string;
    status: string;
    plan_source?: string | null;
    selected_asset_ids?: string[];
  } | null>(null);
  const [formError, setFormError] = useState("");

  const { data: projects, isLoading: projectsLoading } = useProjects();
  const generateVideo = useGenerateVideo();

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setLastResult(null);
    if (!selectedProjectId || !prompt.trim()) return;

    try {
      const result = await generateVideo.mutateAsync({
        project_id: selectedProjectId,
        prompt: prompt.trim(),
      });
      setLastResult({
        job_id: result.job_id,
        status: result.status,
        plan_source: result.plan_source,
        selected_asset_ids: result.selected_asset_ids,
      });
      setPrompt("");
    } catch (err: unknown) {
      const ax = err as {
        response?: { status?: number; data?: { detail?: string | { msg?: string }[] } };
        message?: string;
      };
      const status = ax.response?.status;
      let detail = ax.message || "Failed to start generation";
      const d = ax.response?.data?.detail;
      if (typeof d === "string") detail = d;
      else if (Array.isArray(d)) detail = d.map((x) => x.msg || JSON.stringify(x)).join("; ");
      if (status === 429) {
        detail = "Rate limit exceeded (max 10 generate requests/min). Wait and try again.";
      } else if (status === 401) {
        detail = "Session expired \u2014 please sign in again.";
      }
      setFormError(detail);
    }
  }

  if (projectsLoading) {
    return <p className="muted">Loading projects\u2026</p>;
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ marginBottom: 4 }}>AI Video Generator</h1>
      <p className="muted" style={{ marginBottom: 20 }}>
        Describe the video you want. The agent searches project assets (RAG), builds a timeline, and queues
        FFmpeg render.
      </p>

      <form className="card" onSubmit={handleGenerate} style={{ display: "grid", gap: 16 }}>
        <label>
          Select Project
          <select
            required
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            style={{ marginTop: 6 }}
          >
            <option value="">\u2014 Choose a project \u2014</option>
            {projects?.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        {projects && projects.length === 0 && (
          <p className="error">
            No projects yet. <Link href="/projects">Create one first</Link>.
          </p>
        )}

        <label>
          Video Prompt
          <textarea
            required
            rows={5}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. Create a dynamic 30-second intro about relocating to Bulgaria, with text overlays."
            style={{ marginTop: 6 }}
          />
        </label>

        {formError && <div className="error">{formError}</div>}

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="submit"
            disabled={!selectedProjectId || !prompt.trim() || generateVideo.isPending}
          >
            {generateVideo.isPending ? "Processing\u2026" : "Generate Video"}
          </button>
        </div>
      </form>

      {lastResult && (
        <div className="card" style={{ marginTop: 16 }}>
          <strong>Generation started</strong>
          <p className="muted" style={{ margin: "8px 0 0", fontSize: 14 }}>
            Job ID: <code>{lastResult.job_id}</code>
            <br />
            Status: {lastResult.status}
            {lastResult.plan_source ? (
              <>
                <br />
                Plan source: {lastResult.plan_source}
              </>
            ) : null}
            {lastResult.selected_asset_ids && lastResult.selected_asset_ids.length > 0 ? (
              <>
                <br />
                Assets: {lastResult.selected_asset_ids.length} selected
              </>
            ) : null}
          </p>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <strong>How it works</strong>
        <ul className="muted" style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 14 }}>
          <li>RAG ranks assets by prompt relevance</li>
          <li>AI (or mock) returns a TimelineDefinition</li>
          <li>FFmpegCompiler builds argv; Celery queues render</li>
          <li>Rate limit: ~10 generate requests per minute</li>
        </ul>
      </div>
    </div>
  );
}
