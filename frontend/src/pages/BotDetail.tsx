import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Play, RotateCcw, Sparkles, Square, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ChecksList, EventsList, ModeBadge, OpenPositionCard, OrdersTable, PositionsTable, StatusBadge } from "../components/bot";
import { CandleChart } from "../components/charts";
import { useStrategies } from "../components/forms";
import { Button, Card, Confirm, ErrorBox, Loading, PageHeader, Pnl, Stat, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { duration, INTERVAL_LABELS, money, num, pct, timeAgo } from "../lib/format";
import type { Bot, BotChart, BotEvent, OrderRow, Position } from "../lib/types";

type Tab = "trades" | "orders" | "events";
type Action = "start" | "stop" | "close" | "delete" | "reset" | null;

function ConfigSummary({ bot }: { bot: Bot }) {
  const strategies = useStrategies();
  const info = strategies.data?.strategies.find((s) => s.key === bot.strategy);
  const r = bot.risk;
  const sizing =
    r.sizing_mode === "fixed_quote" ? `${num(r.order_size_quote)} ${bot.quote_asset} por compra` : r.sizing_mode === "percent_balance" ? `${r.balance_percent}% do saldo` : `${r.risk_percent}% de risco até o stop`;
  const stop = r.stop_loss_mode === "atr" ? `${num(r.stop_loss_atr_mult)}× ATR` : r.stop_loss_mode === "percent" ? `${num(r.stop_loss_pct)}%` : "sem stop";
  return (
    <dl className="text-sm">
      <Row k="Estratégia" v={bot.strategy_name} />
      <Row k="Candle" v={INTERVAL_LABELS[bot.interval] ?? bot.interval} />
      <Row k="Tamanho" v={sizing} />
      <Row k="Stop loss" v={stop} />
      <Row k="Trailing" v={r.trailing_enabled ? `${r.trailing_mode === "atr" ? `${num(r.trailing_atr_mult)}× ATR` : `${num(r.trailing_pct)}%`} após +${num(r.trailing_activation_pct)}%` : "desligado"} />
      <Row k="Alvos" v={r.take_profits.length ? r.take_profits.map((t) => `+${num(t.pct)}% (vende ${num(t.size_pct)}%)`).join(", ") : "nenhum (sai pelo sinal)"} />
      <Row k="Break-even" v={r.breakeven_at_pct ? `após +${num(r.breakeven_at_pct)}%` : "desligado"} />
      <Row k="Perda diária máx." v={r.max_daily_loss_quote ? `${num(r.max_daily_loss_quote)} ${bot.quote_asset}` : "sem limite"} />
      {info?.params.map((p) => (
        <Row key={p.name} k={p.label} v={String(typeof bot.strategy_params[p.name] === "boolean" ? (bot.strategy_params[p.name] ? "sim" : "não") : bot.strategy_params[p.name] ?? p.default)} />
      ))}
    </dl>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-1.5">
      <dt className="text-ink-2">{k}</dt>
      <dd className="text-right text-ink">{v}</dd>
    </div>
  );
}

export function BotDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("trades");
  const [action, setAction] = useState<Action>(null);

  const bot = useQuery({ queryKey: ["bot", id], queryFn: () => api.get<Bot>(`/bots/${id}`), refetchInterval: 10_000 });
  const chart = useQuery({ queryKey: ["bot", id, "chart"], queryFn: () => api.get<BotChart>(`/bots/${id}/chart?limit=300`), refetchInterval: 60_000 });
  const positions = useQuery({ queryKey: ["bot", id, "positions"], queryFn: () => api.get<Position[]>(`/bots/${id}/positions`), refetchInterval: 15_000 });
  const orders = useQuery({ queryKey: ["bot", id, "orders"], queryFn: () => api.get<OrderRow[]>(`/bots/${id}/orders`), enabled: tab === "orders" });
  const events = useQuery({ queryKey: ["bot", id, "events"], queryFn: () => api.get<BotEvent[]>(`/bots/${id}/events?limit=150`), refetchInterval: 15_000 });

  const mutate = useMutation({
    mutationFn: (a: Exclude<Action, null>) => {
      if (a === "delete") return api.del(`/bots/${id}`);
      const path = { start: "start", stop: "stop", close: "close-position", reset: "reset-paper" }[a];
      return api.post(`/bots/${id}/${path}`);
    },
    onSuccess: (_, a) => {
      setAction(null);
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["system"] });
      if (a === "delete") navigate("/bots");
      else qc.invalidateQueries({ queryKey: ["bot", id] });
    },
  });

  if (bot.isLoading) return <Loading />;
  if (!bot.data) return <ErrorBox error={bot.error ?? "Bot não encontrado"} />;
  const b = bot.data;
  const running = b.status === "running";
  const q = b.quote_asset;

  const confirmations: Record<Exclude<Action, null>, { title: string; message: string; label: string; danger?: boolean }> = {
    start: {
      title: b.mode === "live" ? "Ligar bot em modo REAL?" : "Ligar bot?",
      message: b.mode === "live" ? "O bot vai enviar ordens reais à Binance com o seu dinheiro, conforme a estratégia e o risco configurados." : "O bot vai operar com saldo simulado e preços reais.",
      label: "Ligar",
    },
    stop: { title: "Parar bot?", message: b.position ? "A posição aberta continua aberta e deixa de ser monitorada (sem stop automático) até você ligar o bot de novo." : "O bot deixa de avaliar o mercado.", label: "Parar", danger: true },
    close: { title: "Encerrar posição agora?", message: `Vende toda a posição a mercado${b.mode === "live" ? " na Binance" : ""}.`, label: "Vender agora", danger: true },
    delete: { title: "Excluir bot?", message: "O histórico de operações deste bot também será apagado.", label: "Excluir", danger: true },
    reset: { title: "Resetar simulação?", message: "Apaga operações, ordens e eventos deste bot e volta o saldo simulado ao valor inicial.", label: "Resetar", danger: true },
  };

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {b.name} <ModeBadge mode={b.mode} /> <StatusBadge bot={b} />
          </span>
        }
        subtitle={`${b.symbol} · ${INTERVAL_LABELS[b.interval] ?? b.interval} · ${b.strategy_name}${b.last_tick_at ? ` · última checagem ${timeAgo(b.last_tick_at)}` : ""}`}
        actions={
          <>
            {running ? (
              <Button onClick={() => setAction("stop")}><Square className="size-4" />Parar</Button>
            ) : (
              <Button variant="primary" onClick={() => setAction("start")}><Play className="size-4" />Ligar</Button>
            )}
            {b.position && <Button variant="danger" onClick={() => setAction("close")}><XCircle className="size-4" />Encerrar posição</Button>}
            <Button onClick={() => navigate("/ai", { state: { botId: b.id, prompt: `Analise o desempenho do bot "${b.name}" e sugira melhorias concretas, validando com backtest.` } })}>
              <Sparkles className="size-4" />Analisar com IA
            </Button>
            <Button variant="ghost" onClick={() => navigate(`/bots/${b.id}/edit`)} aria-label="Editar"><Pencil className="size-4" /></Button>
            {b.mode === "paper" && !running && (
              <Button variant="ghost" onClick={() => setAction("reset")} aria-label="Resetar simulação"><RotateCcw className="size-4" /></Button>
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
        <Stat label="Resultado total" value={<Pnl value={b.stats.total_pnl} quote={q} />} sub={`Hoje ${b.stats.today_pnl >= 0 ? "+" : ""}${num(b.stats.today_pnl)}`} />
        <Stat label="Realizado" value={<Pnl value={b.stats.realized_pnl} quote={q} />} />
        <Stat label="Em aberto" value={<Pnl value={b.stats.unrealized_pnl} quote={q} />} />
        <Stat label="Operações" value={b.stats.trades} sub={`acerto ${pct(b.stats.win_rate, false, 0)}`} />
        <Stat label="Tempo de operação" value={duration(b.runtime_seconds)} sub={b.started_at ? `ligado há ${duration((Date.now() - new Date(b.started_at).getTime()) / 1000)}` : "parado"} />
        {b.mode === "paper" ? (
          <Stat label="Saldo simulado" value={money(b.paper_balance, q)} sub={`inicial ${num(b.paper_initial_balance)}`} />
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
        <Card title="Condições da estratégia" action={<span className="text-xs text-muted">último candle fechado</span>}>
          <ChecksList snapshot={chart.data?.preview ?? b.last_signal} quote={q} />
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
                { value: "orders", label: "Ordens" },
                { value: "events", label: "Eventos" },
              ]}
            />
          </div>
          <div className="max-h-[520px] overflow-y-auto p-4">
            {tab === "trades" && <PositionsTable positions={positions.data ?? []} quote={q} />}
            {tab === "orders" && <OrdersTable orders={orders.data ?? []} quote={q} />}
            {tab === "events" && <EventsList events={events.data ?? []} />}
          </div>
        </Card>
        <Card title="Configuração">
          <ConfigSummary bot={b} />
        </Card>
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
    </>
  );
}
