"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { session } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(session.getToken() ? "/dashboard" : "/auth/login");
  }, [router]);
  return (
    <p className="muted" style={{ padding: 24 }}>
      Загрузка…
    </p>
  );
}
