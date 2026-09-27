import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Bot as BotIcon, BrainCircuit, Check, ChevronDown, CircleMinus, Info, Loader2, Play, RotateCcw, Sparkles, Trash2, X, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { AITabs } from "../components/aitabs";
import { ModeBadge } from "../components/bot";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Loading, Modal, PageHeader, Select, Switch } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, INTERVAL_LABELS, num, pct, signedMoney, timeAgo } from "../lib/format";
import type { AutopilotBot, AutopilotConfig, AutopilotMode, AutopilotOverview, Finding, Insight, OptimizationRun, RunChange, RunMetrics, RunStatus, SecurityStatus } from "../lib/types";
import { MarkdownView } from "./AI";

export const RUN_STATUS: Record<RunStatus, { label: string; tone: "good" | "bad" | "warn" | "neutral" | "accent" }> = {
  running: { label: "Analisando…", tone: "accent" },
  suggested: { label: "Sugestão pendente", tone: "warn" },
  applied: { label: "Aplicada", tone: "good" },
  rejected: { label: "Recusada", tone: "neutral" },
  reverted: { label: "Desfeita", tone: "neutral" },
  no_change: { label: "Sem mudança", tone: "neutral" },
  failed: { label: "Falhou", tone: "bad" },
  superseded: { label: "Substituída", tone: "neutral" },
};

const MODE_OPTIONS: { value: AutopilotMode; label: string }[] = [
  { value: "auto_paper", label: "Aplica sozinho nos simulados (padrão)" },
  { value: "suggest", label: "Só sugere (você aprova)" },
  { value: "auto_all", label: "Aplica sozinho também nos reais" },
  { value: "off", label: "Desligado" },
];

const FREQUENCIES = [
  { value: 24, label: "Todo dia" },
  { value: 72, label: "A cada 3 dias" },
  { value: 168, label: "Toda semana" },
  { value: 336, label: "A cada 2 semanas" },
];

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const s = RUN_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return (
    <Badge tone={s.tone}>
      {status === "running" && <Loader2 className="size-3 animate-spin" />}
      {s.label}
    </Badge>
  );
}

function value(v: unknown): string {
  if (typeof v === "boolean") return v ? "ligado" : "desligado";
  if (typeof v === "number") return num(v, 4);
  if (Array.isArray(v)) return v.length ? v.map((t) => (typeof t === "object" && t && "pct" in t ? `+${num((t as { pct: number }).pct)}%` : String(t))).join(", ") : "nenhum";
  if (v == null || v === "") return "–";
  return String(v);
}

function ChangeList({ changes }: { changes: RunChange[] }) {
  return (
    <ul className="space-y-0.5 text-xs text-ink-2">
      {changes.map((c) => (
        <li key={c.field}>
          {c.label}: <span className="text-ink">{value(c.from)}</span> → <span className="font-medium text-ink">{value(c.to)}</span>
        </li>
      ))}
    </ul>
  );
}

const FINDING_ICON = {
  bad: <XCircle className="mt-0.5 size-4 shrink-0 text-bad-text" aria-label="problema" />,
  warn: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-text" aria-label="atenção" />,
  info: <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-label="informação" />,
};

export function Findings({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <p className="text-sm text-good-text">Nenhum problema encontrado no histórico do bot.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {findings.map((f) => (
        <li key={f.code} className="flex gap-2 text-ink-2">
          {FINDING_ICON[f.level]}
          <span>{f.text}</span>
        </li>
      ))}
    </ul>
  );
}

function MetricCells({ m }: { m: RunMetrics | null | undefined }) {
  if (!m) return <td colSpan={2} className="py-1.5 pr-3 text-right text-muted">–</td>;
  return (
    <>
      <td className="py-1.5 pr-3 text-right tabular">{pct(m.return_pct, true, 1)}</td>
      <td className="py-1.5 pr-3 text-right text-ink-2 tabular">{pct(m.drawdown_pct, false, 1)} · {m.trades} op.</td>
    </>
  );
}

function Comparison({ run }: { run: OptimizationRun }) {
  const base = run.baseline;
  const cand = run.candidate?.results;
  if (!base) return null;
  const rows: { label: ReactNode; b?: RunMetrics; c?: RunMetrics }[] = [
    { label: <>Escolha <span className="text-muted">(2/3 antigos)</span></>, b: base.in, c: cand?.in },
    { label: <>Confirmação <span className="text-muted">(1/3 recente)</span></>, b: base.out, c: cand?.out },
    { label: "Período todo", b: base.full, c: cand?.full },
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            <th className="py-1.5 pr-3 font-medium">Backtest</th>
            <th className="py-1.5 pr-3 text-right font-medium" colSpan={2}>Atual (retorno · queda)</th>
            {cand && <th className="py-1.5 pr-3 text-right font-medium" colSpan={2}>Com a mudança</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="py-1.5 pr-3 text-ink-2">{r.label}</td>
              <MetricCells m={r.b} />
              {cand && <MetricCells m={r.c} />}
            </tr>
          ))}
        </tbody>
      </table>
      {cand?.cross && (
        <p className="mt-2 text-xs text-muted">
          Em outros pares ({cand.cross.pairs?.map((p) => p.symbol).join(", ")}), a mudança variou o placar em {num(cand.cross.delta, 1)} ponto(s) em média.
        </p>
      )}
    </div>
  );
}

function RunDetail({ runId, onClose }: { runId: number | null; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["autopilot-run", runId],
    queryFn: () => api.get<OptimizationRun>(`/autopilot/runs/${runId}`),
    enabled: runId != null,
  });
  const period = data?.baseline_full?.period;
  return (
    <Modal open={runId != null} onClose={onClose} title="Ciclo do piloto automático" wide>
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && (
        <div className="max-h-[75vh] space-y-5 overflow-y-auto pr-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <RunStatusBadge status={data.status} />
            <span>{dateTime(data.created_at)}</span>
            <span>· {data.trigger === "manual" ? "pedido manual" : "agendado"}</span>
            {data.ai_model && <span>· análise por {data.ai_model}</span>}
          </div>
          <p className="text-sm text-ink">{data.summary}</p>
          {data.candidate && (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Mudança {data.candidate.source === "ai" ? "(ideia da IA)" : ""}</h3>
              <ChangeList changes={data.candidate.changes} />
              {data.candidate.note && <p className="text-xs text-ink-2">Motivo da IA: {data.candidate.note}</p>}
            </section>
          )}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Resultado no histórico</h3>
            <Comparison run={data} />
            {period && (
              <p className="text-xs text-muted">
                Escolha: {dateTime(period.start)} a {dateTime(period.split)} · confirmação: {dateTime(period.split)} a {dateTime(period.end)}
                {period.sentiment_data ? " · com o índice de medo e ganância real de cada dia" : ""}.
              </p>
            )}
          </section>
          <section className="space-y-2">
            <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Diagnóstico do bot</h3>
            <Findings findings={data.diagnostics?.findings ?? data.findings} />
          </section>
          {data.ai_notes && (
            <section className="space-y-2">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted uppercase"><Sparkles className="size-3.5" />Análise da IA</h3>
              <div className="rounded-lg bg-surface-2 p-3"><MarkdownView text={data.ai_notes} /></div>
            </section>
          )}
          {data.tested && data.tested.length > 0 && (
            <section className="space-y-2">
              <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Variações testadas ({data.tested.length})</h3>
              <ul className="divide-y divide-line text-sm">
                {data.tested.slice(0, 20).map((t) => (
                  <li key={t.key} className="flex items-start gap-2 py-1.5">
                    {t.passed ? <Check className="mt-0.5 size-4 shrink-0 text-good-text" aria-label="aprovada" /> : <X className="mt-0.5 size-4 shrink-0 text-muted" aria-label="reprovada" />}
                    <div className="min-w-0 flex-1">
                      <div className="text-ink">{t.label}{t.source === "ai" && <Badge tone="accent" className="ml-1.5">IA</Badge>}</div>
                      <div className="text-xs text-muted">
                        {t.in ? `escolha ${pct(t.in.return_pct, true, 1)}` : ""}
                        {t.out ? ` · recente ${pct(t.out.return_pct, true, 1)}` : ""}
                        {t.reasons.length ? ` · ${t.reasons.join(", ")}` : ""}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.followup && (
            <p className="text-sm text-ink-2">
              Depois da mudança ({num(data.followup.days, 1)} dias): {data.followup.trades} operação(ões), resultado {signedMoney(data.followup.pnl_quote)}.
            </p>
          )}
          {data.error && <ErrorBox error={data.error} />}
        </div>
      )}
    </Modal>
  );
}

function AuthorizeModal({ open, botName, onConfirm, onClose, error, loading }: {
  open: boolean;
  botName: string;
  onConfirm: (password: string, code: string) => void;
  onClose: () => void;
  error: unknown;
  loading: boolean;
}) {
  const security = useQuery({ queryKey: ["security"], queryFn: () => api.get<SecurityStatus>("/security/status"), enabled: open });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  return (
    <Modal open={open} onClose={onClose} title="Autorizar mudanças automáticas em dinheiro real?">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(password, code);
        }}
      >
        <div className="space-y-2 text-sm text-ink-2">
          <p>
            Com isso, o piloto pode mudar parâmetros e regras de risco de <strong className="text-ink">{botName}</strong> mesmo com o bot operando dinheiro real, sem pedir sua
            aprovação a cada vez.
          </p>
          <p>Continua valendo: nunca muda par, tempo de candle, modo nem valor das ordens; troca de estratégia sempre espera você; no máximo uma mudança a cada 5 dias; você pode desfazer qualquer mudança.</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Sua senha">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" autoFocus />
          </Field>
          {security.data?.two_factor.enabled && (
            <Field label="Código de 2 etapas">
              <Input value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" className="font-mono" />
            </Field>
          )}
        </div>
        <ErrorBox error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" loading={loading}>Autorizar</Button>
        </div>
      </form>
    </Modal>
  );
}

function useAutopilotActions() {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["autopilot"] });
    qc.invalidateQueries({ queryKey: ["bot"] });
    qc.invalidateQueries({ queryKey: ["bots"] });
  };
  const run = useMutation({ mutationFn: (botId: number) => api.post(`/autopilot/bots/${botId}/run`), onSuccess: refresh });
  const act = useMutation({
    mutationFn: ({ runId, action }: { runId: number; action: "apply" | "reject" | "revert" }) => api.post(`/autopilot/runs/${runId}/${action}`),
    onSuccess: refresh,
  });
  return { run, act, refresh };
}

/** Sugestão pendente com os botões aplicar/recusar (usado aqui e na tela do bot). */
export function SuggestionBox({ run, onDetails }: { run: OptimizationRun; onDetails: () => void }) {
  const { act } = useAutopilotActions();
  return (
    <div className="space-y-2 rounded-lg border border-warn/40 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
        <Sparkles className="size-4 text-warn-text" /> Sugestão: {run.candidate?.label}
      </div>
      <p className="text-xs text-ink-2">{run.summary}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" onClick={() => act.mutate({ runId: run.id, action: "apply" })} loading={act.isPending && act.variables?.action === "apply"}>
          <Check className="size-3.5" />Aplicar
        </Button>
        <Button size="sm" onClick={() => act.mutate({ runId: run.id, action: "reject" })} loading={act.isPending && act.variables?.action === "reject"}>
          Recusar
        </Button>
        <Button size="sm" variant="ghost" onClick={onDetails}>Ver detalhes</Button>
      </div>
      <ErrorBox error={act.error} />
    </div>
  );
}

function BotAutopilotCard({ item, onDetails }: { item: AutopilotBot; onDetails: (runId: number) => void }) {
  const qc = useQueryClient();
  const { run, act } = useAutopilotActions();
  const cfg = item.autopilot;
  const [pending, setPending] = useState<Partial<AutopilotConfig> | null>(null);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put<AutopilotConfig>(`/autopilot/bots/${item.bot.id}`, body),
    onSuccess: () => {
      setPending(null);
      qc.invalidateQueries({ queryKey: ["autopilot"] });
    },
  });
  const update = (changes: Partial<AutopilotConfig>) => {
    const next = { mode: cfg.mode, interval_hours: cfg.interval_hours, allow_strategy_change: cfg.allow_strategy_change, ...changes };
    if (next.mode === "auto_all" && !cfg.live_authorized) {
      setPending(next); // pede senha antes
      return;
    }
    save.mutate(next);
  };
  const stopped = item.bot.status !== "running";
  const last = item.last_run;
  const applied = item.last_applied;
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          <Link to={`/bots/${item.bot.id}`} className="hover:underline">{item.bot.name}</Link>
          <ModeBadge mode={item.bot.mode} />
        </span>
      }
      action={item.running ? <RunStatusBadge status="running" /> : undefined}
    >
      <div className="space-y-4 text-sm">
        <p className="text-xs text-muted">{item.bot.symbol} · {INTERVAL_LABELS[item.bot.interval] ?? item.bot.interval} · {item.bot.strategy}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Piloto automático">
            <Select value={cfg.mode} onChange={(e) => update({ mode: e.target.value as AutopilotMode })} disabled={save.isPending}>
              {MODE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Frequência">
            <Select value={cfg.interval_hours} onChange={(e) => update({ interval_hours: Number(e.target.value) })} disabled={save.isPending || cfg.mode === "off"}>
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
              {!FREQUENCIES.some((f) => f.value === cfg.interval_hours) && <option value={cfg.interval_hours}>A cada {cfg.interval_hours} h</option>}
            </Select>
          </Field>
        </div>
        <Switch
          checked={cfg.allow_strategy_change}
          onChange={(v) => update({ allow_strategy_change: v })}
          disabled={save.isPending || cfg.mode === "off"}
          label={<span className="text-sm text-ink-2">Pode testar outras estratégias</span>}
        />
        {item.bot.mode === "live" && cfg.mode === "auto_all" && cfg.live_authorized && (
          <p className="text-xs text-warn-text">Autorizado a mudar este bot real sozinho (exceto troca de estratégia).</p>
        )}
        <ErrorBox error={save.error} />

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => run.mutate(item.bot.id)} loading={run.isPending} disabled={item.running}>
            <Play className="size-3.5" />Otimizar agora
          </Button>
          <span className="text-xs text-muted">
            {cfg.mode === "off"
              ? "Piloto desligado."
              : stopped
                ? "O ciclo automático só roda com o bot ligado."
                : cfg.next_run_at
                  ? `Próximo ciclo ${new Date(cfg.next_run_at) < new Date() ? "em instantes" : `em ${dateTime(cfg.next_run_at)}`}.`
                  : ""}
          </span>
        </div>
        <ErrorBox error={run.error} />

        {item.suggestion && <SuggestionBox run={item.suggestion} onDetails={() => onDetails(item.suggestion!.id)} />}

        {last && last.id !== item.suggestion?.id && (
          <div className="space-y-1 border-t border-line pt-3">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <RunStatusBadge status={last.status} />
              <span className="text-muted">{timeAgo(last.created_at)}</span>
              {last.status !== "running" && (
                <button className="text-accent hover:underline" onClick={() => onDetails(last.id)}>detalhes</button>
              )}
            </div>
            {last.summary && <p className="line-clamp-3 text-xs text-ink-2">{last.summary}</p>}
            {last.status !== "running" && last.findings.some((f) => f.level !== "info") && (
              <p className="text-xs text-warn-text">
                {last.findings.filter((f) => f.level !== "info").length} alerta(s) no diagnóstico: veja os detalhes.
              </p>
            )}
          </div>
        )}

        {applied && (
          <div className="flex flex-wrap items-start justify-between gap-2 border-t border-line pt-3">
            <div className="min-w-0 text-xs text-ink-2">
              <div>
                Última mudança: <span className="text-ink">{applied.candidate?.label}</span> ({timeAgo(applied.applied_at)})
              </div>
              {applied.followup && (
                <div className="text-muted">
                  Desde então: {applied.followup.trades} operação(ões), {signedMoney(applied.followup.pnl_quote)}
                </div>
              )}
            </div>
            <Button size="sm" variant="ghost" onClick={() => act.mutate({ runId: applied.id, action: "revert" })} loading={act.isPending}>
              <RotateCcw className="size-3.5" />Desfazer
            </Button>
          </div>
        )}
        <ErrorBox error={act.error} />
      </div>
      <AuthorizeModal
        open={pending != null}
        botName={item.bot.name}
        loading={save.isPending}
        error={save.error}
        onClose={() => {
          setPending(null);
          save.reset();
        }}
        onConfirm={(password, code) => save.mutate({ ...pending, password, code: code || null })}
      />
    </Card>
  );
}

function HowItWorks() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem("bt-autopilot-guide") !== "closed";
    } catch {
      return true;
    }
  });
  const toggle = () => {
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem("bt-autopilot-guide", next ? "open" : "closed");
    } catch {
      /* armazenamento bloqueado */
    }
  };
  const steps: [string, string][] = [
    ["Diagnóstico", "Lê as operações, stops, sinais ignorados e erros de cada bot e aponta os problemas."],
    ["Testa uma coisa por vez", "Parâmetros da estratégia, stop, trailing, alvos, filtro de sentimento, outras estratégias, a configuração anterior e as ideias da IA."],
    ["Escolhe e confirma", "Escolhe usando os 2/3 mais antigos do histórico e confirma no 1/3 mais recente, que a escolha não viu. Também não pode piorar em BTC e ETH."],
    ["Só muda com folga", "Precisa melhorar nas duas partes sem aumentar a queda máxima. No máximo uma mudança a cada 5 dias por bot."],
    ["Limites", "Nunca mexe no par, no tempo de candle, no modo (simulado/real) nem no valor das ordens. Nos bots reais só muda sozinho com sua autorização, e troca de estratégia sempre espera você."],
    ["Aprende", "Cada ciclo fica registrado, com o resultado real depois da mudança. A IA recebe esse histórico e as lições anteriores; você pode desfazer qualquer mudança."],
  ];
  return (
    <Card className="mb-4" padded={false}>
      <button className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-semibold text-ink" onClick={toggle} aria-expanded={open}>
        <span className="flex items-center gap-2"><BrainCircuit className="size-4 text-accent" />Como o piloto automático melhora os bots</span>
        <ChevronDown className={clsx("size-4 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="grid grid-cols-1 gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
          {steps.map(([title, text], i) => (
            <li key={title} className="rounded-lg bg-surface-2 p-3 text-xs text-ink-2">
              <div className="mb-1 font-medium text-ink">{i + 1}. {title}</div>
              {text}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

const INSIGHT_ICON = {
  lesson: <BrainCircuit className="mt-0.5 size-4 shrink-0 text-accent" aria-label="lição" />,
  warning: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-text" aria-label="alerta" />,
  observation: <CircleMinus className="mt-0.5 size-4 shrink-0 text-muted" aria-label="observação" />,
};

function InsightsCard() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["insights"], queryFn: () => api.get<Insight[]>("/autopilot/insights") });
  const forget = useMutation({ mutationFn: (id: number) => api.del(`/autopilot/insights/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["insights"] }) });
  return (
    <Card title="O que a IA aprendeu">
      {data?.length ? (
        <ul className="divide-y divide-line text-sm">
          {data.map((i) => (
            <li key={i.id} className="group flex items-start gap-2 py-2">
              {INSIGHT_ICON[i.kind] ?? INSIGHT_ICON.observation}
              <div className="min-w-0 flex-1">
                <div className="text-ink">{i.text}</div>
                <div className="text-xs text-muted">{[i.symbol, INTERVAL_LABELS[i.interval] ?? i.interval].filter(Boolean).join(" · ")} · {timeAgo(i.created_at)}</div>
              </div>
              <button className="opacity-60 group-hover:opacity-100" onClick={() => forget.mutate(i.id)} aria-label="Esquecer esta lição" title="Esquecer">
                <Trash2 className="size-3.5 text-muted hover:text-bad-text" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">As lições que a IA tirar de cada ciclo aparecem aqui e são usadas nos próximos. Precisa de uma chave de IA (Claude ou GPT).</p>
      )}
    </Card>
  );
}

export function AutopilotPage() {
  const [detail, setDetail] = useState<number | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["autopilot"],
    queryFn: () => api.get<AutopilotOverview>("/autopilot"),
    refetchInterval: (q) => (q.state.data?.bots.some((b) => b.running) ? 4000 : 30_000),
  });
  return (
    <>
      <PageHeader title="Análise com IA" subtitle="Piloto automático: diagnostica cada bot, testa melhorias no histórico e aplica só as que se confirmam." />
      <AITabs />
      <HowItWorks />
      {data && !data.ai_configured && (
        <div className="mb-4 flex gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink-2">
          <Sparkles className="mt-0.5 size-3.5 shrink-0 text-accent" />
          <span>
            Sem uma chave de IA (Claude ou GPT) o piloto funciona só com os testes. Com a chave (em <Link to="/settings" className="text-accent hover:underline">Configurações</Link>), a IA escreve a
            análise de cada ciclo, acumula lições e propõe ideias novas, que passam pelos mesmos testes.
          </span>
        </div>
      )}
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && data.bots.length === 0 && (
        <Card>
          <Empty icon={<BotIcon className="size-8" />} title="Nenhum bot ainda">Crie um bot e o piloto automático começa a acompanhá-lo.</Empty>
        </Card>
      )}
      {data && data.bots.length > 0 && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {data.bots.map((item) => (
            <BotAutopilotCard key={item.bot.id} item={item} onDetails={setDetail} />
          ))}
        </div>
      )}
      <div className="mt-4">
        <InsightsCard />
      </div>
      <RunDetail runId={detail} onClose={() => setDetail(null)} />
    </>
  );
}
