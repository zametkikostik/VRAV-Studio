"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Project, projects, session } from "@/lib/api";

export default function ProjectsPage() {
  const router = useRouter();
  const [list, setList] = useState<Project[]>([]);
  const [name, setName] = useState("Новый проект");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload(token: string, orgId: string) {
    setList(await projects.list(token, orgId));
  }

  useEffect(() => {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) { router.replace("/login"); return; }
    reload(token, org.id).catch((e) => setError(String(e)));
  }, [router]);

  async function create() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    setBusy(true); setError("");
    try {
      const p = await projects.create(token, org.id, name);
      await reload(token, org.id);
      router.push(`/projects/${p.id}`);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <AppShell>
      <h1>Проекты</h1>
      <div className="card row" style={{ marginBottom: 16 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1 }} />
        <button type="button" onClick={create} disabled={busy}>Создать</button>
      </div>
      {error && <p className="error">{error}</p>}
      <div style={{ display: "grid", gap: 8 }}>
        {list.map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`} className="card" style={{ color: "inherit", textDecoration: "none" }}>
            <strong>{p.name}</strong>
            <div className="muted" style={{ fontSize: 12 }}>{p.id}</div>
          </Link>
        ))}
        {!list.length && <p className="muted">Пока нет проектов</p>}
      </div>
    </AppShell>
  );
}
