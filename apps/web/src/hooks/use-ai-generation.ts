"use client";

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface GenerateVideoRequest {
  project_id: string;
  prompt: string;
  top_k?: number;
  model?: string;
}

export interface GenerateVideoResponse {
  job_id: string;
  status: string;
  timeline?: Record<string, unknown> | null;
  selected_asset_ids?: string[];
  plan_source?: string | null;
}

export function useGenerateVideo() {
  return useMutation<GenerateVideoResponse, Error, GenerateVideoRequest>({
    mutationFn: async (data) => {
      const { data: body } = await apiClient.post<GenerateVideoResponse>(
        `/projects/${data.project_id}/generate`,
        {
          prompt: data.prompt,
          top_k: data.top_k ?? 10,
          model: data.model ?? "mock/default",
        }
      );
      return body;
    },
  });
}
