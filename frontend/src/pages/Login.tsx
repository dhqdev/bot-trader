import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, ErrorBox, Field, Input } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { LoginResult } from "../lib/types";

export function LoginPage() {
  const { status, refresh } = useAuth();
  const setup = status ? !status.has_users : false;
  const [mode, setMode] = useState<"login" | "register">(setup ? "register" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const registering = setup || mode === "register";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (ticket) {
        await api.post("/auth/login/2fa", { ticket, code: code.trim() });
      } else if (registering) {
        await api.post("/auth/register", { email, password, name });
      } else {
        const res = await api.post<LoginResult>("/auth/login", { email, password });
        if ("two_factor_required" in res) {
          // senha certa: falta o código do app autenticador
          setTicket(res.ticket);
          setPassword("");
          return;
        }
      }
      await refresh();
    } catch (err) {
      setError(err);
      if (ticket && err instanceof Error && /expirou/.test(err.message)) setTicket(null);
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
          {ticket ? (
            <>
              <div>
                <h1 className="flex items-center gap-2 text-base font-semibold">
                  <ShieldCheck className="size-4 text-accent" /> Verificação em duas etapas
                </h1>
                <p className="mt-1 text-sm text-ink-2">Digite o código de 6 dígitos do seu app autenticador (Google Authenticator, Authy, 1Password…).</p>
              </div>
              <Field label="Código" help="Sem o celular? Use um dos códigos de recuperação que você guardou.">
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  minLength={6}
                  maxLength={32}
                  placeholder="000000"
                  className="font-mono tracking-widest"
                />
              </Field>
              <ErrorBox error={error} />
              <Button type="submit" variant="primary" className="w-full" loading={busy}>
                Confirmar
              </Button>
              <button
                type="button"
                className="w-full text-center text-xs text-ink-2 hover:text-ink"
                onClick={() => {
                  setTicket(null);
                  setCode("");
                  setError(null);
                }}
              >
                Voltar
              </button>
            </>
          ) : (
            <>
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
              <Field label="Senha" help={registering ? "Mínimo de 8 caracteres. Use uma senha longa e só deste sistema." : undefined}>
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
            </>
          )}
        </form>
      </div>
    </div>
  );
}
