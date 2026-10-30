"use client";

import { useEffect, useRef, useState } from "react";
import { collab, session } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function wsUrl(roomId: string) {
  const u = new URL(API_BASE);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = `/ws/collab/${encodeURIComponent(roomId)}`;
  u.search = "";
  return u.toString();
}

export function CollabPanel({
  projectId,
  onRemoteEvent,
}: {
  projectId: string;
  onRemoteEvent?: (msg: { type: string; event_type?: string; payload?: unknown; client_id?: string }) => void;
}) {
  const [sessionId, setSessionId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [status, setStatus] = useState<"off" | "connecting" | "live" | "error">("off");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const clientId = useRef(
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `c-${Date.now()}`
  );

  function pushLog(line: string) {
    setLog((p) => [...p.slice(-40), line]);
  }

  async function start() {
    const token = session.getToken();
    if (!token) return;
    setError("");
    try {
      const r = await collab.createSession(token, projectId);
      setSessionId(r.session_id);
      setRoomId(r.room_id);
      connectWs(r.room_id);
    } catch (e) {
      setError(String(e));
    }
  }

  function connectWs(room: string) {
    wsRef.current?.close();
    setStatus("connecting");
    const ws = new WebSocket(wsUrl(room));
    wsRef.current = ws;
    ws.onopen = () => {
      setStatus("live");
      pushLog("ws connected");
      ws.send(
        JSON.stringify({
          type: "presence",
          event_type: "hello",
          client_id: clientId.current,
          payload: { projectId },
        })
      );
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        pushLog(`${msg.type}${msg.event_type ? "/" + msg.event_type : ""}`);
        onRemoteEvent?.(msg);
      } catch {
        pushLog("bad message");
      }
    };
    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus("off");
  }

  function broadcast(event_type: string, payload: unknown) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "event",
        event_type,
        client_id: clientId.current,
        payload,
      })
    );
  }

  async function sendHttpFallback() {
    const token = session.getToken();
    if (!token || !sessionId) return;
    await collab.postEvent(token, sessionId, "ping", { at: Date.now() });
    pushLog("http ping");
  }

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    (window as unknown as { __vravCollabBroadcast?: typeof broadcast }).__vravCollabBroadcast = broadcast;
    return () => {
      delete (window as unknown as { __vravCollabBroadcast?: unknown }).__vravCollabBroadcast;
    };
  });

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <strong>Collab</strong>
      <p className="muted" style={{ fontSize: 13 }}>
        WebSocket room · status: <b>{status}</b>
        {roomId ? ` · ${roomId}` : ""}
      </p>
      <div className="row">
        <button type="button" onClick={start}>Start session + WS</button>
        <button type="button" className="secondary" onClick={() => broadcast("cursor", { t: Date.now() })} disabled={status !== "live"}>
          Ping peers
        </button>
        <button type="button" className="secondary" onClick={sendHttpFallback} disabled={!sessionId}>
          HTTP fallback
        </button>
      </div>
      <ul className="muted" style={{ fontSize: 12, maxHeight: 120, overflow: "auto" }}>
        {log.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
