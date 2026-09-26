import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, Loading, PageHeader, Switch } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, num } from "../lib/format";
import type { Credentials } from "../lib/types";

interface TestResult {
  ok: boolean;
  testnet: boolean;
  can_trade: boolean;
  account_type: string;
  permissions: string[];
  balances: { asset: string; free: number; locked: number }[];
}

function BinanceCard({ creds }: { creds: Credentials["binance"] }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(!creds.configured);
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [testnet, setTestnet] = useState(creds.testnet);

  const save = useMutation({
    mutationFn: () => api.put("/settings/binance", { api_key: key, api_secret: secret, testnet }),
    onSuccess: () => {
      setKey("");
      setSecret("");
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["credentials"] });
      qc.invalidateQueries({ queryKey: ["balance"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del("/settings/binance"),
    onSuccess: () => {
      setEditing(true);
      qc.invalidateQueries({ queryKey: ["credentials"] });
    },
  });
  const test = useMutation({ mutationFn: () => api.post<TestResult>("/settings/binance/test") });

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <Card title="Binance" action={creds.configured ? <Badge tone="good"><CheckCircle2 className="size-3" />Conectada{creds.testnet ? " (testnet)" : ""}</Badge> : <Badge>Não configurada</Badge>}>
      {creds.configured && !editing ? (
        <div className="space-y-4">
          <div className="text-sm">
            <div className="text-ink-2">API key</div>
            <div className="font-mono text-ink">{creds.api_key}</div>
            <div className="mt-1 text-xs text-muted">Atualizada em {dateTime(creds.updated_at)} · o segredo nunca é exibido</div>
          </div>
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
          <ErrorBox error={save.error} />
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={save.isPending}>Salvar chaves</Button>
            {creds.configured && <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>}
          </div>
        </form>
      )}
      <div className="mt-5 flex gap-2 rounded-lg bg-surface-2 p-3 text-xs text-ink-2">
        <ShieldCheck className="size-4 shrink-0 text-accent" />
        <div>
          Na Binance, crie a chave com <strong className="text-ink">apenas leitura e Spot Trading</strong>, <strong className="text-ink">sem saque</strong>, e restrinja ao IP do servidor.
          As chaves ficam criptografadas no banco (chave derivada de BT_SECRET_KEY).
        </div>
      </div>
    </Card>
  );
}

function AnthropicCard({ creds }: { creds: Credentials["anthropic"] }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const save = useMutation({
    mutationFn: () => api.put("/settings/anthropic", { api_key: key }),
    onSuccess: () => {
      setKey("");
      qc.invalidateQueries({ queryKey: ["credentials"] });
      qc.invalidateQueries({ queryKey: ["ai-status"] });
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
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field label={creds.configured ? "Nova chave" : "Chave da API"} className="min-w-64 flex-1">
            <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…" required autoComplete="off" />
          </Field>
          <Button type="submit" variant="primary" loading={save.isPending}>Salvar</Button>
          {creds.source === "db" && <Button type="button" variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>Remover</Button>}
        </form>
        <ErrorBox error={save.error ?? remove.error} />
        <p className="text-xs text-muted">Crie a chave em console.anthropic.com. Cada análise consome créditos da sua conta Anthropic.</p>
      </div>
    </Card>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api.post("/auth/password", { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
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
        {change.isSuccess && <p className="text-sm text-good-text">Senha alterada.</p>}
      </div>
    </Card>
  );
}

export function SettingsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  return (
    <>
      <PageHeader title="Configurações" subtitle="Chaves de acesso e segurança da conta." />
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <BinanceCard creds={data.binance} />
          <div className="space-y-4">
            <AnthropicCard creds={data.anthropic} />
            <PasswordCard />
          </div>
        </div>
      )}
    </>
  );
}
