import { useState, type FormEvent } from "react";
import { Button, ErrorBox, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export function LoginPage() {
  const { status, refresh } = useAuth();
  const setup = status ? !status.has_users : false;
  const [mode, setMode] = useState<"login" | "register">(setup ? "register" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const registering = setup || mode === "register";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (registering) await api.post("/auth/register", { email, password, name });
      else await api.post("/auth/login", { email, password });
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-8" />
          <span className="text-lg font-semibold">Bot Trader</span>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-6">
          <div>
            <h1 className="text-base font-semibold">{setup ? "Crie sua conta" : registering ? "Criar conta" : "Entrar"}</h1>
            {setup && <p className="mt-1 text-sm text-ink-2">Primeiro acesso: esta será a conta dona do sistema.</p>}
          </div>
          {registering && (
            <Field label="Nome">
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="E-mail">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus />
          </Field>
          <Field label="Senha" help={registering ? "Mínimo de 8 caracteres" : undefined}>
            <Input
              type="password"
              required
              minLength={registering ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={registering ? "new-password" : "current-password"}
            />
          </Field>
          <ErrorBox error={error} />
          <Button type="submit" variant="primary" className="w-full" loading={busy}>
            {registering ? "Criar conta" : "Entrar"}
          </Button>
          {!setup && status?.registration_open && (
            <button type="button" className="w-full text-center text-xs text-ink-2 hover:text-ink" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Criar uma conta" : "Já tenho conta"}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
