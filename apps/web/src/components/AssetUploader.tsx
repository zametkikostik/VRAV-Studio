"use client";

import { useCallback, useState } from "react";
import { useUploadAsset } from "@/hooks/use-assets";

interface AssetUploaderProps {
  projectId: string;
}

export default function AssetUploader({ projectId }: AssetUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState("");
  const uploadAsset = useUploadAsset(projectId);

  const acceptFile = useCallback(
    (file: File) => {
      const ok =
        file.type.startsWith("video/") ||
        file.type.startsWith("audio/") ||
        file.type.startsWith("image/") ||
        /\.(mp4|mov|webm|mp3|wav|png|jpe?g|gif|webp)$/i.test(file.name);
      if (!ok) {
        setLocalError(`Unsupported type: ${file.name}`);
        return;
      }
      setLocalError("");
      uploadAsset.mutate(file, {
        onError: (err: unknown) => {
          const ax = err as { response?: { data?: { detail?: string } }; message?: string };
          setLocalError(ax.response?.data?.detail || ax.message || "Upload failed");
        },
      });
    },
    [uploadAsset]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setIsDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        Array.from(e.dataTransfer.files).forEach(acceptFile);
      }}
      className="card"
      style={{
        borderStyle: "dashed",
        borderColor: isDragging ? "var(--accent)" : "var(--border)",
        background: isDragging ? "rgba(108,140,255,0.08)" : undefined,
        textAlign: "center",
        padding: 28,
      }}
    >
      <p style={{ margin: "0 0 8px", fontWeight: 600 }}>Upload media</p>
      <p className="muted" style={{ margin: "0 0 12px", fontSize: 13 }}>
        Drag & drop video, audio, or images — or choose files
      </p>
      <label style={{ display: "inline-block", cursor: "pointer" }}>
        <span
          style={{
            display: "inline-block",
            padding: "8px 14px",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          Browse files
        </span>
        <input
          type="file"
          multiple
          accept="video/*,audio/*,image/*"
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files) Array.from(e.target.files).forEach(acceptFile);
            e.target.value = "";
          }}
        />
      </label>
      <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
        MP4, MOV, MP3, WAV, PNG, JPEG…
      </p>
      {uploadAsset.isPending && (
        <p style={{ marginTop: 12, color: "var(--accent)" }}>Uploading…</p>
      )}
      {localError && (
        <p className="error" style={{ marginTop: 12 }}>
          {localError}
        </p>
      )}
    </div>
  );
}
