"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ai, session } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [provider, setProvider] = useState("openrouter");
  const [key, setKey] = useState("");
  const [connections, setConnections] = useState<Array<{ id: string; provider_id: string; key_hint: string }>>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    setConnections(await ai.listConnections(token, org.id));
  }

  useEffect(() => {
    if (!session.getToken()) { router.replace("/login"); return; }
    load().catch((e) => setError(String(e)));
  }, [router]);

  async function save() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org || !key) return;
    setError("");
    try {
      const r = await ai.saveConnection(token, org.id, provider, key);
      setMsg(`Сохранено: ${r.key_hint}`);
      setKey("");
      await load();
    } catch (e) { setError(String(e)); }
  }

  return (
    <AppShell>
      <h1>Настройки / BYOK</h1>
      <p className="muted">Ключи шифруются на сервере (Fernet). В ответах API только hint.</p>
      <div className="card" style={{ display: "grid", gap: 12, maxWidth: 480 }}>
        <label>
          Провайдер
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="openrouter">OpenRouter</option>
            <option value="xai">xAI</option>
            <option value="routerai">RouterAI</option>
          </select>
        </label>
        <label>
          API key
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-..." />
        </label>
        <button type="button" onClick={save}>Сохранить</button>
      </div>
      <h2 style={{ marginTop: 24 }}>Активные подключения</h2>
      {connections.map((c) => (
        <div key={c.id} className="card" style={{ marginBottom: 8 }}>
          <strong>{c.provider_id}</strong> <span className="muted">{c.key_hint}</span>
        </div>
      ))}
      {!connections.length && <p className="muted">Пока нет</p>}
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </AppShell>
  );
}
