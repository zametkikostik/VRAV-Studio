"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { session } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const checkAuth = useAuthStore((s) => s.checkAuth);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    checkAuth();
    const token = session.getToken();
    if (!token) {
      router.replace("/auth/login");
    }
  }, [checkAuth, router]);

  if (typeof window !== "undefined" && !session.getToken() && !isAuthenticated) {
    return (
      <p className="muted" style={{ padding: 24 }}>
        Redirecting…
      </p>
    );
  }

  return <AppShell>{children}</AppShell>;
}
