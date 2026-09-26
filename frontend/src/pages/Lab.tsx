import { useMutation } from "@tanstack/react-query";
import { BarChart3, Bot as BotIcon, ChevronDown, Play, Sparkles } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router";
import { BacktestEquityChart, CandleChart } from "../components/charts";
import { defaultParams, INTERVALS, ParamsForm, RiskForm, StrategyPicker, useStrategies, useSymbols, type Params } from "../components/forms";
import { Button, Card, Empty, ErrorBox, Field, Input, Loading, PageHeader, Pnl, Select, Stat } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, duration, INTERVAL_LABELS, INTERVAL_MINUTES_MAP, num, pct, price, REASONS } from "../lib/format";
import type { BacktestResult, ChartMarker, CompareRow, RiskConfig } from "../lib/types";
import type { BotDraft } from "./BotForm";

function Metrics({ r }: { r: BacktestResult }) {
  const m = r.metrics;
  const beat = m.total_return_pct - m.buy_hold_return_pct;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat label="Retorno da estratégia" value={<Pnl value={m.total_return_pct} percent />} sub={`${num(m.initial_capital)} → ${num(m.final_equity)}`} />
      <Stat label="Buy & hold no período" value={<Pnl value={m.buy_hold_return_pct} percent />} sub={`${beat >= 0 ? "Estratégia melhor em" : "Estratégia pior em"} ${pct(Math.abs(beat))}`} />
      <Stat label="Queda máxima (drawdown)" value={pct(m.max_drawdown_pct)} sub="Pior queda do pico ao fundo" />
      <Stat label="Operações" value={m.trades} sub={`acerto ${pct(m.win_rate_pct, false, 0)} · ${m.avg_bars_in_trade} candles em média`} />
      <Stat label="Profit factor" value={m.profit_factor == null ? "–" : num(m.profit_factor)} sub="Ganhos ÷ perdas (acima de 1 = lucro)" />
      <Stat label="Sharpe (anualizado)" value={num(m.sharpe)} sub="Retorno ajustado ao risco" />
      <Stat label="Média por operação" value={<Pnl value={m.avg_trade_pct} percent />} sub={`ganho ${pct(m.avg_win_pct, true)} · perda ${pct(m.avg_loss_pct, true)}`} />
      <Stat label="Tempo posicionado" value={pct(m.exposure_pct, false, 0)} sub={`taxas pagas ${num(m.fees_paid)}`} />
    </div>
  );
}

function CompareTable({ rows, onPick }: { rows: CompareRow[]; onPick: (key: string) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm tabular">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-2">
            <th className="py-2 pr-3 font-medium">Estratégia</th>
            <th className="py-2 pr-3 text-right font-medium">Retorno</th>
            <th className="py-2 pr-3 text-right font-medium">Buy & hold</th>
            <th className="py-2 pr-3 text-right font-medium">Drawdown</th>
            <th className="py-2 pr-3 text-right font-medium">Operações</th>
            <th className="py-2 pr-3 text-right font-medium">Acerto</th>
            <th className="py-2 text-right font-medium">Profit factor</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.strategy} className="cursor-pointer hover:bg-surface-2" onClick={() => onPick(r.strategy)}>
              <td className="py-2 pr-3 text-ink">{r.name}</td>
              {r.error ? (
                <td colSpan={6} className="py-2 text-bad-text">{r.error}</td>
              ) : (
                <>
                  <td className="py-2 pr-3 text-right"><Pnl value={r.total_return_pct} percent /></td>
                  <td className="py-2 pr-3 text-right text-ink-2">{pct(r.buy_hold_return_pct, true)}</td>
                  <td className="py-2 pr-3 text-right text-ink-2">{pct(r.max_drawdown_pct)}</td>
                  <td className="py-2 pr-3 text-right text-ink-2">{r.trades}</td>
                  <td className="py-2 pr-3 text-right text-ink-2">{pct(r.win_rate_pct, false, 0)}</td>
                  <td className="py-2 text-right text-ink-2">{r.profit_factor == null ? "–" : num(r.profit_factor)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-muted">Parâmetros padrão de cada estratégia, mesmo risco e período. Clique numa linha para abri-la no formulário.</p>
    </div>
  );
}

export function LabPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const draft = (location.state as { draft?: BotDraft } | null)?.draft;
  const strategies = useStrategies();
  const symbols = useSymbols();

  const [symbol, setSymbol] = useState(draft?.symbol ?? "BTCUSDT");
  const [interval, setTimeframe] = useState(draft?.interval ?? "1h");
  const [days, setDays] = useState(180);
  const [capital, setCapital] = useState(1000);
  const [strategy, setStrategy] = useState<string | null>(draft?.strategy ?? null);
  const [params, setParams] = useState<Params | null>(draft?.params ?? null);
  const [risk, setRisk] = useState<RiskConfig | null>(draft ? { ...draft.risk, sizing_mode: "percent_balance", balance_percent: 100 } : null);
  const [showRisk, setShowRisk] = useState(false);

  const run = useMutation({
    mutationFn: (body: object) => api.post<BacktestResult>("/backtest", body),
  });
  const compare = useMutation({
    mutationFn: (body: object) => api.post<CompareRow[]>("/backtest/compare", body),
  });

  const data = strategies.data;
  const key = strategy ?? data?.default ?? "";
  const info = data?.strategies.find((s) => s.key === key);
  const currentParams = params ?? defaultParams(info);
  // no laboratório o padrão é investir 100% do capital, para o retorno refletir a estratégia
  const currentRisk: RiskConfig | null = risk ?? (data ? { ...data.default_risk, sizing_mode: "percent_balance", balance_percent: 100 } : null);
  const result = run.data;

  const markers = useMemo<ChartMarker[]>(() => {
    if (!result) return [];
    return result.trades.flatMap((t) => [
      { time: t.entry_time / 1000, side: "BUY" as const, price: t.entry_price, reason: "signal" },
      { time: t.exit_time / 1000, side: "SELL" as const, price: t.exit_price, reason: t.exit_reason },
    ]);
  }, [result]);

  if (!data || !currentRisk) return <Loading />;

  function submit(e: FormEvent) {
    e.preventDefault();
    run.mutate({ symbol, interval, strategy: key, params: currentParams, risk: currentRisk, days, initial_capital: capital });
  }

  const maxDays = Math.floor((20000 * (INTERVAL_MINUTES_MAP[interval] ?? 60)) / 1440);

  return (
    <>
      <PageHeader title="Laboratório" subtitle="Teste estratégias com dados reais da Binance antes de arriscar dinheiro: com taxa, slippage, stop e alvos." />
      <form onSubmit={submit} className="space-y-4">
        <Card>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Par">
              <Input list="lab-symbols" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase().replace("/", ""))} required />
              <datalist id="lab-symbols">{symbols.data?.map((s) => <option key={s.symbol} value={s.symbol} />)}</datalist>
            </Field>
            <Field label="Tempo do candle">
              <Select value={interval} onChange={(e) => setTimeframe(e.target.value)}>
                {INTERVALS.map((i) => <option key={i} value={i}>{INTERVAL_LABELS[i]}</option>)}
              </Select>
            </Field>
            <Field label="Período (dias)" help={`Máximo ~${Math.min(maxDays, 730)} dias neste tempo de candle`}>
              <Input type="number" min={7} max={730} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            </Field>
            <Field label="Capital inicial (USDT)">
              <Input type="number" min={10} value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
            </Field>
          </div>
        </Card>

        <Card title="Estratégia">
          <StrategyPicker strategies={data.strategies} value={key} onChange={(k) => { setStrategy(k); setParams(defaultParams(data.strategies.find((s) => s.key === k))); }} />
          {info && <div className="mt-5 border-t border-line pt-4"><ParamsForm strategy={info} values={currentParams} onChange={setParams} /></div>}
        </Card>

        <Card>
          <button type="button" className="flex w-full items-center justify-between text-sm font-semibold" onClick={() => setShowRisk(!showRisk)}>
            Gerenciamento de risco
            <ChevronDown className={`size-4 text-muted transition-transform ${showRisk ? "rotate-180" : ""}`} />
          </button>
          {showRisk && <div className="mt-4"><RiskForm risk={currentRisk} onChange={setRisk} /></div>}
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" loading={run.isPending}><Play className="size-4" />Rodar backtest</Button>
          <Button type="button" loading={compare.isPending} onClick={() => compare.mutate({ symbol, interval, days, risk: currentRisk })}>
            <BarChart3 className="size-4" />Comparar todas as estratégias
          </Button>
        </div>
        <ErrorBox error={run.error ?? compare.error} />
      </form>

      {compare.data && (
        <Card title={`Comparação · ${symbol} · ${INTERVAL_LABELS[interval]} · ${days} dias`} className="mt-6">
          <CompareTable rows={compare.data} onPick={(k) => { setStrategy(k); setParams(defaultParams(data.strategies.find((s) => s.key === k))); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </Card>
      )}

      {run.isPending && <Loading label="Baixando histórico e simulando…" />}

      {result && !run.isPending && (
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">{result.request.strategy_name} · {result.request.symbol} · {INTERVAL_LABELS[result.request.interval]}</h2>
              <p className="text-xs text-muted">
                {dateTime(result.metrics.period_start)} até {dateTime(result.metrics.period_end)} · {result.metrics.bars} candles
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => navigate("/ai", { state: { backtest: result, prompt: "Analise este backtest: os resultados são confiáveis? O que você mudaria? Valide suas sugestões com novos backtests, inclusive em outros períodos." } })}>
                <Sparkles className="size-4" />Analisar com IA
              </Button>
              <Button variant="primary" onClick={() => navigate("/bots/new", { state: { draft: { symbol: result.request.symbol, interval: result.request.interval, strategy: result.request.strategy, params: result.request.params, risk: result.request.risk } satisfies BotDraft } })}>
                <BotIcon className="size-4" />Criar bot com esta configuração
              </Button>
            </div>
          </div>

          <Metrics r={result} />

          <Card title="Patrimônio: estratégia × buy & hold">
            <BacktestEquityChart data={result.equity_curve} />
          </Card>

          {result.candles && (
            <Card title="Operações no gráfico">
              <CandleChart candles={result.candles} overlays={result.overlays} markers={markers} height={420} />
            </Card>
          )}

          <Card title={`Operações (${result.trades.length})`}>
            {result.trades.length === 0 ? (
              <Empty title="Nenhuma operação no período">As condições de entrada não foram atendidas. Tente outro período, par ou parâmetros.</Empty>
            ) : (
              <div className="max-h-[480px] overflow-auto">
                <table className="w-full text-sm tabular">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-line text-left text-xs text-ink-2">
                      <th className="py-2 pr-3 font-medium">Entrada</th>
                      <th className="py-2 pr-3 text-right font-medium">Preço</th>
                      <th className="py-2 pr-3 font-medium">Saída</th>
                      <th className="py-2 pr-3 text-right font-medium">Preço</th>
                      <th className="py-2 pr-3 font-medium">Motivo</th>
                      <th className="py-2 pr-3 text-right font-medium">Duração</th>
                      <th className="py-2 text-right font-medium">Resultado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {[...result.trades].reverse().map((t) => (
                      <tr key={t.entry_time}>
                        <td className="py-2 pr-3 whitespace-nowrap text-ink-2">{dateTime(t.entry_time)}</td>
                        <td className="py-2 pr-3 text-right">{price(t.entry_price)}</td>
                        <td className="py-2 pr-3 whitespace-nowrap text-ink-2">{dateTime(t.exit_time)}</td>
                        <td className="py-2 pr-3 text-right">{price(t.exit_price)}</td>
                        <td className="py-2 pr-3 text-ink-2">{REASONS[t.exit_reason] ?? t.exit_reason}{t.partial_exits > 0 ? ` (+${t.partial_exits} parcial)` : ""}</td>
                        <td className="py-2 pr-3 text-right text-ink-2">{duration((t.exit_time - t.entry_time) / 1000)}</td>
                        <td className="py-2 text-right whitespace-nowrap"><Pnl value={t.pnl} /> <span className="text-xs text-muted">({pct(t.pnl_pct, true)})</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <p className="text-xs text-muted">
            Backtest executa cada sinal na abertura do candle seguinte, com taxa de {currentRisk.fee_pct}% e slippage de 0,05%. Resultado passado não garante resultado futuro:
            confirme em outros períodos e pares, e rode em modo simulado antes do real.
          </p>
        </div>
      )}
    </>
  );
}
