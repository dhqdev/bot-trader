import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, Pencil, Play, RotateCcw, Square, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { AutopilotCard } from "../components/autopilot";
import { ChecksList, EventsList, ModeBadge, OpenPositionCard, PositionsTable, StatusBadge, VolatilityBadge } from "../components/bot";
import { CandleChart } from "../components/charts";
import { Button, Card, Confirm, ErrorBox, Field, Input, Loading, Modal, PageHeader, Pnl, Segmented, Stat, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { duration, INTERVAL_LABELS, money, NEWS_GUARD_LABELS, num, pct, SENTIMENT_FILTER_LABELS, timeAgo } from "../lib/format";
import type { Bot, BotChart, BotEvent, Credentials, Mode, Position, StrategiesResponse } from "../lib/types";

type Tab = "trades" | "events";
type Action = "start" | "stop" | "close" | "delete" | "reset" | null;

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-1.5">
      <dt className="text-ink-2">{k}</dt>
      <dd className="text-right text-ink">{v}</dd>
    </div>
  );
}

/** As regras do robô, para quem quiser conferir (fechado por padrão). */
function TechnicalDetails({ bot }: { bot: Bot }) {
  const [open, setOpen] = useState(false);
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: () => api.get<StrategiesResponse>("/strategies"), staleTime: Infinity, enabled: open });
  const info = strategies.data?.strategies.find((s) => s.key === bot.strategy);
  const r = bot.risk;
  const stop = r.stop_loss_mode === "atr" ? `${num(r.stop_loss_atr_mult)}× ATR` : r.stop_loss_mode === "percent" ? `${num(r.stop_loss_pct)}%` : "sem stop";
  const trailing = r.trailing_mode === "atr" ? `${num(r.trailing_atr_mult)}× ATR` : `${num(r.trailing_pct)}%`;
  return (
    <Card padded={false}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-ink">
        Detalhes técnicos
        <ChevronDown className={clsx("size-4 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <dl className="px-4 pb-4 text-sm">
          <Row k="Estratégia" v={bot.strategy_name} />
          <Row k="Candle" v={INTERVAL_LABELS[bot.interval] ?? bot.interval} />
          <Row k="Stop loss" v={stop} />
          <Row k="Trailing" v={r.trailing_enabled ? `${trailing} após +${num(r.trailing_activation_pct)}%` : "desligado"} />
          <Row k="Alvos" v={r.take_profits.length ? r.take_profits.map((t) => `+${num(t.pct)}% (vende ${num(t.size_pct)}%)`).join(", ") : "sai pelo sinal"} />
          <Row k="Sentimento" v={SENTIMENT_FILTER_LABELS[r.sentiment_filter] ?? r.sentiment_filter} />
          <Row k="Notícias" v={r.news_guard === "off" ? "desligada" : NEWS_GUARD_LABELS[r.news_guard]} />
          {info?.params.map((p) => (
            <Row key={p.name} k={p.label} v={String(typeof bot.strategy_params[p.name] === "boolean" ? (bot.strategy_params[p.name] ? "sim" : "não") : bot.strategy_params[p.name] ?? p.default)} />
          ))}
        </dl>
      )}
    </Card>
  );
}

function EditModal({ bot, onClose }: { bot: Bot; onClose: () => void }) {
  const qc = useQueryClient();
  const creds = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  const [name, setName] = useState(bot.name);
  const [amount, setAmount] = useState(bot.risk.order_size_quote);
  const [mode, setMode] = useState<Mode>(bot.mode);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { name, risk: { ...bot.risk, sizing_mode: "fixed_quote", order_size_quote: amount } };
      if (mode !== bot.mode) body.mode = mode;
      return api.put<Bot>(`/bots/${bot.id}`, body);
    },
    onSuccess: () => {
      for (const k of ["bots", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
      qc.invalidateQueries({ queryKey: ["bot", String(bot.id)] });
      onClose();
    },
  });
  const noKeys = mode === "live" && creds.data != null && !creds.data.okx.configured;
  return (
    <Modal open onClose={onClose} title="Editar robô">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Nome">
          <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
        </Field>
        <Field label={`Valor por operação (${bot.quote_asset})`} help="Vale a partir da próxima compra.">
          <Input type="number" min={5} step="any" value={amount} onChange={(e) => setAmount(Number(e.target.value))} required />
        </Field>
        <div className="space-y-2">
          <Segmented<Mode>
            value={mode}
            onChange={setMode}
            options={[
              { value: "paper", label: "Simulado" },
              { value: "live", label: "Dinheiro real" },
            ]}
          />
          {mode !== bot.mode && <p className="text-xs text-ink-2">Para trocar o modo, o robô precisa estar desligado e sem posição aberta.</p>}
          {noKeys && <p className="text-xs text-warn-text">Cadastre a chave da OKX em Configurações para usar dinheiro real.</p>}
        </div>
        <ErrorBox error={save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" loading={save.isPending} disabled={noKeys || !(amount >= 5)}>Salvar</Button>
        </div>
      </form>
    </Modal>
  );
}

export function BotDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("trades");
  const [action, setAction] = useState<Action>(null);
  const [editing, setEditing] = useState(false);

  const bot = useQuery({ queryKey: ["bot", id], queryFn: () => api.get<Bot>(`/bots/${id}`), refetchInterval: 10_000 });
  const chart = useQuery({ queryKey: ["bot", id, "chart"], queryFn: () => api.get<BotChart>(`/bots/${id}/chart?limit=300`), refetchInterval: 60_000 });
  const positions = useQuery({ queryKey: ["bot", id, "positions"], queryFn: () => api.get<Position[]>(`/bots/${id}/positions`), refetchInterval: 15_000 });
  const events = useQuery({ queryKey: ["bot", id, "events"], queryFn: () => api.get<BotEvent[]>(`/bots/${id}/events?limit=150`), refetchInterval: 15_000, enabled: tab === "events" });

  const mutate = useMutation({
    mutationFn: (a: Exclude<Action, null>) => {
      if (a === "delete") return api.del(`/bots/${id}`);
      const path = { start: "start", stop: "stop", close: "close-position", reset: "reset-paper" }[a];
      return api.post(`/bots/${id}/${path}`);
    },
    onSuccess: (_, a) => {
      setAction(null);
      for (const k of ["bots", "dashboard", "system"]) qc.invalidateQueries({ queryKey: [k] });
      if (a === "delete") navigate("/bots");
      else qc.invalidateQueries({ queryKey: ["bot", id] });
    },
  });

  if (bot.isLoading) return <Loading />;
  if (!bot.data) return <ErrorBox error={bot.error ?? "Robô não encontrado"} />;
  const b = bot.data;
  const running = b.status === "running";
  const q = b.quote_asset;

  const confirmations: Record<Exclude<Action, null>, { title: string; message: string; label: string; danger?: boolean }> = {
    start: {
      title: b.mode === "live" ? "Ligar com dinheiro real?" : "Ligar o robô?",
      message: b.mode === "live" ? `O robô vai enviar ordens reais à OKX: cada compra usa ${money(b.risk.order_size_quote, q)}.` : "O robô vai operar com saldo simulado e preços reais.",
      label: "Ligar",
    },
    stop: {
      title: "Desligar o robô?",
      message: b.position ? "A posição aberta continua aberta e deixa de ser acompanhada (sem stop automático) até você ligar de novo." : "O robô deixa de comprar e vender.",
      label: "Desligar",
      danger: true,
    },
    close: { title: "Vender agora?", message: `Vende toda a posição a mercado${b.mode === "live" ? " na OKX" : ""}.`, label: "Vender agora", danger: true },
    delete: { title: "Excluir robô?", message: "O histórico de operações deste robô também será apagado.", label: "Excluir", danger: true },
    reset: { title: "Recomeçar a simulação?", message: "Apaga as operações deste robô e volta o saldo simulado ao valor inicial.", label: "Recomeçar", danger: true },
  };

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {b.name} <ModeBadge mode={b.mode} /> <VolatilityBadge interval={b.interval} /> <StatusBadge bot={b} />
          </span>
        }
        subtitle={`${b.symbol} · ${b.strategy_name}${b.last_tick_at ? ` · checado ${timeAgo(b.last_tick_at)}` : ""}`}
        actions={
          <>
            {running ? (
              <Button onClick={() => setAction("stop")}><Square className="size-4" />Desligar</Button>
            ) : (
              <Button variant="primary" onClick={() => setAction("start")}><Play className="size-4" />Ligar</Button>
            )}
            {b.position && <Button variant="danger" onClick={() => setAction("close")}><XCircle className="size-4" />Vender agora</Button>}
            <Button variant="ghost" onClick={() => setEditing(true)} aria-label="Editar"><Pencil className="size-4" /></Button>
            {b.mode === "paper" && !running && (
              <Button variant="ghost" onClick={() => setAction("reset")} aria-label="Recomeçar simulação"><RotateCcw className="size-4" /></Button>
            )}
            {!running && <Button variant="ghost" onClick={() => setAction("delete")} aria-label="Excluir"><Trash2 className="size-4" /></Button>}
          </>
        }
      />

      {(b.status === "error" || b.last_error) && (
        <div className="mb-4 rounded-lg border border-bad/40 px-3 py-2 text-sm text-bad-text">
          {b.status_reason || b.last_error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Resultado" value={<Pnl value={b.stats.total_pnl} quote={q} />} sub={`hoje ${b.stats.today_pnl >= 0 ? "+" : ""}${num(b.stats.today_pnl)}`} />
        <Stat label="Por operação" value={money(b.risk.order_size_quote, q)} />
        <Stat label="Em aberto" value={<Pnl value={b.stats.unrealized_pnl} quote={q} />} />
        <Stat label="Operações" value={b.stats.trades} sub={`acerto ${pct(b.stats.win_rate, false, 0)}`} />
        <Stat label="Tempo ligado" value={duration(b.runtime_seconds)} sub={running ? "ligado agora" : "desligado"} />
        {b.mode === "paper" ? (
          <Stat label="Saldo simulado" value={money(b.paper_balance, q)} sub={`começou com ${num(b.paper_initial_balance)}`} />
        ) : (
          <Stat label="Preço atual" value={num(b.current_price, 6)} sub={q} />
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Gráfico" className="xl:col-span-2">
          {chart.data ? (
            <CandleChart candles={chart.data.candles} overlays={chart.data.overlays} markers={chart.data.markers} lines={chart.data.lines} />
          ) : chart.isError ? (
            <ErrorBox error={chart.error} />
          ) : (
            <Loading />
          )}
        </Card>
        <Card title="O que o robô está esperando" action={<span className="text-xs text-muted">último candle</span>}>
          <ChecksList snapshot={chart.data?.preview ?? b.last_signal} quote={q} market={b.last_signal?.market} />
        </Card>
      </div>

      {b.position && (
        <Card title="Posição aberta" className="mt-4">
          <OpenPositionCard position={b.position} quote={q} base={b.base_asset} />
        </Card>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" padded={false}>
          <div className="px-4 pt-2">
            <Tabs<Tab>
              value={tab}
              onChange={setTab}
              tabs={[
                { value: "trades", label: "Operações" },
                { value: "events", label: "Atividade" },
              ]}
            />
          </div>
          <div className="max-h-[520px] overflow-y-auto p-4">
            {tab === "trades" && <PositionsTable positions={positions.data ?? []} quote={q} />}
            {tab === "events" && <EventsList events={events.data ?? []} />}
          </div>
        </Card>
        <div className="space-y-4">
          <AutopilotCard botId={b.id} live={b.mode === "live"} />
          <TechnicalDetails bot={b} />
        </div>
      </div>

      {action && (
        <Confirm
          open
          title={confirmations[action].title}
          message={<>{confirmations[action].message}{mutate.error && <div className="mt-3"><ErrorBox error={mutate.error} /></div>}</>}
          confirmLabel={confirmations[action].label}
          danger={confirmations[action].danger}
          loading={mutate.isPending}
          onConfirm={() => mutate.mutate(action)}
          onClose={() => {
            setAction(null);
            mutate.reset();
          }}
        />
      )}
      {editing && <EditModal bot={b} onClose={() => setEditing(false)} />}
    </>
  );
}
