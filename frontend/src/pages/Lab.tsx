import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, BarChart3, Bot as BotIcon, CheckCircle2, ChevronDown, CircleMinus, Play, Sparkles, XCircle } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { BacktestEquityChart, CandleChart } from "../components/charts";
import { defaultParams, HELP, INTERVALS, ParamsForm, RiskForm, StrategyPicker, useStrategies, useSymbols, type Params } from "../components/forms";
import { ProfilePicker } from "../components/profiles";
import { Button, Card, Empty, ErrorBox, Field, InfoTip, Input, Loading, PageHeader, Pnl, Select, Stat } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, duration, INTERVAL_LABELS, INTERVAL_MINUTES_MAP, num, pct, price, REASONS } from "../lib/format";
import type { BacktestMetrics, BacktestResult, ChartMarker, CompareRow, Profile, RiskConfig } from "../lib/types";
import { mergeProfileRisk, type BotDraft } from "./BotForm";

// ------------------------------------------------------------------ explicações

const METRIC_HELP = {
  ret: "Quanto o capital inicial rendeu no período, já descontando taxas e slippage (a diferença entre o preço esperado e o executado).",
  bh: "Quanto você teria ganhado só comprando no primeiro dia e segurando até o fim. É a régua: a estratégia vale a pena se ganha dele ou se perde bem menos nas quedas.",
  dd: "A maior queda do patrimônio, do pico ao fundo. Mede o 'estômago' necessário: −25% quer dizer que em algum momento 1.000 viraram 750 antes de recuperar.",
  trades: "Quantas operações completas (compra + venda). Com menos de ~20, o resultado pode ser sorte. Tendência costuma acertar 35-50% e compensar ganhando mais nas vencedoras.",
  pf: "Soma dos ganhos ÷ soma das perdas. Acima de 1 dá lucro; acima de 1,5 é bom; acima de 2 é excelente. Abaixo de 1,2, taxas e slippage reais podem zerar o lucro.",
  sharpe: "Retorno ajustado pela oscilação, anualizado. Acima de 1 é bom; entre 0 e 1 é fraco; negativo significa que perdeu.",
  avg: "Resultado médio de cada operação, e a média separada das vencedoras e das perdedoras.",
  exposure: "Parte do período em que o dinheiro ficou comprado. No resto do tempo ficou em USDT, protegido de quedas.",
};

type Verdict = { tone: "good" | "warn" | "bad" | "info"; text: ReactNode };

/** Leitura em português do resultado, com as mesmas réguas das explicações. */
function interpret(m: BacktestMetrics, interval: string): Verdict[] {
  const out: Verdict[] = [];
  const diff = m.total_return_pct - m.buy_hold_return_pct;

  if (m.trades < 10) out.push({ tone: "bad", text: <>Só <strong>{m.trades} operações</strong>: pouco para confiar. Aumente o período ou teste outros pares.</> });
  else if (m.trades < 20) out.push({ tone: "warn", text: <><strong>{m.trades} operações</strong>: amostra pequena. Confirme em outro período antes de usar.</> });
  else out.push({ tone: "good", text: <><strong>{m.trades} operações</strong>: amostra razoável para avaliar.</> });

  if (m.total_return_pct > 0 && diff >= 0) {
    out.push({ tone: "good", text: <>Lucrou <strong>{pct(m.total_return_pct, true)}</strong> e ganhou do buy & hold por {pct(diff)}.</> });
  } else if (m.total_return_pct > 0) {
    out.push({ tone: "warn", text: <>Lucrou <strong>{pct(m.total_return_pct, true)}</strong>, mas {pct(-diff)} a menos que só segurar a moeda. Isso é normal em alta forte: a estratégia fica de fora em parte do tempo para se proteger.</> });
  } else if (m.buy_hold_return_pct < 0 && m.total_return_pct > m.buy_hold_return_pct) {
    out.push({ tone: "warn", text: <>Perdeu <strong>{pct(m.total_return_pct)}</strong>, mas o mercado caiu {pct(m.buy_hold_return_pct)}: protegeu {pct(diff)} do capital.</> });
  } else {
    out.push({ tone: "bad", text: <>Perdeu <strong>{pct(m.total_return_pct)}</strong> e ficou {pct(-diff)} atrás do buy & hold. Não use essa configuração neste par.</> });
  }

  if (m.max_drawdown_pct > -15) out.push({ tone: "good", text: <>Queda máxima de <strong>{pct(m.max_drawdown_pct)}</strong>: moderada.</> });
  else if (m.max_drawdown_pct > -30) out.push({ tone: "warn", text: <>Queda máxima de <strong>{pct(m.max_drawdown_pct)}</strong>: você precisaria aguentar ver o capital cair isso no caminho.</> });
  else out.push({ tone: "bad", text: <>Queda máxima de <strong>{pct(m.max_drawdown_pct)}</strong>: alta. Reduza o tamanho da posição ou prefira outra estratégia.</> });

  if (m.profit_factor != null && m.trades > 0) {
    if (m.profit_factor < 1) out.push({ tone: "bad", text: <>Profit factor <strong>{num(m.profit_factor)}</strong>: as perdas somaram mais que os ganhos.</> });
    else if (m.profit_factor < 1.2) out.push({ tone: "warn", text: <>Profit factor <strong>{num(m.profit_factor)}</strong>: margem pequena, que custos reais podem consumir.</> });
    else out.push({ tone: "good", text: <>Profit factor <strong>{num(m.profit_factor)}</strong>: ganhos bem maiores que as perdas.</> });
  }

  if ((INTERVAL_MINUTES_MAP[interval] ?? 60) <= 60) {
    out.push({ tone: "warn", text: <>Candle de {INTERVAL_LABELS[interval]}: nos nossos testes, 1 hora ou menos perdeu em quase todas as estratégias. Compare com 4 horas.</> });
  }
  out.push({ tone: "info", text: <>Próximo passo: rode o mesmo teste em outro período e em outros pares. Se continuar bom, crie o bot em modo <strong>simulado</strong> antes do real.</> });
  return out;
}

const VERDICT_ICON = {
  good: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good-text" aria-label="bom" />,
  warn: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-text" aria-label="atenção" />,
  bad: <XCircle className="mt-0.5 size-4 shrink-0 text-bad-text" aria-label="ruim" />,
  info: <CircleMinus className="mt-0.5 size-4 shrink-0 text-muted" aria-label="informação" />,
};

function Guide() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem("bt-lab-guide") !== "closed";
    } catch {
      return true;
    }
  });
  const toggle = () => {
    setOpen(!open);
    try {
      localStorage.setItem("bt-lab-guide", open ? "closed" : "open");
    } catch {
      /* ignore */
    }
  };
  return (
    <Card>
      <button type="button" onClick={toggle} className="flex w-full items-center justify-between text-left text-sm font-semibold">
        Como usar o laboratório
        <ChevronDown className={clsx("size-4 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-3 space-y-3 text-sm text-ink-2">
          <p>
            O laboratório simula a estratégia no histórico real da Binance, como se o bot tivesse operado naquele período: compra e vende nos mesmos
            pontos em que o bot compraria, paga taxa e slippage, e respeita stop e alvos. Nenhum dinheiro é usado.
          </p>
          <ol className="list-decimal space-y-1.5 pl-5">
            <li><strong className="text-ink">Nível:</strong> escolha um perfil pronto: Rápido (minutos), Médio (horas) ou Lento (dias). Ele preenche o resto.</li>
            <li><strong className="text-ink">Mercado:</strong> escolha o par e quantos dias simular (o tempo do candle vem do perfil).</li>
            <li><strong className="text-ink">Estratégia:</strong> opcional, ajuste a estratégia e os parâmetros. Eles já vêm com os melhores valores dos testes.</li>
            <li><strong className="text-ink">Rodar backtest:</strong> veja o retorno, compare com o buy & hold e leia a análise automática logo abaixo.</li>
            <li><strong className="text-ink">Comparar todas:</strong> roda todas as estratégias no mesmo par e período e mostra um ranking.</li>
            <li><strong className="text-ink">Confirmar:</strong> repita em outro período e em outros pares. Só então use "Criar bot" (em modo simulado).</li>
          </ol>
          <p className="text-xs text-muted">Clique ou toque no ícone (i) ao lado de cada número do resultado para ver o que ele significa.</p>
        </div>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ resultado

function Metrics({ r }: { r: BacktestResult }) {
  const m = r.metrics;
  const beat = m.total_return_pct - m.buy_hold_return_pct;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat label="Retorno da estratégia" info={METRIC_HELP.ret} value={<Pnl value={m.total_return_pct} percent />} sub={`${num(m.initial_capital)} → ${num(m.final_equity)} USDT`} />
      <Stat label="Buy & hold no período" info={METRIC_HELP.bh} value={<Pnl value={m.buy_hold_return_pct} percent />} sub={`Estratégia ${beat >= 0 ? "melhor" : "pior"} em ${pct(Math.abs(beat))}`} />
      <Stat label="Queda máxima (drawdown)" info={METRIC_HELP.dd} value={pct(m.max_drawdown_pct)} sub="Pior queda do pico ao fundo" />
      <Stat label="Operações" info={METRIC_HELP.trades} value={m.trades} sub={`acerto ${pct(m.win_rate_pct, false, 0)} · ${num(m.avg_bars_in_trade, 1)} candles por operação`} />
      <Stat label="Profit factor" info={METRIC_HELP.pf} value={m.profit_factor == null ? "–" : num(m.profit_factor)} sub="Ganhos ÷ perdas" />
      <Stat label="Sharpe (anualizado)" info={METRIC_HELP.sharpe} value={num(m.sharpe)} sub="Retorno ajustado ao risco" />
      <Stat label="Média por operação" info={METRIC_HELP.avg} value={<Pnl value={m.avg_trade_pct} percent />} sub={`ganho ${pct(m.avg_win_pct, true)} · perda ${pct(m.avg_loss_pct, true)}`} />
      <Stat label="Tempo posicionado" info={METRIC_HELP.exposure} value={pct(m.exposure_pct, false, 0)} sub={`taxas pagas ${num(m.fees_paid)} USDT`} />
    </div>
  );
}

function Reading({ r }: { r: BacktestResult }) {
  const items = interpret(r.metrics, r.request.interval);
  return (
    <Card title="Leitura do resultado">
      <ul className="space-y-2 text-sm text-ink-2">
        {items.map((v, i) => (
          <li key={i} className="flex gap-2.5">
            {VERDICT_ICON[v.tone]}
            <span>{v.text}</span>
          </li>
        ))}
      </ul>
    </Card>
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
            <th className="py-2 pr-3 text-right font-medium">Queda máx.</th>
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
      <p className="mt-3 text-xs text-muted">
        Todas com os parâmetros padrão, o mesmo risco e o mesmo período. Um único par e período não decide nada: repita em outros antes de escolher.
        Clique numa linha para carregar a estratégia no formulário.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ página

export function LabPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const draft = (location.state as { draft?: BotDraft } | null)?.draft;
  const strategies = useStrategies();
  const symbols = useSymbols();

  const [symbol, setSymbol] = useState(draft?.symbol ?? "BTCUSDT");
  const [intervalChoice, setTimeframe] = useState<string | null>(draft?.interval ?? null);
  const [days, setDays] = useState(365);
  const [capital, setCapital] = useState(1000);
  const [strategy, setStrategy] = useState<string | null>(draft?.strategy ?? null);
  const [params, setParams] = useState<Params | null>(draft?.params ?? null);
  const [risk, setRisk] = useState<RiskConfig | null>(draft ? { ...draft.risk, sizing_mode: "percent_balance", balance_percent: 100 } : null);
  const [showRisk, setShowRisk] = useState(false);
  const [profileKey, setProfileKey] = useState<string | null>(draft ? (draft.profile ?? null) : "lento_squeeze_4h");

  const run = useMutation({ mutationFn: (body: object) => api.post<BacktestResult>("/backtest", body) });
  const compare = useMutation({ mutationFn: (body: object) => api.post<CompareRow[]>("/backtest/compare", body) });

  const data = strategies.data;
  const interval = intervalChoice ?? data?.default_interval ?? "4h";
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

  const maxDaysFor = (itv: string) => Math.min(730, Math.floor((20000 * (INTERVAL_MINUTES_MAP[itv] ?? 60)) / 1440));
  const maxDays = maxDaysFor(interval);

  function applyProfile(profile: Profile) {
    setProfileKey(profile.key);
    setTimeframe(profile.interval);
    setDays(Math.min(profile.stats.period_days, maxDaysFor(profile.interval)));
    setStrategy(profile.strategy);
    setParams(profile.params);
    setRisk({ ...mergeProfileRisk(currentRisk!, profile), sizing_mode: "percent_balance", balance_percent: 100 });
  }

  return (
    <>
      <PageHeader title="Laboratório" subtitle="Teste estratégias no histórico real da Binance antes de arriscar dinheiro, com taxa, slippage, stop e alvos." />
      <div className="mb-4">
        <Guide />
      </div>
      <form onSubmit={submit} className="space-y-4">
        <Card title="1. Nível de risco e prazo">
          <ProfilePicker selected={profileKey} onPick={applyProfile} />
        </Card>

        <Card title="2. Mercado e período">
          <div className="grid grid-cols-1 gap-x-3 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Par" help={HELP.symbol}>
              <Input list="lab-symbols" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase().replace("/", ""))} required />
              <datalist id="lab-symbols">{symbols.data?.map((s) => <option key={s.symbol} value={s.symbol} />)}</datalist>
            </Field>
            <Field label="Tempo do candle" help={HELP.interval}>
              <Select
                value={interval}
                onChange={(e) => {
                  setTimeframe(e.target.value);
                  setProfileKey(null);
                }}
              >
                {INTERVALS.map((i) => (
                  <option key={i} value={i}>
                    {INTERVAL_LABELS[i]}
                    {i === data.default_interval ? " (recomendado)" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Período (dias)" help={`Quantos dias de histórico simular, terminando hoje. Mais dias = mais operações e resultado mais confiável. Recomendado: 365. Máximo neste candle: ${maxDays}.`}>
              <Input type="number" min={7} max={maxDays} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            </Field>
            <Field label="Capital inicial (USDT)" help="Valor fictício com que a simulação começa. Não muda a porcentagem de retorno, só os valores em USDT.">
              <Input type="number" min={10} value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
            </Field>
          </div>
        </Card>

        <Card title="3. Estratégia">
          <StrategyPicker strategies={data.strategies} value={key} onChange={(k) => { setStrategy(k); setParams(defaultParams(data.strategies.find((s) => s.key === k))); setProfileKey(null); }} />
          {info && (
            <div className="mt-5 space-y-4 border-t border-line pt-4">
              <p className="text-sm text-ink-2">{info.description}</p>
              <ParamsForm strategy={info} values={currentParams} onChange={setParams} />
            </div>
          )}
        </Card>

        <Card>
          <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setShowRisk(!showRisk)}>
            <span>
              <span className="block text-sm font-semibold">4. Gerenciamento de risco</span>
              <span className="mt-0.5 block text-xs text-ink-2">Stop loss, alvos, tamanho da posição e taxa. Os padrões foram os que deram melhor resultado nos testes.</span>
            </span>
            <ChevronDown className={clsx("size-4 shrink-0 text-muted transition-transform", showRisk && "rotate-180")} />
          </button>
          {showRisk && <div className="mt-5"><RiskForm risk={currentRisk} onChange={setRisk} lab /></div>}
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" variant="primary" loading={run.isPending}><Play className="size-4" />Rodar backtest</Button>
          <Button type="button" loading={compare.isPending} onClick={() => compare.mutate({ symbol, interval, days, risk: currentRisk })}>
            <BarChart3 className="size-4" />Comparar todas as estratégias
          </Button>
          <InfoTip>"Rodar backtest" testa a estratégia e os parâmetros escolhidos acima. "Comparar todas" roda as 6 estratégias com os parâmetros padrão no mesmo par e período.</InfoTip>
        </div>
        <ErrorBox error={run.error ?? compare.error} />
      </form>

      {compare.data && (
        <Card title={`Comparação · ${symbol} · ${INTERVAL_LABELS[interval]} · ${days} dias`} className="mt-6">
          <CompareTable rows={compare.data} onPick={(k) => { setStrategy(k); setParams(defaultParams(data.strategies.find((s) => s.key === k))); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </Card>
      )}

      {run.isPending && <Loading label="Baixando o histórico e simulando…" />}

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
              <Button variant="primary" onClick={() => navigate("/bots/new", { state: { draft: { symbol: result.request.symbol, interval: result.request.interval, strategy: result.request.strategy, params: result.request.params, risk: result.request.risk, profile: profileKey } satisfies BotDraft } })}>
                <BotIcon className="size-4" />Criar bot com esta configuração
              </Button>
            </div>
          </div>

          <Metrics r={result} />
          <Reading r={result} />

          <Card title="Patrimônio: estratégia × buy & hold">
            <p className="-mt-1 mb-3 text-xs text-ink-2">Evolução do capital, em USDT, ao longo do período. A linha cinza é quanto você teria só segurando a moeda.</p>
            <BacktestEquityChart data={result.equity_curve} />
          </Card>

          {result.candles && (
            <Card title="Operações no gráfico">
              <p className="-mt-1 mb-3 text-xs text-ink-2">Cada seta é uma compra (▲) ou venda (▼) que o bot teria feito. As linhas coloridas são os indicadores da estratégia.</p>
              <CandleChart candles={result.candles} overlays={result.overlays} markers={markers} height={420} />
            </Card>
          )}

          <Card title={`Operações (${result.trades.length})`}>
            {result.trades.length === 0 ? (
              <Empty title="Nenhuma operação no período">As condições de entrada não foram atendidas. Tente um período maior, outro par ou o candle de 4 horas.</Empty>
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
            Cada sinal é executado na abertura do candle seguinte, com taxa de {num(currentRisk.fee_pct)}% por ordem e slippage de 0,05%. Resultado passado não
            garante resultado futuro.
          </p>
        </div>
      )}
    </>
  );
}
