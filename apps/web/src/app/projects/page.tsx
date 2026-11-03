"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { session } from "@/lib/api";
import { useCreateProject, useProjects } from "@/hooks/use-projects";

export default function ProjectsPage() {
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const { data: projects, isLoading, error, refetch } = useProjects();
  const createProject = useCreateProject();

  useEffect(() => {
    if (!session.getToken() || !session.getOrg()) {
      router.replace("/auth/login");
    }
  }, [router]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const p = await createProject.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setModalOpen(false);
      setName("");
      setDescription("");
      router.push(`/projects/${p.id}`);
    } catch {
      /* mutation error surfaced below */
    }
  }

  return (
    <AppShell>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>Projects</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            Create and open AI video projects
          </p>
        </div>
        <button type="button" onClick={() => setModalOpen(true)}>
          + New Project
        </button>
      </div>

      {isLoading && <p className="muted">Loading projects…</p>}
      {error && (
        <div className="error card" style={{ marginBottom: 12 }}>
          Failed to load projects.{" "}
          <button type="button" className="secondary" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}
      {createProject.isError && (
        <div className="error" style={{ marginBottom: 12 }}>
          {(createProject.error as Error)?.message || "Create failed"}
        </div>
      )}

      {!isLoading && projects && projects.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 32 }}>
          <p className="muted">No projects yet.</p>
          <button type="button" onClick={() => setModalOpen(true)} style={{ marginTop: 12 }}>
            Create your first project
          </button>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        }}
      >
        {projects?.map((project) => (
          <Link
            key={project.id}
            href={`/projects/${project.id}`}
            className="card"
            style={{ color: "inherit", textDecoration: "none" }}
          >
            <strong style={{ fontSize: 18 }}>{project.name}</strong>
            <p className="muted" style={{ fontSize: 13, margin: "8px 0", minHeight: 36 }}>
              {project.description || "No description"}
            </p>
            <div className="muted" style={{ fontSize: 11 }}>
              {project.created_at
                ? `Created: ${new Date(project.created_at).toLocaleDateString()}`
                : `ID: ${project.id.slice(0, 8)}…`}
            </div>
          </Link>
        ))}
      </div>

      {modalOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 50,
            padding: 16,
          }}
          onClick={() => setModalOpen(false)}
        >
          <div className="card" style={{ width: "100%", maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>Create New Project</h2>
            <form onSubmit={handleCreate} style={{ display: "grid", gap: 12 }}>
              <label>
                Project Name
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Relocation Vlog"
                />
              </label>
              <label>
                Description (optional)
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  placeholder="Briefly describe your video…"
                />
              </label>
              <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
                <button type="button" className="secondary" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={createProject.isPending}>
                  {createProject.isPending ? "Creating…" : "Create Project"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
}
