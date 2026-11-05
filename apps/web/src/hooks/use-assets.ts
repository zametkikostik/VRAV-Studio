"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { session } from "@/lib/api";

/** Matches backend AssetOut (intelligence fields optional; no public storage_key) */
export interface Asset {
  id: string;
  project_id: string;
  scene_id: string | null;
  type: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  probe_status?: string | null;
  transcription_status?: string | null;
  transcription_provider?: string | null;
  transcript?: string | null;
  transcript_segments?: Array<{ start_ms: number; end_ms: number; text: string }> | null;
  keyframes?: Array<{ index: number; timestamp_ms: number; filename: string }> | null;
}

export interface JobOut {
  id: string;
  organization_id: string;
  project_id: string | null;
  type: string;
  status: string;
  error: string | null;
  created_at?: string | null;
  result_summary?: Record<string, unknown> | null;
}

function requireOrgId(): string {
  const org = session.getOrg();
  if (!org?.id) throw new Error("Organization not selected — log in again");
  return org.id;
}

export function inferAssetType(file: File): "video" | "audio" | "image" | "other" {
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("image/")) return "image";
  return "other";
}

export function useAssets(projectId: string) {
  return useQuery<Asset[]>({
    queryKey: ["assets", projectId],
    queryFn: async () => {
      const { data } = await apiClient.get<Asset[]>(`/projects/${projectId}/assets`);
      return data;
    },
    enabled: typeof window !== "undefined" && Boolean(projectId),
  });
}

export function useUploadAsset(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("asset_type", inferAssetType(file));
      const { data } = await apiClient.post<Asset>(
        `/projects/${projectId}/assets/upload`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
          transformRequest: [
            (body, headers) => {
              if (body instanceof FormData && headers) {
                delete (headers as Record<string, unknown>)["Content-Type"];
              }
              return body;
            },
          ],
        }
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
    },
  });
}

export function useAnalyzeAsset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) => {
      const { data } = await apiClient.post<JobOut>("/jobs/analyze", {
        organization_id: requireOrgId(),
        project_id: projectId,
        asset_id: assetId,
        extract_frames: true,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
    },
  });
}

export function useTranscribeAsset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) => {
      const { data } = await apiClient.post<JobOut>("/jobs/transcribe", {
        organization_id: requireOrgId(),
        project_id: projectId,
        asset_id: assetId,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
    },
  });
}
