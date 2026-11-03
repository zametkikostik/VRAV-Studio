"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { session } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";

const links = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/projects", label: "Проекты" },
  { href: "/billing", label: "Биллинг" },
  { href: "/settings", label: "Настройки / BYOK" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [org, setOrg] = useState<{ id: string; name: string; slug: string } | null>(null);
  const storeLogout = useAuthStore((s) => s.logout);

  useEffect(() => {
    setOrg(session.getOrg());
  }, []);

  function logout() {
    session.clear();
    storeLogout();
    router.push("/auth/login");
  }

  return (
    <div className="shell">
      <aside className="nav">
        <div className="brand">VRAV Studio</div>
        {links.map((l) => (
          <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
            {l.label}
          </Link>
        ))}
        <div style={{ marginTop: "2rem" }} className="muted">
          {org ? `Org: ${org.slug}` : "Org не выбран"}
        </div>
        <button type="button" className="secondary" style={{ marginTop: 12, width: "100%" }} onClick={logout}>
          Выйти
        </button>
      </aside>
      <div className="main">{children}</div>
    </div>
  );
}
