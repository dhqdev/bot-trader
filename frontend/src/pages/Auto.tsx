import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, ChevronDown, Loader2, Minus, Play, Plus, Power, ShieldAlert, Sparkles } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ModeBadge, VolatilityBadge } from "../components/bot";
import { EquityChart } from "../components/charts";
import { Badge, Button, Card, Confirm, Empty, ErrorBox, Field, Input, Loading, Modal, PageHeader, Pnl, Stat } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, duration, money, pct, timeAgo } from "../lib/format";
import type { AutoAction, AutoCycle, AutoLimits, AutoOverview, AutoPoolRow, AutoRobot, Credentials, SecurityStatus } from "../lib/types";

export function useAuto() {
  return useQuery({
    queryKey: ["auto"],
    queryFn: () => api.get<AutoOverview>("/auto"),
    refetchInterval: (q) => (q.state.data?.running ? 4000 : 15_000),
  });
}

type ActionPath = "start" | "stop" | "run" | "resume";

function useAutoAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: ActionPath; body?: unknown }) => api.post<AutoOverview>(`/auto/${path}`, body),
    onSuccess: (data) => {
      qc.setQueryData(["auto"], data);
      for (const k of ["bots", "dashboard", "system"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
}

/** Aviso no Painel: convite para ligar ou o resumo do que a IA está fazendo. */
export function AutoBanner() {
  const { data } = useAuto();
  if (!data) return null;
  const c = data.config;
  const p = data.performance;
  if (!c.enabled) {
    return (
      <Link to="/auto" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/40 bg-surface px-4 py-3 hover:bg-surface-2">
        <span className="flex items-start gap-2 text-sm">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
          <span>
            <strong className="font-semibold text-ink">Deixe a IA fazer tudo.</strong>{" "}
            <span className="text-ink-2">Ela escolhe as moedas e as estratégias, liga os robôs e troca quem vai mal.</span>
          </span>
        </span>
        <span className="text-sm font-medium text-accent">Ligar o modo automático →</span>
      </Link>
    );
  }
  return (
    <Link to="/auto" className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-xl border border-line bg-surface px-4 py-3 text-sm hover:bg-surface-2">
      <span className="flex flex-wrap items-center gap-2 text-ink">
        <Sparkles className="size-4 text-accent" />
        <strong className="font-semibold">Modo automático ligado</strong>
        <ModeBadge mode={c.mode} />
        {c.paused_reason && <Badge tone="warn">Pausado</Badge>}
        {data.running && <Badge tone="accent"><Loader2 className="size-3 animate-spin" />Testando…</Badge>}
      </span>
      <span className="text-ink-2">
        {p.active_robots} {p.active_robots === 1 ? "robô" : "robôs"} · <Pnl value={p.total_pnl} /> (<Pnl value={p.total_pct} percent />)
      </span>
    </Link>
  );
}

const STEPS = [
  { title: "Testa", text: "Todas as estratégias nas moedas mais negociadas da OKX, no histórico real, já com taxas." },
  { title: "Escolhe", text: "Só as que lucraram no período todo e no recente. A IA escolhe as melhores, uma por moeda." },
  { title: "Opera", text: "Divide o valor e liga os robôs, que compram e vendem sozinhos, com stop em toda operação." },
  { title: "Acompanha", text: "Todo dia confere quem está ganhando ou perdendo e troca quem vai mal." },
];

function Protections({ limits: L }: { limits: AutoLimits }) {
  return (
    <Card title={<span className="flex items-center gap-1.5"><ShieldAlert className="size-4 text-accent" />Proteções</span>}>
      <ul className="list-disc space-y-1.5 pl-4 text-xs text-ink-2">
        <li>Só entram robôs com lucro no teste do período todo <strong className="text-ink">e</strong> do período recente, já descontadas as taxas.</li>
        <li>No máximo {L.max_robots} robôs, um por moeda, com pelo menos {money(L.min_per_robot)} cada.</li>
        <li>Robô que perde {L.robot_loss_pct}% do que recebeu é encerrado e não volta por {L.cooldown_days} dias.</li>
        <li>Se o total perder {L.total_loss_pct}%, tudo para até você mandar retomar.</li>
        <li>Toda operação tem stop. Robô encerrado com compra aberta não compra de novo: vende pela regra normal e então para.</li>
        <li>Volatilidade alta (candles de minutos) fica de fora: nos testes, as taxas comeram o lucro.</li>
      </ul>
    </Card>
  );
}

const ROBOT_STATE: Record<AutoRobot["state"], { label: string; tone: "good" | "warn" | "neutral" }> = {
  active: { label: "Operando", tone: "good" },
  retiring: { label: "Encerrando", tone: "warn" },
  retired: { label: "Encerrado", tone: "neutral" },
};

function RobotRow({ r }: { r: AutoRobot }) {
  const b = r.bot;
  const pos = b.position;
  const state = ROBOT_STATE[r.state];
  return (
    <li className="space-y-1.5 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <Link to={`/bots/${b.id}`} className="min-w-0">
          <div className="truncate font-medium text-ink hover:underline">{b.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <Badge tone={state.tone}>{state.label}</Badge>
            <VolatilityBadge interval={b.interval} />
            {b.strategy_name}
          </div>
        </Link>
        <div className="shrink-0 text-right">
          <Pnl value={b.stats.total_pnl} quote="USDT" className="text-sm font-semibold" />
          <div className="text-xs text-muted">
            <Pnl value={r.pnl_pct} percent /> de {money(r.allocation)}
          </div>
        </div>
      </div>
      {pos ? (
        <p className="text-xs text-ink-2">
          Comprado há {duration(pos.duration_seconds)}: <Pnl value={pos.unrealized_pct} percent />
        </p>
      ) : r.state === "active" ? (
        <p className="text-xs text-ink-2">
          Esperando o momento de comprar · {b.stats.trades} {b.stats.trades === 1 ? "operação" : "operações"}
          {b.last_tick_at ? ` · checado ${timeAgo(b.last_tick_at)}` : ""}
        </p>
      ) : null}
      {r.reason && (
        <p className="text-xs text-ink-2">
          <span className="text-muted">Por que a IA escolheu:</span> {r.reason}
        </p>
      )}
      {r.expected && (
        <p className="text-xs text-muted">
          No teste: {pct(r.expected.return_pct, true, 1)} em {r.expected.days} dias, {pct(r.expected.recent_return_pct, true, 1)} no período recente, queda máxima de{" "}
          {pct(r.expected.drawdown_pct, true, 1)}.
        </p>
      )}
      {r.state !== "active" && r.retire_reason && (
        <p className="text-xs text-warn-text">
          {r.state === "retiring" ? `Encerrando: ${r.retire_reason}. Não compra mais; para ao vender a posição.` : `Encerrado ${timeAgo(r.retired_at)}: ${r.retire_reason}.`}
        </p>
      )}
    </li>
  );
}

function RobotsCard({ robots }: { robots: AutoRobot[] }) {
  return (
    <Card title="Robôs da IA" padded={false}>
      {robots.length ? (
        <ul className="divide-y divide-line">
          {robots.map((r) => (
            <RobotRow key={r.bot_id} r={r} />
          ))}
        </ul>
      ) : (
        <Empty title="Nenhum robô agora">
          Quando nenhum robô passa nos testes, ou o mercado está ruim, a IA deixa o dinheiro parado em USDT e testa de novo no dia seguinte.
        </Empty>
      )}
    </Card>
  );
}

const ACTION_ICON: Record<AutoAction["type"], ReactNode> = {
  create: <Plus className="mt-0.5 size-3.5 shrink-0 text-good-text" aria-label="ligou" />,
  retire: <Minus className="mt-0.5 size-3.5 shrink-0 text-warn-text" aria-label="encerrou" />,
  keep: <Check className="mt-0.5 size-3.5 shrink-0 text-muted" aria-label="manteve" />,
  pause: <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-bad-text" aria-label="pausou" />,
  error: <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-bad-text" aria-label="erro" />,
};
const ACTION_VERB: Record<AutoAction["type"], string> = { create: "Ligou", retire: "Encerrou", keep: "Manteve", pause: "Pausou", error: "Falhou" };
const TRIGGER: Record<AutoCycle["trigger"], string> = { start: "ao ligar", manual: "pedido por você", schedule: "teste diário" };

function PoolTable({ rows }: { rows: AutoPoolRow[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-1 text-xs text-accent hover:underline">
        {open ? "Esconder" : "Ver"} os robôs aprovados neste teste ({rows.length})
        <ChevronDown className={clsx("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs tabular">
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                <th className="py-1.5 pr-3 font-medium">Robô</th>
                <th className="py-1.5 pr-3 text-right font-medium">Período todo</th>
                <th className="py-1.5 pr-3 text-right font-medium">Recente</th>
                <th className="py-1.5 pr-3 text-right font-medium">Queda máx.</th>
                <th className="py-1.5 text-right font-medium">Operações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => (
                <tr key={r.pick}>
                  <td className="py-1.5 pr-3 text-ink">
                    {r.symbol.replace(/USDT$/, "")} · {r.name} <span className="text-muted">({r.days} dias)</span>
                  </td>
                  <td className="py-1.5 pr-3 text-right"><Pnl value={r.return_pct} percent /></td>
                  <td className="py-1.5 pr-3 text-right"><Pnl value={r.recent_return_pct} percent /></td>
                  <td className="py-1.5 pr-3 text-right text-ink-2">{pct(r.drawdown_pct, true, 1)}</td>
                  <td className="py-1.5 text-right text-ink-2">{r.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function History({ cycles }: { cycles: AutoCycle[] }) {
  return (
    <Card title="O que a IA fez">
      {cycles.length === 0 ? (
        <p className="text-sm text-muted">Nada ainda.</p>
      ) : (
        <ol className="space-y-4">
          {cycles.map((c, i) => (
            <li key={c.id} className="space-y-1.5 border-l-2 border-line pl-3">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                <span className="font-medium text-ink-2">{dateTime(c.created_at)}</span>
                <span>· {TRIGGER[c.trigger] ?? c.trigger}</span>
                {c.status === "running" && <Badge tone="accent"><Loader2 className="size-3 animate-spin" />Testando…</Badge>}
                {c.status === "failed" && <Badge tone="bad">Falhou</Badge>}
                {c.ai_model && <span>· decidido pela IA ({c.ai_model})</span>}
              </div>
              {c.summary && <p className="text-sm text-ink">{c.summary}</p>}
              {c.actions.length > 0 && (
                <ul className="space-y-1 text-xs">
                  {c.actions.map((a, j) => (
                    <li key={j} className="flex gap-1.5 text-ink-2">
                      {ACTION_ICON[a.type]}
                      <span>
                        <strong className="font-medium text-ink">
                          {ACTION_VERB[a.type]}
                          {a.name ? ` ${a.name}` : ""}
                        </strong>
                        : {a.text}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {i === 0 && c.pool && c.pool.length > 0 && <PoolTable rows={c.pool} />}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function LiveModal({ open, onClose, data }: { open: boolean; onClose: () => void; data: AutoOverview }) {
  const act = useAutoAction();
  const creds = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials"), enabled: open });
  const security = useQuery({ queryKey: ["security"], queryFn: () => api.get<SecurityStatus>("/security/status"), enabled: open });
  const [budget, setBudget] = useState(data.config.mode === "live" ? String(data.config.budget) : "");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [agree, setAgree] = useState(false);
  const L = data.limits;
  const noKeys = creds.data != null && !creds.data.okx.configured;
  const close = () => {
    act.reset();
    setPassword("");
    setCode("");
    onClose();
  };
  return (
    <Modal open={open} onClose={close} title="Deixar a IA usar dinheiro real?">
      {noKeys ? (
        <div className="space-y-4 text-sm text-ink-2">
          <p>Para usar dinheiro real, cadastre antes a chave da OKX, só com Leitura e Negociação (nunca Saque).</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Cancelar</Button>
            <Link to="/settings" className="inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-medium text-accent-ink hover:brightness-110">
              Ir para Configurações
            </Link>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            act.mutate({ path: "start", body: { mode: "live", budget: Number(budget.replace(",", ".")), password, code: code || null } }, { onSuccess: close });
          }}
        >
          <p className="text-sm text-ink-2">
            A IA vai criar e ligar robôs que enviam ordens reais à OKX, e trocar os que forem mal, sem perguntar. Se o simulado estiver ligado, os robôs dele são
            encerrados.
          </p>
          <Field
            label="Quanto a IA pode usar no total (USDT)"
            help={`Dividido em até ${L.max_robots} robôs, com pelo menos ${money(L.min_per_robot)} cada. Use só um valor que você aceita perder.`}
          >
            <Input inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} required placeholder="ex.: 100" autoFocus />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Sua senha">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            </Field>
            {security.data?.two_factor.enabled && (
              <Field label="Código de 2 etapas">
                <Input value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" className="font-mono" />
              </Field>
            )}
          </div>
          <label className="flex items-start gap-2 text-sm text-ink-2">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
            Entendo que resultado de teste não garante lucro e que posso perder dinheiro.
          </label>
          <ErrorBox error={act.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={close}>Cancelar</Button>
            <Button type="submit" variant="primary" loading={act.isPending} disabled={!agree}>Ligar com dinheiro real</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function OffView({ data }: { data: AutoOverview }) {
  const act = useAutoAction();
  const [live, setLive] = useState(false);
  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-5">
          <div className="flex items-start gap-3">
            <div className="grid size-10 shrink-0 place-items-center rounded-full bg-accent/15 text-accent">
              <Sparkles className="size-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-ink">Você liga, a IA faz o resto</h2>
              <p className="mt-1 text-sm text-ink-2">Nenhum campo para preencher: ela escolhe a moeda, a estratégia, o tempo de candle e quanto vai em cada robô.</p>
            </div>
          </div>
          <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-lg border border-line p-3">
                <div className="text-xs font-medium text-accent">{i + 1}. {s.title}</div>
                <p className="mt-1 text-xs text-ink-2">{s.text}</p>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => act.mutate({ path: "start", body: { mode: "paper" } })} loading={act.isPending}>
              <Power className="size-4" />
              Ligar no simulado
            </Button>
            <Button onClick={() => setLive(true)}>Usar dinheiro real</Button>
          </div>
          <p className="text-xs text-muted">
            No simulado a IA usa {money(data.limits.default_paper_budget)} de mentira, com preços reais, taxas e slippage. Sem risco: deixe rodar alguns dias e veja
            se ela ganha antes de passar para o real.
          </p>
          {!data.ai_configured && (
            <p className="text-xs text-warn-text">
              Sem chave de IA, a escolha segue o ranking dos testes. Para o Claude ou o GPT decidirem, cadastre a chave em{" "}
              <Link to="/settings" className="underline">Configurações</Link>.
            </p>
          )}
          <ErrorBox error={act.error} />
        </div>
      </Card>
      <Protections limits={data.limits} />
      {data.cycles.length > 0 && <History cycles={data.cycles} />}
      <LiveModal open={live} onClose={() => setLive(false)} data={data} />
    </div>
  );
}

function OnView({ data }: { data: AutoOverview }) {
  const act = useAutoAction();
  const [confirm, setConfirm] = useState<"off" | "paper" | null>(null);
  const [live, setLive] = useState(false);
  const c = data.config;
  const p = data.performance;
  const pending = (path: ActionPath) => act.isPending && act.variables?.path === path;
  return (
    <div className="space-y-4">
      {c.paused_reason && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/40 bg-surface px-4 py-3 text-sm">
          <span className="flex gap-2 text-warn-text">
            <ShieldAlert className="mt-0.5 size-4 shrink-0" />
            {c.paused_reason}
          </span>
          <Button size="sm" variant="primary" onClick={() => act.mutate({ path: "resume" })} loading={pending("resume")}>Retomar</Button>
        </div>
      )}
      {data.running && (
        <div className="flex items-center gap-2 rounded-xl border border-accent/40 bg-surface px-4 py-3 text-sm text-ink-2">
          <Loader2 className="size-4 shrink-0 animate-spin text-accent" />
          A IA está testando as moedas e escolhendo os robôs. Leva de alguns segundos a alguns minutos.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="rounded-xl border border-line bg-surface px-5 py-4 lg:col-span-2">
          <div className="flex items-center gap-2 text-xs text-ink-2">
            Resultado da IA <ModeBadge mode={c.mode} />
          </div>
          <div className="mt-1 text-5xl font-semibold tracking-tight">
            <Pnl value={p.total_pnl} quote="" proportional />
            <span className="ml-2 text-lg font-normal text-muted">USDT</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
            <span><Pnl value={p.total_pct} percent /> do valor</span>
            <span>Hoje <Pnl value={p.today_pnl} /></span>
            <span>Realizado <Pnl value={p.realized_pnl} /></span>
            <span>Em aberto <Pnl value={p.unrealized_pnl} /></span>
          </div>
        </div>
        <Stat label="Robôs operando" value={`${p.active_robots} de ${c.slots}`} sub={`${money(c.allocation)} cada · ${money(c.budget)} no total`} />
        <Stat label="Taxa de acerto" value={p.win_rate == null ? "–" : pct(p.win_rate, false, 0)} sub={`${p.wins} de ${p.trades} operações com lucro`} />
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-2">
            {c.last_run_at ? `Último teste ${timeAgo(c.last_run_at)}` : data.running ? "Primeiro teste em andamento" : "Ainda sem teste concluído"}
            {c.next_run_at && !c.paused_reason && !data.running ? ` · próximo: ${dateTime(c.next_run_at)}` : ""}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => act.mutate({ path: "run" })} disabled={data.running || Boolean(c.paused_reason)} loading={pending("run")}>
              <Play className="size-3.5" />
              Testar agora
            </Button>
            {c.mode === "paper" ? (
              <Button size="sm" onClick={() => setLive(true)}>Usar dinheiro real</Button>
            ) : (
              <Button size="sm" onClick={() => setConfirm("paper")}>Voltar ao simulado</Button>
            )}
            <Button size="sm" variant="danger" onClick={() => setConfirm("off")}>
              <Power className="size-3.5" />
              Desligar
            </Button>
          </div>
        </div>
        {!confirm && <div className="mt-3 empty:hidden"><ErrorBox error={act.error} /></div>}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Resultado acumulado" className="lg:col-span-2">
          {data.equity_curve.length > 1 ? (
            <EquityChart data={data.equity_curve} />
          ) : (
            <Empty title="Sem operações fechadas ainda">A curva aparece depois da primeira venda. Os robôs lentos podem levar dias para comprar.</Empty>
          )}
        </Card>
        <Protections limits={data.limits} />
      </div>

      <RobotsCard robots={data.robots} />
      <History cycles={data.cycles} />

      <Confirm
        open={confirm === "off"}
        title="Desligar o modo automático?"
        message="Os robôs da IA param de comprar. Quem tem compra aberta vende pela regra normal (sinal, stop ou alvo) e então para: nada é vendido na hora."
        confirmLabel="Desligar"
        danger
        loading={pending("stop")}
        onConfirm={() => act.mutate({ path: "stop" }, { onSuccess: () => setConfirm(null) })}
        onClose={() => setConfirm(null)}
      />
      <Confirm
        open={confirm === "paper"}
        title="Voltar ao simulado?"
        message={`Os robôs com dinheiro real param de comprar e vendem pela regra normal. A IA passa a operar no simulado, com ${money(data.limits.default_paper_budget)} de mentira.`}
        confirmLabel="Voltar ao simulado"
        loading={pending("start")}
        onConfirm={() => act.mutate({ path: "start", body: { mode: "paper" } }, { onSuccess: () => setConfirm(null) })}
        onClose={() => setConfirm(null)}
      />
      <LiveModal open={live} onClose={() => setLive(false)} data={data} />
    </div>
  );
}

export function AutoPage() {
  const { data, isLoading, error } = useAuto();
  const header = (
    <PageHeader
      title="Modo automático"
      subtitle="Você liga e a IA faz o resto: escolhe as moedas e as estratégias, testa no histórico, liga os robôs, acompanha se está ganhando ou perdendo e troca quem vai mal."
    />
  );
  if (isLoading) return <>{header}<Loading /></>;
  if (error || !data) return <>{header}<ErrorBox error={error} /></>;
  return (
    <>
      {header}
      {data.config.enabled ? <OnView data={data} /> : <OffView data={data} />}
    </>
  );
}
