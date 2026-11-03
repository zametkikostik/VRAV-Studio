"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/store/auth-store";
import { orgs } from "@/lib/api";

export default function AuthLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const login = useAuthStore((s) => s.login);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await apiClient.post("/auth/login", { email, password });
      login({ access: data.access_token, refresh: data.refresh_token });
      try {
        const list = await orgs.list(data.access_token);
        if (!list.length) {
          await orgs.create(data.access_token, "My Studio", `studio-${Date.now().toString(36)}`);
        }
      } catch {
        /* org bootstrap is best-effort */
      }
      router.push("/dashboard");
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(ax.response?.data?.detail || ax.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ background: "#0b0f14", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="card" style={{ maxWidth: 420, width: "100%", margin: 24, padding: 28 }}>
        <h1 style={{ marginBottom: 4 }}>VRAV Studio</h1>
        <p className="muted" style={{ marginBottom: 20 }}>
          AI-powered video editing
        </p>
        <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
          {error && <div className="error">{error}</div>}
          <label>
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Password
            <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Loading…" : "Sign in"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: 16, textAlign: "center" }}>
          <Link href="/auth/register">Don&apos;t have an account? Register</Link>
        </p>
      </div>
    </div>
  );
}
