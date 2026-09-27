import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Copy, Download, KeyRound, LogOut, ShieldAlert, ShieldCheck, Smartphone, XCircle } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, Loading, Modal, PageHeader, Segmented, Select, Switch } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, num, timeAgo } from "../lib/format";
import { APP_VERSION, isIOS, isStandalone, useInstallPrompt } from "../lib/pwa";
import type { AIProvider, Credentials, KeyPermissions, SecurityEvent, SecurityStatus, TwoFactorSetup } from "../lib/types";

interface TestResult {
  ok: boolean;
  testnet: boolean;
  can_trade: boolean;
  account_type: string;
  permissions: string[];
  key_permissions: KeyPermissions | null;
  warnings: string[];
  balances: { asset: string; free: number; locked: number }[];
}

function useSecurity() {
  return useQuery({ queryKey: ["security"], queryFn: () => api.get<SecurityStatus>("/security/status") });
}

/** Senha (e código de 2 etapas, se ativado) para confirmar ações sensíveis. */
function StepUpFields({ password, code, onPassword, onCode, twoFactor }: {
  password: string;
  code: string;
  onPassword: (v: string) => void;
  onCode: (v: string) => void;
  twoFactor: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Sua senha do Bot Trader" help="Confirmação: protege suas chaves mesmo se alguém pegar sua sessão aberta.">
        <Input type="password" value={password} onChange={(e) => onPassword(e.target.value)} required autoComplete="current-password" />
      </Field>
      {twoFactor && (
        <Field label="Código de 2 etapas" help="Do app autenticador (ou um código de recuperação).">
          <Input value={code} onChange={(e) => onCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" className="font-mono" />
        </Field>
      )}
    </div>
  );
}

function PermissionList({ perms }: { perms: KeyPermissions }) {
  const rows: { label: string; ok: boolean; text: string }[] = [
    { label: "Saque", ok: !perms.withdrawals, text: perms.withdrawals ? "liberado (recusado)" : "bloqueado" },
    { label: "Spot Trading", ok: perms.spot_trading, text: perms.spot_trading ? "liberado" : "desligado" },
    { label: "Restrição de IP", ok: perms.ip_restricted, text: perms.ip_restricted ? "ativa" : "qualquer IP" },
    { label: "Transferências", ok: !perms.internal_transfer && !perms.universal_transfer, text: perms.internal_transfer || perms.universal_transfer ? "liberadas" : "bloqueadas" },
    { label: "Margem/futuros", ok: !perms.margin && !perms.futures, text: perms.margin || perms.futures ? "liberados" : "bloqueados" },
  ];
  return (
    <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-1.5">
          {r.ok ? <CheckCircle2 className="size-3.5 text-good-text" aria-label="ok" /> : <AlertTriangle className="size-3.5 text-warn-text" aria-label="atenção" />}
          <span className="text-ink-2">{r.label}:</span> <span className="text-ink">{r.text}</span>
        </li>
      ))}
    </ul>
  );
}

function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1 rounded-lg border border-warn/40 px-3 py-2 text-xs text-warn-text">
      {items.map((w) => (
        <li key={w} className="flex gap-1.5">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {w}
        </li>
      ))}
    </ul>
  );
}

function BinanceCard({ creds, twoFactor }: { creds: Credentials["binance"]; twoFactor: boolean }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(!creds.configured);
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [testnet, setTestnet] = useState(creds.testnet);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");

  const save = useMutation({
    mutationFn: () => api.put<{ ok: boolean; warnings: string[] }>("/settings/binance", { api_key: key, api_secret: secret, testnet, password, code: code || null }),
    onSuccess: () => {
      setKey("");
      setSecret("");
      setPassword("");
      setCode("");
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["credentials"] });
      qc.invalidateQueries({ queryKey: ["security-events"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del("/settings/binance"),
    onSuccess: () => {
      setEditing(true);
      qc.invalidateQueries({ queryKey: ["credentials"] });
    },
  });
  const test = useMutation({
    mutationFn: () => api.post<TestResult>("/settings/binance/test"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["credentials"] }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  const perms = test.data?.key_permissions ?? creds.permissions;
  const warnings = test.data?.warnings ?? creds.warnings ?? [];
  return (
    <Card title="Binance" action={creds.configured ? <Badge tone="good"><CheckCircle2 className="size-3" />Conectada{creds.testnet ? " (testnet)" : ""}</Badge> : <Badge>Não configurada</Badge>}>
      {creds.configured && !editing ? (
        <div className="space-y-4">
          <div className="text-sm">
            <div className="text-ink-2">API key</div>
            <div className="font-mono text-ink">{creds.api_key}</div>
            <div className="mt-1 text-xs text-muted">Atualizada em {dateTime(creds.updated_at)} · o segredo nunca é exibido</div>
          </div>
          {perms && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-ink-2">Permissões da chave{creds.checked_at ? ` (conferidas ${timeAgo(creds.checked_at)})` : ""}</div>
              <PermissionList perms={perms} />
            </div>
          )}
          <Warnings items={warnings} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => test.mutate()} loading={test.isPending}>Testar conexão</Button>
            <Button variant="ghost" onClick={() => setEditing(true)}>Trocar chaves</Button>
            <Button variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>Remover</Button>
          </div>
          <ErrorBox error={test.error ?? remove.error} />
          {test.data && (
            <div className="rounded-lg border border-line p-3 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge tone={test.data.can_trade ? "good" : "bad"}>{test.data.can_trade ? "Pode negociar" : "Sem permissão de trade"}</Badge>
                <Badge>{test.data.account_type}</Badge>
              </div>
              {test.data.balances.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2 tabular">
                  {test.data.balances.map((b) => (
                    <span key={b.asset}>{b.asset} <span className="text-ink">{num(b.free + b.locked, 6)}</span></span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <Field label="API key">
            <Input value={key} onChange={(e) => setKey(e.target.value)} required autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="Secret key">
            <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} required autoComplete="new-password" />
          </Field>
          <Switch checked={testnet} onChange={setTestnet} label="Chaves da Spot Testnet (testnet.binance.vision)" />
          <StepUpFields password={password} code={code} onPassword={setPassword} onCode={setCode} twoFactor={twoFactor} />
          <ErrorBox error={save.error} />
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={save.isPending}>Validar e salvar</Button>
            {creds.configured && <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>}
          </div>
        </form>
      )}
      <div className="mt-5 flex gap-2 rounded-lg bg-surface-2 p-3 text-xs text-ink-2">
        <ShieldCheck className="size-4 shrink-0 text-accent" />
        <div>
          Na Binance, crie a chave com <strong className="text-ink">leitura e Spot Trading</strong>, <strong className="text-ink">sem saque</strong>, e restrinja ao IP do servidor.
          O sistema confere as permissões na Binance e <strong className="text-ink">recusa chaves com saque liberado</strong>. As chaves ficam criptografadas no banco.
        </div>
      </div>
    </Card>
  );
}

function useInvalidateAI() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["credentials", "ai-status", "autopilot", "security-events"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

/** Qual IA o sistema usa quando as duas chaves estão cadastradas. */
function AIProviderCard({ creds }: { creds: Credentials }) {
  const invalidate = useInvalidateAI();
  const choose = useMutation({ mutationFn: (provider: AIProvider) => api.put("/settings/ai-provider", { provider }), onSuccess: invalidate });
  const both = creds.anthropic.configured && creds.openai.configured;
  return (
    <Card title="Inteligência artificial" action={creds.ai.active ? <Badge tone="good"><CheckCircle2 className="size-3" />{creds.ai.active_label}</Badge> : <Badge>Nenhuma</Badge>}>
      <div className="space-y-3 text-sm text-ink-2">
        {creds.ai.active ? (
          <p>
            Em uso: <strong className="text-ink">{creds.ai.active_label}</strong>, na conversa, na leitura das notícias e no piloto automático.
          </p>
        ) : (
          <p>Cadastre a chave do <strong className="text-ink">Claude</strong> (Anthropic) ou do <strong className="text-ink">GPT</strong> (OpenAI) abaixo para ligar a análise com IA. Pode ser qualquer uma das duas, ou as duas.</p>
        )}
        {both && creds.ai.active && (
          <div className="flex flex-wrap items-center gap-3">
            <Segmented<AIProvider>
              value={creds.ai.active}
              onChange={(p) => choose.mutate(p)}
              options={[
                { value: "anthropic", label: "Claude" },
                { value: "openai", label: "GPT" },
              ]}
            />
            {choose.isPending && <span className="text-xs text-muted">Trocando…</span>}
          </div>
        )}
        {!both && creds.ai.active && <p className="text-xs text-muted">Cadastre também a outra chave se quiser poder alternar entre as duas.</p>}
        <ErrorBox error={choose.error} />
      </div>
    </Card>
  );
}

function OpenAICard({ creds, twoFactor }: { creds: Credentials["openai"]; twoFactor: boolean }) {
  const invalidate = useInvalidateAI();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(creds.model);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const save = useMutation({
    mutationFn: () => api.put("/settings/openai", { api_key: key, model, password, code: code || null }),
    onSuccess: () => {
      setKey("");
      setPassword("");
      setCode("");
      invalidate();
    },
  });
  const changeModel = useMutation({ mutationFn: (m: string) => api.put("/settings/openai/model", { model: m }), onSuccess: invalidate });
  const remove = useMutation({ mutationFn: () => api.del("/settings/openai"), onSuccess: invalidate });
  const current = creds.configured ? creds.model : model;
  const options = creds.models.some((m) => m.id === current) ? creds.models : [...creds.models, { id: current, label: current }];
  return (
    <Card title="IA (OpenAI GPT)" action={creds.configured ? <Badge tone="good"><CheckCircle2 className="size-3" />Configurada</Badge> : <Badge>Não configurada</Badge>}>
      <div className="space-y-3">
        {creds.configured && (
          <div className="text-sm">
            <div className="text-ink-2">Chave</div>
            <div className="font-mono text-ink">{creds.api_key}</div>
            {creds.source === "env" && <div className="mt-1 text-xs text-muted">Definida por variável de ambiente</div>}
          </div>
        )}
        <Field label="Modelo" help={`As notícias usam o ${creds.fast_model}, mais barato, porque são muitas chamadas pequenas.`}>
          <Select value={current} onChange={(e) => (creds.configured ? changeModel.mutate(e.target.value) : setModel(e.target.value))} disabled={changeModel.isPending}>
            {options.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </Select>
        </Field>
        <ErrorBox error={changeModel.error} />
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field label={creds.configured ? "Nova chave" : "Chave da API"}>
            <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-…" required autoComplete="off" />
          </Field>
          {key && <StepUpFields password={password} code={code} onPassword={setPassword} onCode={setCode} twoFactor={twoFactor} />}
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={save.isPending}>Validar e salvar</Button>
            {creds.source === "db" && <Button type="button" variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>Remover</Button>}
          </div>
        </form>
        <ErrorBox error={save.error ?? remove.error} />
        <p className="text-xs text-muted">
          Crie a chave em platform.openai.com → API keys (a conta precisa ter créditos). Ao salvar, o sistema confere a chave e o modelo na OpenAI; essa consulta não gasta créditos.
        </p>
      </div>
    </Card>
  );
}

function AnthropicCard({ creds, twoFactor }: { creds: Credentials["anthropic"]; twoFactor: boolean }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const save = useMutation({
    mutationFn: () => api.put("/settings/anthropic", { api_key: key, password, code: code || null }),
    onSuccess: () => {
      setKey("");
      setPassword("");
      setCode("");
      qc.invalidateQueries({ queryKey: ["credentials"] });
      qc.invalidateQueries({ queryKey: ["ai-status"] });
      qc.invalidateQueries({ queryKey: ["autopilot"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del("/settings/anthropic"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credentials"] });
      qc.invalidateQueries({ queryKey: ["ai-status"] });
    },
  });
  return (
    <Card title="IA (Anthropic Claude)" action={creds.configured ? <Badge tone="good"><CheckCircle2 className="size-3" />Configurada</Badge> : <Badge>Não configurada</Badge>}>
      <div className="space-y-3">
        {creds.configured && (
          <div className="text-sm">
            <div className="text-ink-2">Chave</div>
            <div className="font-mono text-ink">{creds.api_key}</div>
            <div className="mt-1 text-xs text-muted">Modelo: {creds.model}{creds.source === "env" ? " · definida por variável de ambiente" : ""}</div>
          </div>
        )}
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field label={creds.configured ? "Nova chave" : "Chave da API"}>
            <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…" required autoComplete="off" />
          </Field>
          {key && <StepUpFields password={password} code={code} onPassword={setPassword} onCode={setCode} twoFactor={twoFactor} />}
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={save.isPending}>Salvar</Button>
            {creds.source === "db" && <Button type="button" variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>Remover</Button>}
          </div>
        </form>
        <ErrorBox error={save.error ?? remove.error} />
        <p className="text-xs text-muted">
          Com a chave, a IA analisa os bots, classifica as notícias e ajuda o piloto automático a melhorar as estratégias. Crie em console.anthropic.com; cada análise consome créditos da sua conta.
        </p>
      </div>
    </Card>
  );
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  const text = `Bot Trader — códigos de recuperação\nCada código funciona uma única vez.\n\n${codes.join("\n")}\n`;
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">
        Guarde estes códigos num lugar seguro (gerenciador de senhas ou papel). Se perder o celular, cada um permite entrar <strong className="text-ink">uma vez</strong>. Eles não serão mostrados de novo.
      </p>
      <div className="grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-3 font-mono text-sm text-ink">
        {codes.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => {
            void navigator.clipboard?.writeText(text).then(() => setCopied(true));
          }}
        >
          <Copy className="size-3.5" /> {copied ? "Copiado" : "Copiar"}
        </Button>
        <Button
          size="sm"
          onClick={() => {
            const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
            const a = document.createElement("a");
            a.href = url;
            a.download = "bot-trader-codigos-de-recuperacao.txt";
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          <Download className="size-3.5" /> Baixar .txt
        </Button>
      </div>
    </div>
  );
}

function TwoFactorSetupModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useMutation({ mutationFn: () => api.post<TwoFactorSetup>("/security/2fa/setup", { password }), onSuccess: setSetup });
  const enable = useMutation({
    mutationFn: () => api.post<{ recovery_codes: string[] }>("/security/2fa/enable", { code }),
    onSuccess: (r) => {
      setCodes(r.recovery_codes);
      qc.invalidateQueries({ queryKey: ["security"] });
      qc.invalidateQueries({ queryKey: ["security-events"] });
    },
  });
  const close = () => {
    setPassword("");
    setCode("");
    setSetup(null);
    setCodes(null);
    start.reset();
    enable.reset();
    onClose();
  };
  return (
    <Modal open={open} onClose={close} title="Ativar verificação em duas etapas">
      {codes ? (
        <div className="space-y-4">
          <p className="flex items-center gap-2 text-sm text-good-text"><CheckCircle2 className="size-4" /> Ativada. A partir de agora o login pede o código do app.</p>
          <RecoveryCodes codes={codes} />
          <div className="flex justify-end"><Button variant="primary" onClick={close}>Concluir</Button></div>
        </div>
      ) : setup ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            enable.mutate();
          }}
        >
          <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">
            <li>Abra o app autenticador (Google Authenticator, Authy, 1Password, Microsoft Authenticator).</li>
            <li>Escaneie o QR code abaixo (ou digite a chave manualmente).</li>
            <li>Digite o código de 6 dígitos que aparecer.</li>
          </ol>
          <div className="flex flex-col items-center gap-2">
            <img src={setup.qr} alt="QR code para o app autenticador" className="size-48 rounded-lg bg-white p-2" />
            <code className="rounded bg-surface-2 px-2 py-1 text-xs break-all text-ink">{setup.secret}</code>
          </div>
          <Field label="Código do app">
            <Input value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={8} className="font-mono tracking-widest" autoFocus />
          </Field>
          <ErrorBox error={enable.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={close}>Cancelar</Button>
            <Button type="submit" variant="primary" loading={enable.isPending}>Ativar</Button>
          </div>
        </form>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <p className="text-sm text-ink-2">
            Além da senha, o login passa a pedir um código que muda a cada 30 segundos no seu celular. Mesmo que alguém descubra sua senha, não consegue entrar nem mexer nas chaves.
          </p>
          <Field label="Confirme sua senha">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" autoFocus />
          </Field>
          <ErrorBox error={start.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={close}>Cancelar</Button>
            <Button type="submit" variant="primary" loading={start.isPending}>Continuar</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function StepUpModal({ open, title, intro, confirmLabel, danger, path, onDone, onClose }: {
  open: boolean;
  title: string;
  intro: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  path: string;
  onDone: (r: { recovery_codes?: string[] }) => void;
  onClose: () => void;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const run = useMutation({ mutationFn: () => api.post<{ recovery_codes?: string[] }>(path, { password, code }), onSuccess: onDone });
  const close = () => {
    setPassword("");
    setCode("");
    run.reset();
    onClose();
  };
  return (
    <Modal open={open} onClose={close} title={title}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          run.mutate();
        }}
      >
        <div className="text-sm text-ink-2">{intro}</div>
        <StepUpFields password={password} code={code} onPassword={setPassword} onCode={setCode} twoFactor />
        <ErrorBox error={run.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={close}>Cancelar</Button>
          <Button type="submit" variant={danger ? "danger" : "primary"} loading={run.isPending}>{confirmLabel}</Button>
        </div>
      </form>
    </Modal>
  );
}

function SecurityCard({ status }: { status: SecurityStatus }) {
  const qc = useQueryClient();
  const [modal, setModal] = useState<"setup" | "disable" | "codes" | null>(null);
  const [newCodes, setNewCodes] = useState<string[] | null>(null);
  const logoutOthers = useMutation({
    mutationFn: () => api.post("/auth/logout-all"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["security-events"] }),
  });
  const enabled = status.two_factor.enabled;
  return (
    <Card
      title="Segurança da conta"
      action={enabled ? <Badge tone="good"><ShieldCheck className="size-3" />2 etapas ativa</Badge> : <Badge tone="warn"><ShieldAlert className="size-3" />Só senha</Badge>}
    >
      <div className="space-y-5 text-sm">
        <section className="space-y-2">
          <h3 className="font-medium text-ink">Verificação em duas etapas (2FA)</h3>
          {enabled ? (
            <>
              <p className="text-ink-2">
                O login e as ações sensíveis pedem o código do app autenticador. Códigos de recuperação restantes: <strong className="text-ink">{status.two_factor.recovery_codes_left}</strong>.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setModal("codes")}>Gerar novos códigos de recuperação</Button>
                <Button size="sm" variant="danger" onClick={() => setModal("disable")}>Desativar</Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-ink-2">
                Recomendado: com o 2FA, quem descobrir sua senha ainda precisa do seu celular para entrar, trocar as chaves da Binance ou liberar o piloto automático em bots reais.
              </p>
              <Button size="sm" variant="primary" onClick={() => setModal("setup")}><ShieldCheck className="size-3.5" />Ativar</Button>
            </>
          )}
        </section>
        <section className="space-y-2 border-t border-line pt-4">
          <h3 className="font-medium text-ink">Sessões</h3>
          <p className="text-ink-2">Esqueceu o sistema aberto em outro computador ou celular? Encerre todas as outras sessões; este aparelho continua conectado.</p>
          <Button size="sm" onClick={() => logoutOthers.mutate()} loading={logoutOthers.isPending}><LogOut className="size-3.5" />Sair dos outros aparelhos</Button>
          {logoutOthers.isSuccess && <p className="text-xs text-good-text">Pronto: as outras sessões foram encerradas.</p>}
          <ErrorBox error={logoutOthers.error} />
        </section>
        <ul className="space-y-1 border-t border-line pt-4 text-xs text-ink-2">
          <li className="flex gap-1.5"><CheckCircle2 className="size-3.5 shrink-0 text-good-text" />Chaves criptografadas; o segredo da Binance nunca volta para a tela nem vai para a IA.</li>
          <li className="flex gap-1.5"><CheckCircle2 className="size-3.5 shrink-0 text-good-text" />Bloqueio automático após várias senhas erradas (por IP e por conta).</li>
          <li className="flex gap-1.5"><CheckCircle2 className="size-3.5 shrink-0 text-good-text" />Cookie de sessão protegido (HttpOnly, SameSite=Strict) e proteção contra requisições de outros sites.</li>
        </ul>
      </div>
      <TwoFactorSetupModal open={modal === "setup"} onClose={() => setModal(null)} />
      <StepUpModal
        open={modal === "disable"}
        title="Desativar verificação em duas etapas?"
        intro="A conta volta a ficar protegida só pela senha."
        confirmLabel="Desativar"
        danger
        path="/security/2fa/disable"
        onDone={() => {
          setModal(null);
          qc.invalidateQueries({ queryKey: ["security"] });
          qc.invalidateQueries({ queryKey: ["security-events"] });
        }}
        onClose={() => setModal(null)}
      />
      <StepUpModal
        open={modal === "codes"}
        title="Gerar novos códigos de recuperação"
        intro="Os códigos antigos deixam de funcionar."
        confirmLabel="Gerar"
        path="/security/2fa/recovery-codes"
        onDone={(r) => {
          setModal(null);
          setNewCodes(r.recovery_codes ?? null);
          qc.invalidateQueries({ queryKey: ["security"] });
        }}
        onClose={() => setModal(null)}
      />
      <Modal open={newCodes != null} onClose={() => setNewCodes(null)} title="Novos códigos de recuperação">
        {newCodes && <RecoveryCodes codes={newCodes} />}
      </Modal>
    </Card>
  );
}

/** "Chrome · Windows" a partir do user agent. */
function device(ua: string): string {
  if (!ua) return "";
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "";
  return [browser, os].filter(Boolean).join(" · ") || ua.slice(0, 40);
}

const RISKY = new Set(["login_fail", "login_blocked", "login_2fa_fail", "step_up_fail", "binance_keys_rejected", "2fa_disabled"]);

function ActivityCard() {
  const { data } = useQuery({ queryKey: ["security-events"], queryFn: () => api.get<SecurityEvent[]>("/security/events?limit=30") });
  return (
    <Card title="Atividade recente da conta">
      {data?.length ? (
        <ul className="divide-y divide-line text-sm">
          {data.map((e) => (
            <li key={e.id} className="flex items-start gap-2.5 py-2">
              {RISKY.has(e.kind) ? <XCircle className="mt-0.5 size-4 shrink-0 text-warn-text" aria-label="atenção" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-muted" aria-label="ok" />}
              <div className="min-w-0 flex-1">
                <div className="text-ink">{e.label}{e.detail ? <span className="text-ink-2"> · {e.detail}</span> : null}</div>
                <div className="text-xs text-muted">{[e.ip, device(e.user_agent)].filter(Boolean).join(" · ")}</div>
              </div>
              <span className="shrink-0 text-xs text-muted" title={dateTime(e.created_at)}>{timeAgo(e.created_at)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">Logins, trocas de senha e de chaves aparecem aqui.</p>
      )}
      <p className="mt-3 text-xs text-muted">Viu algo que não reconhece? Troque a senha (isso encerra as outras sessões) e ative as 2 etapas.</p>
    </Card>
  );
}

function InstallCard() {
  const { canInstall, install } = useInstallPrompt();
  const installed = isStandalone();
  return (
    <Card title="App no celular" action={installed ? <Badge tone="good"><CheckCircle2 className="size-3" />Instalado</Badge> : undefined}>
      <div className="space-y-3 text-sm text-ink-2">
        <p className="flex gap-2">
          <Smartphone className="mt-0.5 size-4 shrink-0 text-accent" />
          <span>
            Instale o Bot Trader como app: ícone na tela inicial, abre em tela cheia e carrega mais rápido. Os bots continuam rodando no servidor mesmo com
            o celular desligado.
          </span>
        </p>
        {installed ? (
          <p className="text-xs text-muted">Você já está usando a versão instalada (v{APP_VERSION}).</p>
        ) : canInstall ? (
          <Button variant="primary" onClick={install}><Download className="size-4" />Instalar app</Button>
        ) : isIOS() ? (
          <ol className="list-decimal space-y-1 pl-5 text-xs">
            <li>Abra este site no <strong className="text-ink">Safari</strong>.</li>
            <li>Toque em <strong className="text-ink">Compartilhar</strong> (quadrado com seta para cima).</li>
            <li>Escolha <strong className="text-ink">Adicionar à Tela de Início</strong> e confirme.</li>
          </ol>
        ) : (
          <ol className="list-decimal space-y-1 pl-5 text-xs">
            <li>No Android, abra este site no <strong className="text-ink">Chrome</strong>.</li>
            <li>Toque no menu <strong className="text-ink">⋮</strong> e escolha <strong className="text-ink">Instalar app</strong> (ou Adicionar à tela inicial).</li>
            <li>No computador, use o ícone de instalar na barra de endereço do Chrome ou do Edge.</li>
          </ol>
        )}
      </div>
    </Card>
  );
}

function PasswordCard() {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api.post("/auth/password", { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      qc.invalidateQueries({ queryKey: ["security-events"] });
    },
  });
  return (
    <Card title="Senha de acesso">
      <form
        className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate();
        }}
      >
        <Field label="Senha atual">
          <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
        </Field>
        <Field label="Nova senha">
          <Input type="password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required autoComplete="new-password" />
        </Field>
        <Button type="submit" loading={change.isPending}><KeyRound className="size-4" />Alterar</Button>
      </form>
      <div className="mt-2">
        <ErrorBox error={change.error} />
        {change.isSuccess ? (
          <p className="text-sm text-good-text">Senha alterada. As sessões em outros aparelhos foram encerradas.</p>
        ) : (
          <p className="text-xs text-muted">Trocar a senha encerra as sessões abertas em outros aparelhos.</p>
        )}
      </div>
    </Card>
  );
}

export function SettingsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  const security = useSecurity();
  const twoFactor = security.data?.two_factor.enabled ?? false;
  return (
    <>
      <PageHeader title="Configurações" subtitle="Chaves de acesso e segurança da conta." />
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <BinanceCard creds={data.binance} twoFactor={twoFactor} />
            {security.data && <SecurityCard status={security.data} />}
            <PasswordCard />
          </div>
          <div className="space-y-4">
            <AIProviderCard creds={data} />
            <AnthropicCard creds={data.anthropic} twoFactor={twoFactor} />
            <OpenAICard creds={data.openai} twoFactor={twoFactor} />
            <ActivityCard />
            <InstallCard />
          </div>
        </div>
      )}
    </>
  );
}
