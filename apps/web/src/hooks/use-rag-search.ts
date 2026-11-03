"use client";

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface RagSearchRequest {
  project_id: string;
  query: string;
  top_k?: number;
}

export interface RagSearchResult {
  asset_id: string;
  asset_name: string | null;
  asset_type: string | null;
  score: number;
  snippet?: string | null;
}

export interface RagSearchResponse {
  query: string;
  results: RagSearchResult[];
}

export function useRagSearch() {
  return useMutation<RagSearchResponse, Error, RagSearchRequest>({
    mutationFn: async (data) => {
      const { data: body } = await apiClient.post<RagSearchResponse>(
        `/projects/${data.project_id}/search`,
        {
          query: data.query,
          top_k: data.top_k ?? 10,
        }
      );
      return body;
    },
  });
}
