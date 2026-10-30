"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { session } from "@/lib/api";

const links = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/projects", label: "Проекты" },
  { href: "/billing", label: "Биллинг" },
  { href: "/settings", label: "Настройки / BYOK" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const org = typeof window !== "undefined" ? session.getOrg() : null;

  function logout() {
    session.clear();
    router.push("/login");
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
