"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { session } from "@/lib/api";

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  organization_id: string;
  status?: string;
  created_at?: string | null;
}

function requireOrgId(): string {
  const org = session.getOrg();
  if (!org?.id) {
    throw new Error("Organization not selected — log in again");
  }
  return org.id;
}

export function useProjects() {
  return useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: async () => {
      const orgId = requireOrgId();
      const { data } = await apiClient.get<Project[]>(`/organizations/${orgId}/projects`);
      return data;
    },
    enabled: typeof window !== "undefined",
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: { name: string; description?: string }) => {
      const organization_id = requireOrgId();
      const { data } = await apiClient.post<Project>("/projects", {
        organization_id,
        name: input.name,
        description: input.description || null,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
