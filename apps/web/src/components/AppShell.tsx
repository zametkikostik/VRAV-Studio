"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { session } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";

const links = [
  { href: "/dashboard", label: "\u041e\u0431\u0437\u043e\u0440" },
  { href: "/projects", label: "\u041f\u0440\u043e\u0435\u043a\u0442\u044b" },
  { href: "/dashboard/ai-chat", label: "AI Chat" },
  { href: "/dashboard/search", label: "Search Assets" },
  { href: "/billing", label: "\u0411\u0438\u043b\u043b\u0438\u043d\u0433" },
  { href: "/settings", label: "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 / BYOK" },
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
          {org ? `Org: ${org.slug}` : "Org \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d"}
        </div>
        <button type="button" className="secondary" style={{ marginTop: 12, width: "100%" }} onClick={logout}>
          \u0412\u044b\u0439\u0442\u0438
        </button>
      </aside>
      <div className="main">{children}</div>
    </div>
  );
}
