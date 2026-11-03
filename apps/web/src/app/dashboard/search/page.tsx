"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useProjects } from "@/hooks/use-projects";
import { RagSearchResult, useRagSearch } from "@/hooks/use-rag-search";

export default function SearchPage() {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RagSearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [formError, setFormError] = useState("");

  const { data: projects, isLoading: projectsLoading } = useProjects();
  const searchAssets = useRagSearch();

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setResults([]);
    if (!selectedProjectId || !query.trim()) return;

    try {
      const response = await searchAssets.mutateAsync({
        project_id: selectedProjectId,
        query: query.trim(),
        top_k: 10,
      });
      setResults(response.results || []);
      setSearchedQuery(response.query);
      if (!(response.results || []).length) {
        setFormError(
          "No matching assets. Ensure the project has assets with embeddings (or transcripts)."
        );
      }
    } catch (err: unknown) {
      const ax = err as {
        response?: { status?: number; data?: { detail?: string } };
        message?: string;
      };
      let detail = ax.response?.data?.detail || ax.message || "Search failed";
      if (ax.response?.status === 429) {
        detail = "Rate limit exceeded (30 searches/min). Wait and try again.";
      }
      setFormError(detail);
    }
  }

  if (projectsLoading) {
    return <p className="muted">Loading projects\u2026</p>;
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <h1 style={{ marginBottom: 4 }}>Semantic Asset Search</h1>
      <p className="muted" style={{ marginBottom: 20 }}>
        Natural-language search over project video/audio assets (RAG + embeddings).
      </p>

      <form className="card" onSubmit={handleSearch} style={{ display: "grid", gap: 14 }}>
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
            No projects. <Link href="/projects">Create one first</Link>.
          </p>
        )}

        <label>
          Search Query
          <input
            type="text"
            required
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. talking about moving to Bulgaria, sunset timelapse"
            style={{ marginTop: 6 }}
          />
        </label>

        {formError && <div className="error">{formError}</div>}

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="submit"
            disabled={!selectedProjectId || !query.trim() || searchAssets.isPending}
          >
            {searchAssets.isPending ? "Searching\u2026" : "Search Assets"}
          </button>
        </div>
      </form>

      {results.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 18 }}>
            Found {results.length} asset(s)
            {searchedQuery ? (
              <span className="muted" style={{ fontWeight: 400, fontSize: 14 }}>
                {" "}for \u201c{searchedQuery}\u201d
              </span>
            ) : null}
          </h2>
          <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
            {results.map((result) => (
              <div
                key={result.asset_id}
                className="card row"
                style={{ justifyContent: "space-between" }}
              >
                <div>
                  <strong>{result.asset_name || result.asset_id.slice(0, 8)}</strong>
                  <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    Type: {result.asset_type || "unknown"}
                  </div>
                  {result.snippet ? (
                    <p className="muted" style={{ fontSize: 13, marginTop: 8, fontStyle: "italic" }}>
                      \u201c{result.snippet}\u201d
                    </p>
                  ) : null}
                </div>
                <div>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "4px 8px",
                      borderRadius: 6,
                      background: "rgba(108,140,255,0.15)",
                      color: "var(--accent)",
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    Score: {result.score.toFixed(3)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
