"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { billing, licenses, session } from "@/lib/api";

export default function BillingPage() {
  const router = useRouter();
  const [available, setAvailable] = useState("—");
  const [licenseKey, setLicenseKey] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  async function refresh() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    const c = await billing.credits(token, org.id);
    setAvailable(c.available ?? c.balance);
  }

  useEffect(() => {
    if (!session.getToken()) {
      router.replace("/login");
      return;
    }
    refresh().catch((e) => setError(String(e)));
  }, [router]);

  async function topup() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    setError("");
    try {
      await billing.topup(token, org.id, "100.0000");
      setMsg("Начислено 100 credits (dev topup)");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function issueLicense() {
    const token = session.getToken();
    const org = session.getOrg();
    if (!token || !org) return;
    try {
      const r = await licenses.issue(token, org.id);
      setLicenseKey(r.license_key);
      setMsg("Лицензия создана");
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <AppShell>
      <h1>Биллинг</h1>
      <div className="grid2">
        <div className="card">
          <strong>Credits</strong>
          <p style={{ fontSize: 28, margin: "8px 0" }}>{available}</p>
          <button type="button" onClick={topup}>Top-up 100 (dev)</button>
          <p className="muted" style={{ marginTop: 8 }}>Прод: Stripe / YooKassa checkout</p>
        </div>
        <div className="card">
          <strong>Self-hosted license</strong>
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" onClick={issueLicense}>Выпустить ключ</button>
          </div>
          {licenseKey && (
            <pre style={{ marginTop: 12, fontSize: 13, wordBreak: "break-all" }}>{licenseKey}</pre>
          )}
        </div>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </AppShell>
  );
}
