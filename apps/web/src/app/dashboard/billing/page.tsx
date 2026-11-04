"use client";

import { useCreditBalance, useDevTopup, useLedger, usePlans } from "@/hooks/use-billing";

function fmt(v: string | undefined) {
  if (v == null || v === "") return "0";
  const n = Number(v);
  if (Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return v;
}

function typeClass(t: string) {
  const x = t.toLowerCase();
  if (x.includes("topup") || x.includes("credit") || x.includes("grant")) return { color: "var(--accent2)" };
  if (x.includes("spend") || x.includes("debit") || x.includes("commit")) return { color: "var(--danger)" };
  return { color: "var(--muted)" };
}

export default function DashboardBillingPage() {
  const { data: balance, isLoading: balLoading, error: balErr, refetch: refetchBal } = useCreditBalance();
  const { data: ledger, isLoading: ledLoading, error: ledErr, refetch: refetchLed } = useLedger(50);
  const { data: plans } = usePlans();
  const topup = useDevTopup();

  const loading = balLoading || ledLoading;

  return (
    <div style={{ maxWidth: 960 }}>
      <h1 style={{ marginBottom: 4 }}>Billing & Credits</h1>
      <p className="muted" style={{ marginBottom: 20 }}>
        Organization credit balance and immutable ledger history.
      </p>

      {balErr && (
        <div className="error card" style={{ marginBottom: 12 }}>
          Failed to load balance.{" "}
          <button type="button" className="secondary" onClick={() => refetchBal()}>
            Retry
          </button>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          marginBottom: 24,
        }}
      >
        <div className="card" style={{ background: "linear-gradient(135deg,#3d5afe,#6c8cff)", color: "#fff" }}>
          <div style={{ opacity: 0.85, fontSize: 12, textTransform: "uppercase" }}>Available</div>
          <div style={{ fontSize: 32, fontWeight: 700, marginTop: 8 }}>{fmt(balance?.available)}</div>
          <div style={{ opacity: 0.85, fontSize: 12, marginTop: 4 }}>Ready for AI usage</div>
        </div>
        <div className="card">
          <div className="muted" style={{ fontSize: 12, textTransform: "uppercase" }}>Reserved</div>
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{fmt(balance?.reserved)}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Locked in active jobs</div>
        </div>
        <div className="card">
          <div className="muted" style={{ fontSize: 12, textTransform: "uppercase" }}>Balance</div>
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{fmt(balance?.balance)}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Gross credits</div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 8 }}>
          <button
            type="button"
            disabled={topup.isPending}
            onClick={() =>
              topup.mutate("100.0000", {
                onError: (e: unknown) => {
                  const ax = e as { response?: { data?: { detail?: string } }; message?: string };
                  alert(ax.response?.data?.detail || ax.message || "Top-up failed");
                },
              })
            }
          >
            {topup.isPending ? "\u2026" : "Top up 100 (dev)"}
          </button>
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            Prod: Stripe / YooKassa checkout
          </p>
        </div>
      </div>

      {plans && plans.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <strong>Plans</strong>
          <ul className="muted" style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 14 }}>
            {plans.map((p) => (
              <li key={p.id}>
                {p.name}
                {p.price_monthly != null ? ` \u2014 ${p.price_monthly} ${p.currency || ""}` : ""}
                {p.included_credits != null ? ` \u00b7 ${p.included_credits} credits` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
          <strong>Ledger history</strong>
          <button type="button" className="secondary" onClick={() => refetchLed()}>
            Refresh
          </button>
        </div>
        {loading && <p className="muted" style={{ padding: 16 }}>Loading\u2026</p>}
        {ledErr && <p className="error" style={{ padding: 16 }}>Failed to load ledger</p>}
        {!loading && ledger && ledger.length === 0 && (
          <p className="muted" style={{ padding: 16, textAlign: "center" }}>No transactions yet.</p>
        )}
        {ledger && ledger.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "10px 14px" }}>Date</th>
                <th style={{ padding: "10px 14px" }}>Type</th>
                <th style={{ padding: "10px 14px" }}>Description</th>
                <th style={{ padding: "10px 14px", textAlign: "right" }}>Amount</th>
                <th style={{ padding: "10px 14px", textAlign: "right" }}>Balance</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((tx) => {
                const amt = Number(tx.amount);
                const pos = Number.isFinite(amt) ? amt >= 0 : !String(tx.amount).startsWith("-");
                return (
                  <tr key={tx.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 14px" }} className="muted">
                      {tx.created_at ? new Date(tx.created_at).toLocaleString() : "\u2014"}
                    </td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ ...typeClass(tx.type), fontWeight: 600, fontSize: 12 }}>{tx.type}</span>
                    </td>
                    <td style={{ padding: "10px 14px" }}>{tx.description || "\u2014"}</td>
                    <td style={{ padding: "10px 14px", textAlign: "right", color: pos ? "var(--accent2)" : "var(--danger)", fontWeight: 600 }}>
                      {pos ? "+" : ""}{fmt(tx.amount)}
                    </td>
                    <td style={{ padding: "10px 14px", textAlign: "right", fontWeight: 600 }}>{fmt(tx.balance_after)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
