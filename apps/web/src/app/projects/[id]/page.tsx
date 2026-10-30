"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { CollabPanel } from "@/components/CollabPanel";
import {
  Asset,
  Clip,
  Timeline,
  Track,
  assetContentUrl,
  assets,
  projects,
  session,
  timelines,
} from "@/lib/api";

const PX_PER_MS = 0.08;
const SNAP_MS = 250;
const NUDGE_MS = 100;

function msToPx(ms: number) {
  return ms * PX_PER_MS;
}
function pxToMs(px: number) {
  return Math.round(px / PX_PER_MS);
}
function snap(ms: number, enabled: boolean) {
  if (!enabled) return ms;
  return Math.round(ms / SNAP_MS) * SNAP_MS;
}
function formatTime(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  const f = Math.floor((ms % 1000) / 40);
  return `${m}:${String(r).padStart(2, "0")}.${String(f).padStart(2, "0")}`;
}

export default function ProjectEditorPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = String(params.id || "");
  const [name, setName] = useState("");
  const [assetList, setAssetList] = useState<Asset[]>([]);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState("");
  const [playheadMs, setPlayheadMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dragging, setDragging] = useState<{
    clipIds: string[];
    startX: number;
    originStarts: Record<string, number>;
  } | null>(null);
  const [resizing, setResizing] = useState<{
    clipId: string;
    edge: "left" | "right";
    startX: number;
    originStart: number;
    originDur: number;
  } | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastTs = useRef(0);
  const token = session.getToken();

  const reload = useCallback(async () => {
    if (!token || !projectId) return;
    const p = await projects.get(token, projectId);
    setName(p.name);
    setAssetList(await assets.list(token, projectId));
    let tls = await timelines.list(token, projectId);
    if (!tls.length) {
      await timelines.create(token, projectId, "Main");
      tls = await timelines.list(token, projectId);
    }
    setTimeline(tls[0]);
  }, [token, projectId]);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    reload().catch((e) => setError(String(e)));
  }, [token, reload, router]);

  // playback loop
  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    lastTs.current = performance.now();
    const tick = (t: number) => {
      const dt = t - lastTs.current;
      lastTs.current = t;
      setPlayheadMs((prev) => {
        const next = prev + dt;
        const max = timeline?.duration_ms || 60000;
        if (next >= max) {
          setPlaying(false);
          return max;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, timeline?.duration_ms]);

  const tracks: Track[] = useMemo(
    () => (timeline?.tracks || []).slice().sort((a, b) => a.order_index - b.order_index),
    [timeline]
  );

  async function onUpload(file: File) {
    if (!token) return;
    setError("");
    try {
      const type = file.type.startsWith("video")
        ? "video"
        : file.type.startsWith("audio")
          ? "audio"
          : file.type.startsWith("image")
            ? "image"
            : "other";
      await assets.upload(token, projectId, file, type);
      await reload();
    } catch (e) {
      setError(String(e));
    }
  }

  async function dropAssetOnTrack(trackId: string, asset: Asset, startMs: number) {
    if (!token) return;
    const duration = 3000;
    await timelines.addClip(token, trackId, {
      asset_id: asset.id,
      start_ms: snap(Math.max(0, startMs), snapEnabled),
      duration_ms: duration,
    });
    await reload();
    const bc = (window as unknown as { __vravCollabBroadcast?: (t: string, p: unknown) => void }).__vravCollabBroadcast;
    bc?.("clip_add", { trackId, assetId: asset.id });
  }

  function toggleSelect(clipId: string, multi: boolean) {
    setSelected((prev) => {
      const next = new Set(multi ? prev : []);
      if (next.has(clipId)) next.delete(clipId);
      else next.add(clipId);
      return next;
    });
  }

  async function deleteSelected() {
    if (!token || !selected.size) return;
    // ripple: after delete, shift later clips left on same track
    const byTrack = new Map<string, Clip[]>();
    for (const tr of tracks) {
      for (const c of tr.clips) {
        if (selected.has(c.id)) {
          if (!byTrack.has(tr.id)) byTrack.set(tr.id, []);
          byTrack.get(tr.id)!.push(c);
        }
      }
    }
    for (const [trackId, clips] of byTrack) {
      clips.sort((a, b) => a.start_ms - b.start_ms);
      let shift = 0;
      const track = tracks.find((t) => t.id === trackId);
      const remaining = (track?.clips || []).filter((c) => !selected.has(c.id)).sort((a, b) => a.start_ms - b.start_ms);
      for (const c of clips) {
        shift += c.duration_ms;
        await timelines.deleteClip(token, c.id);
      }
      // simple ripple: pull clips that started after deleted region
      for (const c of remaining) {
        if (c.start_ms >= (clips[0]?.start_ms || 0)) {
          const newStart = Math.max(0, c.start_ms - shift);
          if (newStart !== c.start_ms) {
            await timelines.updateClip(token, c.id, { start_ms: newStart });
          }
        }
      }
    }
    setSelected(new Set());
    await reload();
  }

  async function nudgeSelected(deltaMs: number) {
    if (!token || !selected.size) return;
    for (const id of selected) {
      const clip = tracks.flatMap((t) => t.clips).find((c) => c.id === id);
      if (!clip) continue;
      const start = snap(Math.max(0, clip.start_ms + deltaMs), snapEnabled);
      await timelines.updateClip(token, id, { start_ms: start });
    }
    await reload();
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteSelected();
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        nudgeSelected(e.shiftKey ? -SNAP_MS : -NUDGE_MS);
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        nudgeSelected(e.shiftKey ? SNAP_MS : NUDGE_MS);
      }
      if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (dragging) {
        const dx = e.clientX - dragging.startX;
        const dMs = pxToMs(dx);
        // live preview via CSS transform would be nicer; for MVP we commit on up
        void dx; void dMs;
      }
      if (resizing) {
        void e;
      }
    }
    async function onUp(e: MouseEvent) {
      if (dragging && token) {
        const dx = e.clientX - dragging.startX;
        const dMs = pxToMs(dx);
        for (const id of dragging.clipIds) {
          const origin = dragging.originStarts[id];
          const start = snap(Math.max(0, origin + dMs), snapEnabled);
          await timelines.updateClip(token, id, { start_ms: start });
        }
        setDragging(null);
        await reload();
        const bc = (window as unknown as { __vravCollabBroadcast?: (t: string, p: unknown) => void }).__vravCollabBroadcast;
        bc?.("clip_move", { ids: dragging.clipIds });
      }
      if (resizing && token) {
        const dx = e.clientX - resizing.startX;
        const dMs = pxToMs(dx);
        if (resizing.edge === "right") {
          const dur = Math.max(100, snap(resizing.originDur + dMs, snapEnabled));
          await timelines.updateClip(token, resizing.clipId, { duration_ms: dur });
        } else {
          const start = snap(Math.max(0, resizing.originStart + dMs), snapEnabled);
          const dur = Math.max(100, resizing.originDur - (start - resizing.originStart));
          await timelines.updateClip(token, resizing.clipId, { start_ms: start, duration_ms: dur });
        }
        setResizing(null);
        await reload();
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging, resizing, token, snapEnabled, reload]);

  const rulerWidth = Math.max(800, msToPx((timeline?.duration_ms || 10000) + 5000));

  return (
    <AppShell>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <Link href="/projects" className="muted">← Проекты</Link>
          <h1 style={{ margin: "4px 0" }}>{name || "…"}</h1>
        </div>
        <div className="row">
          <button type="button" className="secondary" onClick={() => setSnapEnabled((s) => !s)}>
            Snap: {snapEnabled ? "ON" : "OFF"}
          </button>
          <button type="button" onClick={() => setPlaying((p) => !p)}>{playing ? "Pause" : "Play"}</button>
          <button type="button" className="secondary" onClick={() => setPlayheadMs(0)}>Stop</button>
          <button type="button" className="secondary" onClick={deleteSelected} disabled={!selected.size}>
            Delete ({selected.size})
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <strong>Assets</strong>
          <input
            type="file"
            style={{ marginTop: 8 }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
            }}
          />
          <ul style={{ listStyle: "none", padding: 0, marginTop: 12 }}>
            {assetList.map((a) => (
              <li
                key={a.id}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/vrav-asset", JSON.stringify(a));
                }}
                style={{
                  padding: "6px 8px",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  marginBottom: 6,
                  cursor: "grab",
                  fontSize: 13,
                }}
              >
                {a.filename || a.id.slice(0, 8)} <span className="muted">{a.type}</span>
              </li>
            ))}
            {!assetList.length && <li className="muted">Загрузите файл</li>}
          </ul>
        </div>

        <div className="card">
          <strong>Preview</strong>
          <p className="muted">{formatTime(playheadMs)}</p>
          <div
            style={{
              height: 120,
              background: "#000",
              borderRadius: 8,
              display: "grid",
              placeItems: "center",
              color: "var(--muted)",
              fontSize: 13,
            }}
          >
            {playing ? "Playing…" : "Paused"} · playhead sync via rAF
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16, overflowX: "auto" }}>
        <div style={{ position: "relative", width: rulerWidth, minHeight: 40 + tracks.length * 56 }}>
          {/* ruler */}
          <div style={{ height: 24, borderBottom: "1px solid var(--border)", position: "relative" }}>
            {Array.from({ length: Math.ceil(rulerWidth / 80) }).map((_, i) => (
              <span
                key={i}
                className="muted"
                style={{ position: "absolute", left: i * 80, fontSize: 10 }}
              >
                {formatTime(pxToMs(i * 80))}
              </span>
            ))}
          </div>
          {/* playhead */}
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: msToPx(playheadMs),
              width: 2,
              background: "var(--accent2)",
              zIndex: 5,
              pointerEvents: "none",
            }}
          />
          {tracks.map((tr) => (
            <div
              key={tr.id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const raw = e.dataTransfer.getData("application/vrav-asset");
                if (!raw) return;
                const asset = JSON.parse(raw) as Asset;
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                const x = e.clientX - rect.left;
                dropAssetOnTrack(tr.id, asset, pxToMs(x));
              }}
              style={{
                height: 52,
                marginTop: 4,
                background: "var(--bg)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                position: "relative",
              }}
            >
              <span className="muted" style={{ position: "absolute", left: 4, top: 2, fontSize: 11 }}>
                {tr.name} ({tr.track_type})
              </span>
              {tr.clips.map((c) => {
                const isSel = selected.has(c.id);
                return (
                  <div
                    key={c.id}
                    onMouseDown={(e) => {
                      if ((e.target as HTMLElement).dataset.edge) return;
                      e.preventDefault();
                      const multi = e.shiftKey || e.metaKey || e.ctrlKey;
                      toggleSelect(c.id, multi);
                      const ids = multi && selected.has(c.id)
                        ? Array.from(selected)
                        : multi
                          ? [...Array.from(selected), c.id]
                          : [c.id];
                      const originStarts: Record<string, number> = {};
                      for (const id of ids) {
                        const clip = tracks.flatMap((t) => t.clips).find((x) => x.id === id);
                        if (clip) originStarts[id] = clip.start_ms;
                      }
                      setDragging({ clipIds: ids, startX: e.clientX, originStarts });
                    }}
                    style={{
                      position: "absolute",
                      left: msToPx(c.start_ms),
                      width: Math.max(8, msToPx(c.duration_ms)),
                      top: 16,
                      height: 32,
                      background: isSel ? "var(--accent)" : "#2a3550",
                      border: isSel ? "2px solid #fff" : "1px solid #3a4a6a",
                      borderRadius: 6,
                      fontSize: 11,
                      padding: "4px 6px",
                      overflow: "hidden",
                      cursor: "grab",
                      userSelect: "none",
                    }}
                    title={`${c.start_ms}ms / ${c.duration_ms}ms`}
                  >
                    <span
                      data-edge="left"
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        setResizing({
                          clipId: c.id,
                          edge: "left",
                          startX: e.clientX,
                          originStart: c.start_ms,
                          originDur: c.duration_ms,
                        });
                      }}
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        bottom: 0,
                        width: 6,
                        cursor: "ew-resize",
                      }}
                    />
                    {c.asset_id?.slice(0, 6) || "clip"}
                    <span
                      data-edge="right"
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        setResizing({
                          clipId: c.id,
                          edge: "right",
                          startX: e.clientX,
                          originStart: c.start_ms,
                          originDur: c.duration_ms,
                        });
                      }}
                      style={{
                        position: "absolute",
                        right: 0,
                        top: 0,
                        bottom: 0,
                        width: 6,
                        cursor: "ew-resize",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          DnD asset → track · drag clip · resize edges · Shift multi-select · Del ripple-delete · ←/→ nudge · Space play
        </p>
      </div>

      <CollabPanel projectId={projectId} onRemoteEvent={() => reload().catch(() => undefined)} />
    </AppShell>
  );
}
