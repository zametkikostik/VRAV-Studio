"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { auth, orgs, session } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("demo@vrav.local");
  const [password, setPassword] = useState("password123");
  const [name, setName] = useState("Demo User");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const tokens =
        mode === "register"
          ? await auth.register(email, password, name)
          : await auth.login(email, password);
      session.save(tokens);
      try {
        const list = await orgs.list(tokens.access_token);
        if (list.length) {
          session.setOrg(list[0]);
        } else {
          const slug = `studio-${Date.now().toString(36)}`;
          const o = await orgs.create(tokens.access_token, "My Studio", slug);
          session.setOrg(o);
        }
      } catch {
        const slug = `studio-${Date.now().toString(36)}`;
        const o = await orgs.create(tokens.access_token, "My Studio", slug);
        session.setOrg(o);
      }
      router.push("/dashboard");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 420, margin: "10vh auto", padding: 16 }}>
      <h1 style={{ marginBottom: 4 }}>VRAV Studio</h1>
      <p className="muted">Войдите или создайте аккаунт</p>
      <form className="card" onSubmit={onSubmit} style={{ display: "grid", gap: 12 }}>
        {mode === "register" && (
          <label>
            Имя
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy}>
          {mode === "login" ? "Войти" : "Зарегистрироваться"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Создать аккаунт" : "Уже есть аккаунт"}
        </button>
      </form>
    </main>
  );
}
