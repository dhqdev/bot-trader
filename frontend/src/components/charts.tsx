import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type IChartApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { dateTime, num, price, shortDate, signedMoney } from "../lib/format";
import type { Candle, ChartMarker, LinePoint } from "../lib/types";

// ------------------------------------------------------------------ tokens

const TOKEN_NAMES = ["surface", "ink", "ink-2", "muted", "grid", "axis", "accent", "good", "bad", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"] as const;
type Tokens = Record<(typeof TOKEN_NAMES)[number], string>;

function readTokens(): Tokens {
  const css = getComputedStyle(document.documentElement);
  return Object.fromEntries(TOKEN_NAMES.map((n) => [n, css.getPropertyValue(`--${n}`).trim()])) as Tokens;
}

/** Cores do tema atual, atualizadas quando o tema muda. */
export function useTokens(): Tokens {
  const [tokens, setTokens] = useState(readTokens);
  useEffect(() => {
    const obs = new MutationObserver(() => setTokens(readTokens()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return tokens;
}

export const seriesColor = (t: Tokens, i: number) => t[`s${(i % 8) + 1}` as keyof Tokens];

// ------------------------------------------------------------------ tooltip

function TipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          {r.color && <span className="inline-block h-0.5 w-3 rounded" style={{ background: r.color }} />}
          <span className="text-ink-2">{r.label}</span>
          <span className="ml-auto pl-3 font-medium text-ink tabular">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

const axisTick = (t: Tokens) => ({ fill: t.muted, fontSize: 11 });

// ------------------------------------------------------------------ curva de resultado

export function EquityChart({ data, quote = "USDT", height = 240 }: { data: { time: string; pnl: number }[]; quote?: string; height?: number }) {
  const t = useTokens();
  const rows = useMemo(() => data.map((d) => ({ ts: new Date(d.time).getTime(), pnl: d.pnl })), [data]);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={shortDate} tick={axisTick(t)} stroke={t.axis} tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={(v) => num(v)} tick={axisTick(t)} stroke={t.axis} tickLine={false} axisLine={false} width={56} />
        <ReferenceLine y={0} stroke={t.axis} />
        <Tooltip
          cursor={{ stroke: t.muted, strokeWidth: 1 }}
          content={({ active, payload }: TooltipContentProps<ValueType, NameType>) =>
            active && payload?.length ? (
              <TipBox title={dateTime(payload[0].payload.ts)} rows={[{ label: "Resultado acumulado", value: signedMoney(Number(payload[0].value), quote) }]} />
            ) : null
          }
        />
        <Area type="monotone" dataKey="pnl" stroke={t.accent} strokeWidth={2} fill={t.accent} fillOpacity={0.1} dot={false} activeDot={{ r: 4, stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------------ resultado por dia

type BarShapeProps = { x?: number; y?: number; width?: number; height?: number; fill?: string; payload?: { pnl: number } };

/** Barra com a ponta de dado arredondada (4px) e a base reta, para valores positivos e negativos. */
function RoundedBar({ x = 0, y = 0, width = 0, height = 0, fill, payload }: BarShapeProps) {
  if (!height) return null;
  const top = Math.min(y, y + height);
  const h = Math.abs(height);
  const r = Math.min(4, h, width / 2);
  const up = (payload?.pnl ?? 0) >= 0; // positivo: ponta em cima; negativo: ponta embaixo
  const path = up
    ? `M${x},${top + h} L${x},${top + r} Q${x},${top} ${x + r},${top} L${x + width - r},${top} Q${x + width},${top} ${x + width},${top + r} L${x + width},${top + h} Z`
    : `M${x},${top} L${x + width},${top} L${x + width},${top + h - r} Q${x + width},${top + h} ${x + width - r},${top + h} L${x + r},${top + h} Q${x},${top + h} ${x},${top + h - r} Z`;
  return <path d={path} fill={fill} />;
}

export function DailyPnlChart({ data, quote = "USDT", height = 200 }: { data: { date: string; pnl: number }[]; quote?: string; height?: number }) {
  const t = useTokens();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d) => shortDate(`${d}T12:00:00`)} tick={axisTick(t)} stroke={t.axis} tickLine={false} minTickGap={24} />
        <YAxis tickFormatter={(v) => num(v)} tick={axisTick(t)} stroke={t.axis} tickLine={false} axisLine={false} width={56} />
        <ReferenceLine y={0} stroke={t.axis} />
        <Tooltip
          cursor={{ fill: t.grid, opacity: 0.4 }}
          content={({ active, payload }: TooltipContentProps<ValueType, NameType>) =>
            active && payload?.length ? (
              <TipBox title={shortDate(`${payload[0].payload.date}T12:00:00`)} rows={[{ label: "Resultado do dia", value: signedMoney(Number(payload[0].value), quote) }]} />
            ) : null
          }
        />
        <Bar dataKey="pnl" maxBarSize={24} shape={(p: BarShapeProps) => <RoundedBar {...p} />} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.date} fill={d.pnl >= 0 ? t.good : t.bad} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------------ backtest: estratégia x buy & hold

export function BacktestEquityChart({ data, height = 280 }: { data: { time: number; equity: number; buy_hold: number }[]; height?: number }) {
  const t = useTokens();
  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-ink-2">
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 rounded" style={{ background: t.s1 }} />Estratégia</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 rounded" style={{ background: t.muted }} />Buy & hold (só comprar e segurar)</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="time" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={shortDate} tick={axisTick(t)} stroke={t.axis} tickLine={false} minTickGap={40} />
          <YAxis tickFormatter={(v) => num(v, 0)} tick={axisTick(t)} stroke={t.axis} tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
          <Tooltip
            cursor={{ stroke: t.muted, strokeWidth: 1 }}
            content={({ active, payload }: TooltipContentProps<ValueType, NameType>) =>
              active && payload?.length ? (
                <TipBox
                  title={dateTime(payload[0].payload.time)}
                  rows={[
                    { label: "Estratégia", value: num(payload[0].payload.equity), color: t.s1 },
                    { label: "Buy & hold", value: num(payload[0].payload.buy_hold), color: t.muted },
                  ]}
                />
              ) : null
            }
          />
          <Line type="monotone" dataKey="buy_hold" stroke={t.muted} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="equity" stroke={t.s1} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ------------------------------------------------------------------ candles

const MARKER_CODES: Record<string, string> = { signal: "V", stop_loss: "SL", trailing_stop: "TS", breakeven: "BE", take_profit: "TP", manual: "M", end: "F" };

export interface PriceLine {
  label: string;
  price: number;
  kind: "entry" | "stop" | "target";
}

export function CandleChart({ candles, overlays = {}, markers = [], lines = [], height = 380 }: {
  candles: Candle[];
  overlays?: Record<string, LinePoint[]>;
  markers?: ChartMarker[];
  lines?: PriceLine[];
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const t = useTokens();
  const [hover, setHover] = useState<Candle | null>(null);
  const overlayNames = Object.keys(overlays);

  useEffect(() => {
    if (!ref.current || candles.length === 0) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: t.surface }, textColor: t.muted, fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif", attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: t.grid } },
      rightPriceScale: { borderColor: t.axis },
      timeScale: { borderColor: t.axis, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: t.good,
      downColor: t.bad,
      wickUpColor: t.good,
      wickDownColor: t.bad,
      borderVisible: false,
      priceFormat: { type: "custom", formatter: (v: number) => price(v), minMove: 1e-8 },
    });
    series.setData(candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })));

    overlayNames.forEach((name, i) => {
      const line = chart.addSeries(LineSeries, {
        color: seriesColor(t, i),
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(overlays[name].map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    });

    const first = candles[0].time;
    const sorted: SeriesMarker<Time>[] = markers
      .filter((m) => m.time >= first)
      .sort((a, b) => a.time - b.time)
      .map((m) => ({
        time: m.time as UTCTimestamp,
        position: m.side === "BUY" ? "belowBar" : "aboveBar",
        shape: m.side === "BUY" ? "arrowUp" : "arrowDown",
        color: m.side === "BUY" ? t.accent : t.s2,
        text: m.side === "BUY" ? "C" : MARKER_CODES[m.reason] ?? "V",
      }));
    if (sorted.length) createSeriesMarkers(series, sorted);

    for (const l of lines) {
      series.createPriceLine({
        price: l.price,
        color: l.kind === "stop" ? t.bad : l.kind === "target" ? t.good : t.accent,
        lineWidth: 1,
        lineStyle: l.kind === "entry" ? LineStyle.Solid : LineStyle.Dashed,
        axisLabelVisible: true,
        title: l.label,
      });
    }

    chart.subscribeCrosshairMove((param) => {
      const d = param.seriesData.get(series) as Candle | undefined;
      setHover(d && "open" in d ? d : null);
    });
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, overlays, markers, lines, t]);

  const last = hover ?? candles[candles.length - 1];
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {last && (
          <span className="text-ink-2 tabular">
            A <span className="text-ink">{price(last.open)}</span> · M <span className="text-ink">{price(last.high)}</span> · m{" "}
            <span className="text-ink">{price(last.low)}</span> · F <span className="text-ink">{price(last.close)}</span>
          </span>
        )}
        {overlayNames.map((name, i) => (
          <span key={name} className="flex items-center gap-1.5 text-ink-2">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: seriesColor(t, i) }} />
            {name}
          </span>
        ))}
        {markers.length > 0 && (
          <span className="text-muted">▲ C compra · ▼ V sinal · SL stop · TS trailing · BE break-even · TP alvo</span>
        )}
      </div>
      <div ref={ref} style={{ height }} className="w-full" />
    </div>
  );
}
