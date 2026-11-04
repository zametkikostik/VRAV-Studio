"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import AssetUploader from "@/components/AssetUploader";
import { useAssets } from "@/hooks/use-assets";

function iconFor(type: string) {
  if (type === "video") return "\ud83c\udfac";
  if (type === "audio") return "\ud83c\udfb5";
  if (type === "image") return "\ud83d\uddbc\ufe0f";
  return "\ud83d\udcc4";
}

function formatSize(bytes: number | null) {
  if (bytes == null) return "\u2014";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProjectAssetsPage() {
  const params = useParams();
  const projectId = String(params.id || "");
  const { data: assets, isLoading, error, refetch } = useAssets(projectId);

  return (
    <AppShell>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0 }}>Project Assets</h1>
          <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
            Upload media for AI / RAG
          </p>
        </div>
        <Link href={`/projects/${projectId}`}>
          <button type="button" className="secondary">
            Back to project
          </button>
        </Link>
      </div>
      <div style={{ marginBottom: 24 }}>
        <AssetUploader projectId={projectId} />
      </div>
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Uploaded files</h2>
      {isLoading && <p className="muted">Loading\u2026</p>}
      {error && (
        <div className="error">
          Failed to load.{" "}
          <button type="button" className="secondary" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}
      {!isLoading && assets?.length === 0 && (
        <p className="muted card" style={{ textAlign: "center" }}>
          No assets yet.
        </p>
      )}
      {assets && assets.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "10px 14px" }}>Name</th>
                <th style={{ padding: "10px 14px" }}>Type</th>
                <th style={{ padding: "10px 14px" }}>Size</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "10px 14px" }}>
                    {iconFor(a.type)} {a.filename || a.id.slice(0, 8)}
                  </td>
                  <td style={{ padding: "10px 14px" }} className="muted">
                    {a.type}
                  </td>
                  <td style={{ padding: "10px 14px" }} className="muted">
                    {formatSize(a.size_bytes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
