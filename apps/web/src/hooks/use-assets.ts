"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

/** Matches backend AssetOut */
export interface Asset {
  id: string;
  project_id: string;
  scene_id: string | null;
  type: string;
  storage_key: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
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
