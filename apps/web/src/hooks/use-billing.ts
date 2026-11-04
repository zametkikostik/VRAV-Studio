"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { session } from "@/lib/api";

export interface CreditBalance {
  organization_id?: string;
  balance: string;
  reserved: string;
  available: string;
}

export interface LedgerEntry {
  id: string;
  type: string;
  amount: string;
  balance_after: string;
  description: string;
  created_at: string | null;
}

export interface PlanRow {
  id: string;
  name: string;
  price_monthly?: string;
  currency?: string;
  included_credits?: string;
  source?: string;
}

function orgId(): string {
  const org = session.getOrg();
  if (!org?.id) throw new Error("No organization selected");
  return org.id;
}

export function useCreditBalance() {
  return useQuery<CreditBalance>({
    queryKey: ["billing", "balance"],
    queryFn: async () => {
      const id = orgId();
      const { data } = await apiClient.get<CreditBalance>(`/billing/credits/${id}`);
      return data;
    },
    enabled: typeof window !== "undefined" && Boolean(session.getToken() && session.getOrg()),
  });
}

export function useLedger(limit = 50) {
  return useQuery<LedgerEntry[]>({
    queryKey: ["billing", "ledger", limit],
    queryFn: async () => {
      const id = orgId();
      const { data } = await apiClient.get<LedgerEntry[]>(`/billing/ledger/${id}`, {
        params: { limit },
      });
      return data;
    },
    enabled: typeof window !== "undefined" && Boolean(session.getToken() && session.getOrg()),
  });
}

export function usePlans() {
  return useQuery<PlanRow[]>({
    queryKey: ["billing", "plans"],
    queryFn: async () => {
      const { data } = await apiClient.get<PlanRow[]>("/billing/plans");
      return data;
    },
  });
}

export function useDevTopup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (amount: string) => {
      const { data } = await apiClient.post<{ balance: string; reserved?: string }>(
        "/billing/credits/topup",
        { organization_id: orgId(), amount }
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing"] });
    },
  });
}
