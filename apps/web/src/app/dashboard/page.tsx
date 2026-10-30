"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ai, auth, billing, session } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<{ email: string } | null>(null);
  const [credits, setCredits] = useState("—");
  const [providers, setProviders] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("Кратко опиши идею тизера для продукта");
  const [reply, setReply] = useState("");
  const [streamMode, setStreamMode] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = session.getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        setUser(await auth.me(token));
        const org = session.getOrg();
        if (org) {
          const c = await billing.credits(token, org.id);
          setCredits(c.available ?? c.balance);
        }
        const p = await ai.providers(token);
        setProviders(p.map((x) => x.id));
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [router]);

  async function runChat() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    setBusy(true);
    setError("");
    setReply("");
    try {
      try {
        await billing.topup(token, org.id, "50.0000");
      } catch {
        /* ignore */
      }

      if (streamMode) {
        const res = await fetch(`${API_BASE}/ai/chat/stream`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            model: "mock/default",
            organization_id: org.id,
            messages: [{ role: "user", content: prompt }],
          }),
        });
        if (!res.ok || !res.body) throw new Error(`${res.status}: ${await res.text()}`);
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        let text = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";
          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            try {
              const data = JSON.parse(raw);
              if (data.delta) {
                text += data.delta;
                setReply(text);
              } else if (data.error) {
                throw new Error(data.error);
              }
            } catch (err) {
              if (err instanceof SyntaxError) continue;
              throw err;
            }
          }
        }
      } else {
        const r = await ai.chat(token, {
          model: "mock/default",
          organization_id: org.id,
          messages: [{ role: "user", content: prompt }],
        });
        setReply(r.content || "(пусто)");
      }

      const c = await billing.credits(token, org.id);
      setCredits(c.available ?? c.balance);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <h1>Обзор</h1>
      <p className="muted">
        Пользователь: {user?.email || "…"} · кредиты: {credits}
      </p>
      {error && <p className="error">{error}</p>}

      <div className="grid2" style={{ marginTop: 16 }}>
        <div className="card">
          <strong>AI-провайдеры</strong>
          <p className="muted">{providers.length ? providers.join(", ") : "загрузка…"}</p>
        </div>
        <div className="card">
          <strong>Чат</strong>
          <label className="row" style={{ marginTop: 8, color: "var(--text)" }}>
            <input type="checkbox" checked={streamMode} onChange={(e) => setStreamMode(e.target.checked)} />
            <span className="muted">Streaming (SSE)</span>
          </label>
          <textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} style={{ marginTop: 8 }} />
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" onClick={runChat} disabled={busy}>
              {busy ? "…" : "Отправить"}
            </button>
          </div>
          {reply && <pre style={{ whiteSpace: "pre-wrap", marginTop: 12, fontSize: 14 }}>{reply}</pre>}
        </div>
      </div>
    </AppShell>
  );
}
