import clsx from "clsx";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, Check, ExternalLink, Info, Radio, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { dateTime, duration, NEWS_GUARD_LABELS, num, pct, price, qty, REASONS, SENTIMENT_FILTER_LABELS, timeAgo } from "../lib/format";
import type { Bot, BotEvent, MarketFilters, Position, Snapshot } from "../lib/types";
import { Badge, Dot, Empty, Pnl } from "./ui";

export function ModeBadge({ mode }: { mode: Bot["mode"] }) {
  return mode === "live" ? <Badge tone="warn">Real</Badge> : <Badge tone="accent">Simulado</Badge>;
}

const LEVEL_OF_INTERVAL: Record<string, "baixa" | "media" | "alta"> = {
  "1m": "alta", "3m": "alta", "5m": "alta", "15m": "alta",
  "30m": "media", "1h": "media", "2h": "media",
  "4h": "baixa", "6h": "baixa", "12h": "baixa", "1d": "baixa",
};

/** Volatilidade do robô, pelo tempo de candle (baixa = operações de dias; alta = de minutos). */
export function VolatilityBadge({ interval }: { interval: string }) {
  const level = LEVEL_OF_INTERVAL[interval] ?? "baixa";
  const tone = level === "baixa" ? "good" : level === "media" ? "warn" : "bad";
  return <Badge tone={tone}>Volatilidade {level === "media" ? "média" : level}</Badge>;
}

export function StatusBadge({ bot }: { bot: Pick<Bot, "status" | "running" | "status_reason"> }) {
  if (bot.status === "error") return <Badge tone="bad"><Dot tone="bad" />Erro</Badge>;
  if (bot.status === "running" && bot.running) return <Badge tone="good"><Dot tone="good" />Operando</Badge>;
  if (bot.status === "running") return <Badge tone="warn"><Dot tone="warn" />Aguardando sistema</Badge>;
  return <Badge><Dot tone="neutral" />Parado</Badge>;
}

/** Sentimento do mercado e trava de notícias na última avaliação do bot. */
export function MarketFiltersView({ market }: { market: MarketFilters }) {
  const s = market.sentiment;
  const week = s && s.change_7d != null ? `, ${s.change_7d > 0 ? "+" : ""}${s.change_7d} na semana` : "";
  return (
    <div className="space-y-1.5 border-t border-line pt-3 text-xs">
      <div className="flex items-center gap-1.5 font-medium text-ink-2">
        {market.blocks_entry ? <ShieldAlert className="size-3.5 text-warn-text" /> : <ShieldCheck className="size-3.5 text-good-text" />}
        Filtros de mercado: {market.blocks_entry ? <span className="text-warn-text">compras travadas</span> : <span className="text-good-text">liberado</span>}
      </div>
      {market.blocks_entry && market.reason && <p className="text-warn-text">{market.reason}</p>}
      <p className="text-ink-2">
        Medo e ganância: {s ? <span className="text-ink">{s.value} ({s.label}){week}</span> : "sem dado"} · filtro{" "}
        {SENTIMENT_FILTER_LABELS[market.sentiment_filter] ?? market.sentiment_filter}
      </p>
      <p className="text-ink-2">Notícias: trava {NEWS_GUARD_LABELS[market.news_guard] ?? market.news_guard}</p>
      {market.news_block && (
        <a href={market.news_block.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 text-warn-text hover:underline">
          {market.news_block.title} ({market.news_block.source}) <ExternalLink className="mt-0.5 size-3 shrink-0" />
        </a>
      )}
    </div>
  );
}

export function ChecksList({ snapshot, quote, market }: { snapshot: Snapshot | null | undefined; quote?: string; market?: MarketFilters | null }) {
  if (!snapshot) return <Empty title="Sem avaliação ainda">As condições aparecem após o primeiro candle fechado.</Empty>;
  const filters = market ?? snapshot.market;
  const required = snapshot.entry_checks.filter((c) => !c.label.startsWith("· "));
  const info = snapshot.entry_checks.filter((c) => c.label.startsWith("· "));
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {snapshot.entry ? <Badge tone="good">Sinal de compra</Badge> : snapshot.exit ? <Badge tone="bad">Sinal de venda</Badge> : <Badge>Sem sinal</Badge>}
        {snapshot.candle_time && <span className="text-xs text-muted">candle de {dateTime(snapshot.candle_time)}</span>}
        {snapshot.close != null && <span className="text-xs text-muted">fechou em {price(snapshot.close)} {quote}</span>}
      </div>
      <div>
        <div className="mb-1.5 text-xs font-medium text-ink-2">Para comprar (todas)</div>
        <CheckRows checks={required} />
        {info.length > 0 && (
          <div className="mt-2 border-l border-line pl-3">
            <CheckRows checks={info.map((c) => ({ ...c, label: c.label.slice(2) }))} muted />
          </div>
        )}
      </div>
      <div>
        <div className="mb-1.5 text-xs font-medium text-ink-2">Para vender (qualquer uma)</div>
        <CheckRows checks={snapshot.exit_checks} />
      </div>
      {Object.keys(snapshot.values).length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-xs">
          {Object.entries(snapshot.values).map(([k, v]) => (
            <span key={k} className="text-ink-2">
              {k} <span className="font-medium text-ink tabular">{num(v, 2)}</span>
            </span>
          ))}
        </div>
      )}
      {filters && <MarketFiltersView market={filters} />}
    </div>
  );
}

function CheckRows({ checks, muted }: { checks: { label: string; ok: boolean }[]; muted?: boolean }) {
  return (
    <ul className="space-y-1">
      {checks.map((c) => (
        <li key={c.label} className={clsx("flex items-start gap-2", muted && "text-xs")}>
          {c.ok ? <Check className="mt-0.5 size-4 shrink-0 text-good-text" aria-label="atendida" /> : <X className="mt-0.5 size-4 shrink-0 text-muted" aria-label="não atendida" />}
          <span className={c.ok ? "text-ink" : "text-ink-2"}>{c.label}</span>
        </li>
      ))}
    </ul>
  );
}

const EVENT_ICON = {
  trade: <ArrowUpRight className="size-3.5 text-accent" />,
  signal: <Radio className="size-3.5 text-muted" />,
  info: <Info className="size-3.5 text-muted" />,
  warn: <AlertTriangle className="size-3.5 text-warn-text" />,
  error: <AlertTriangle className="size-3.5 text-bad-text" />,
};

export function EventsList({ events, showBot }: { events: BotEvent[]; showBot?: boolean }) {
  if (!events.length) return <Empty title="Nenhum evento ainda" />;
  return (
    <ul className="divide-y divide-line">
      {events.map((e) => (
        <li key={e.id} className="flex items-start gap-2.5 py-2 text-sm">
          <span className="mt-0.5" aria-label={e.level}>{EVENT_ICON[e.level] ?? EVENT_ICON.info}</span>
          <div className="min-w-0 flex-1">
            <div className={clsx(e.level === "error" ? "text-bad-text" : e.level === "trade" ? "text-ink" : "text-ink-2", "break-words")}>
              {showBot && e.bot_name && <span className="mr-1.5 font-medium text-ink">{e.bot_name}:</span>}
              {e.message}
            </div>
          </div>
          <span className="shrink-0 text-xs text-muted" title={dateTime(e.created_at)}>{timeAgo(e.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function PositionsTable({ positions, quote, showBot, compact }: { positions: Position[]; quote?: string; showBot?: boolean; compact?: boolean }) {
  if (!positions.length) return <Empty title="Nenhuma operação ainda" />;
  return (
    <>
    {/* celular: lista compacta */}
    <ul className="divide-y divide-line md:hidden">
      {positions.map((p) => {
        const open = p.status === "open";
        return (
          <li key={p.id} className="flex items-start justify-between gap-3 py-2.5 text-sm">
            <div className="min-w-0">
              <div className="truncate text-ink">{showBot ? p.bot_name : dateTime(p.entry_time)}</div>
              <div className="text-xs text-muted tabular">
                {price(p.entry_price)} → {open ? "aberta" : price(p.exit_price)}
                {!open && ` · ${REASONS[p.exit_reason] ?? p.exit_reason}`} · {duration(p.duration_seconds)}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <Pnl value={open ? p.unrealized_pnl : p.pnl_quote} quote={quote} className="font-medium" />
              <div className="text-xs text-muted">{pct(open ? p.unrealized_pct : p.pnl_pct, true)}</div>
            </div>
          </li>
        );
      })}
    </ul>
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-sm tabular">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            {showBot && <th className="py-2 pr-3 font-medium">Bot</th>}
            <th className="py-2 pr-3 font-medium">{compact ? "Quando" : "Entrada"}</th>
            <th className="py-2 pr-3 text-right font-medium">Preço entrada</th>
            <th className="py-2 pr-3 text-right font-medium">Preço saída</th>
            {!compact && <th className="py-2 pr-3 text-right font-medium">Valor</th>}
            <th className="py-2 pr-3 font-medium">Motivo</th>
            {!compact && <th className="py-2 pr-3 text-right font-medium">Duração</th>}
            <th className="py-2 text-right font-medium">Resultado</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {positions.map((p) => {
            const open = p.status === "open";
            const result = open ? p.unrealized_pnl : p.pnl_quote;
            const resultPct = open ? p.unrealized_pct : p.pnl_pct;
            return (
              <tr key={p.id}>
                {showBot && <td className="py-2 pr-3 text-ink-2">{p.bot_name}</td>}
                <td className="py-2 pr-3 whitespace-nowrap text-ink-2">{compact ? timeAgo(p.exit_time ?? p.entry_time) : dateTime(p.entry_time)}</td>
                <td className="py-2 pr-3 text-right">{price(p.entry_price)}</td>
                <td className="py-2 pr-3 text-right">{open ? <span className="text-muted">aberta</span> : price(p.exit_price)}</td>
                {!compact && <td className="py-2 pr-3 text-right text-ink-2">{num(p.cost_quote)}</td>}
                <td className="py-2 pr-3 whitespace-nowrap text-ink-2">{open ? "–" : REASONS[p.exit_reason] ?? p.exit_reason}</td>
                {!compact && <td className="py-2 pr-3 text-right text-ink-2">{duration(p.duration_seconds)}</td>}
                <td className="py-2 text-right whitespace-nowrap">
                  <Pnl value={result} quote={compact ? "" : quote} />{" "}
                  {!compact && <span className="text-xs text-muted">({pct(resultPct, true)})</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}

export function OpenPositionCard({ position, quote, base }: { position: Position; quote: string; base: string }) {
  const kind = position.stop_kind === "trailing_stop" ? "Trailing stop" : position.stop_kind === "breakeven" ? "Break-even" : "Stop loss";
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
      <Item label="Resultado agora" value={<><Pnl value={position.unrealized_pnl} quote={quote} /> <span className="text-xs text-muted">({pct(position.unrealized_pct, true)})</span></>} />
      <Item label="Preço de entrada" value={price(position.entry_price)} />
      <Item label="Preço atual" value={price(position.current_price)} />
      <Item label="Quantidade" value={`${qty(position.qty)} ${base}`} />
      <Item label="Investido" value={`${num(position.cost_quote)} ${quote}`} />
      <Item label={kind} value={position.stop_price ? price(position.stop_price) : "sem stop"} />
      <Item label="Máxima desde a compra" value={price(position.highest_price)} />
      <Item label="Aberta há" value={duration(position.duration_seconds)} />
      <Item label="Já vendido (parciais)" value={`${num(position.proceeds_quote)} ${quote}`} />
    </div>
  );
}

function Item({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-0.5 font-medium text-ink tabular">{value}</div>
    </div>
  );
}
