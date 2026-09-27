import { useQuery } from "@tanstack/react-query";
import { Bot as BotIcon, Plus, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { ModeBadge, StatusBadge, EventsList, PositionsTable } from "../components/bot";
import { DailyPnlChart, EquityChart } from "../components/charts";
import { TierBadge } from "../components/profiles";
import { Button, Card, Empty, ErrorBox, Loading, PageHeader, Pnl, Segmented, Stat } from "../components/ui";
import { api } from "../lib/api";
import { duration, fearGreedTone, money, num, pct, signedMoney } from "../lib/format";
import type { BotAlert, Credentials, Dashboard, SentimentResponse } from "../lib/types";

const TONE_TEXT = { bad: "text-bad-text", warn: "text-warn-text", neutral: "text-ink", good: "text-good-text" } as const;

/** Humor do mercado e travas por notícia, com link para a aba de notícias. */
function MarketCard() {
  const sentiment = useQuery({ queryKey: ["sentiment"], queryFn: () => api.get<SentimentResponse>("/news/sentiment?days=120"), refetchInterval: 600_000 });
  const alerts = useQuery({ queryKey: ["news-alerts"], queryFn: () => api.get<BotAlert[]>("/news/alerts"), refetchInterval: 60_000 });
  const latest = sentiment.data?.latest;
  const blocked = (alerts.data ?? []).filter((a) => a.blocked);
  return (
    <Card title="Mercado agora" action={<Link to="/ai/noticias" className="text-xs text-accent hover:underline">notícias</Link>}>
      <div className="space-y-2 text-sm">
        {latest ? (
          <div className="flex items-baseline gap-2">
            <span className={`text-2xl font-semibold tabular ${TONE_TEXT[fearGreedTone(latest.value)]}`}>{latest.value}</span>
            <span className="text-ink-2">
              {latest.label}
              {latest.change_7d != null ? ` · ${latest.change_7d > 0 ? "+" : ""}${latest.change_7d} na semana` : ""}
            </span>
          </div>
        ) : (
          <p className="text-muted">Índice de medo e ganância ainda não baixado.</p>
        )}
        {blocked.length > 0 ? (
          <ul className="space-y-1 text-xs">
            {blocked.map((a) => (
              <li key={a.bot_id} className="flex gap-1.5 text-warn-text">
                <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
                <span><Link to={`/bots/${a.bot_id}`} className="font-medium hover:underline">{a.name}</Link>: {a.reason}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">Nenhum bot com compras travadas por sentimento ou notícia.</p>
        )}
      </div>
    </Card>
  );
}

type ModeFilter = "live" | "paper" | "all";

function useDefaultMode(): [ModeFilter, (m: ModeFilter) => void] {
  const [mode, setMode] = useState<ModeFilter | null>(() => {
    try {
      return (localStorage.getItem("bt-dash-mode") as ModeFilter) || null;
    } catch {
      return null;
    }
  });
  const bots = useQuery({ queryKey: ["dashboard", "all"], queryFn: () => api.get<Dashboard>("/dashboard?mode=all"), enabled: mode === null });
  useEffect(() => {
    if (mode === null && bots.data) setMode(bots.data.bots.some((b) => b.mode === "live") ? "live" : "paper");
  }, [mode, bots.data]);
  const set = (m: ModeFilter) => {
    setMode(m);
    try {
      localStorage.setItem("bt-dash-mode", m);
    } catch {
      /* ignore */
    }
  };
  return [mode ?? "paper", set];
}

function Balance() {
  const creds = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  const balance = useQuery({
    queryKey: ["balance"],
    queryFn: () => api.get<{ total_usdt: number; testnet: boolean; assets: { asset: string; total: number; value_usdt: number | null }[] }>("/account/balance"),
    enabled: Boolean(creds.data?.binance.configured),
    refetchInterval: 60_000,
    retry: false,
  });
  if (!creds.data?.binance.configured) return null;
  return (
    <Stat
      label={balance.data?.testnet ? "Carteira Binance (testnet)" : "Carteira Binance"}
      value={balance.data ? money(balance.data.total_usdt) : balance.isError ? "indisponível" : "…"}
      sub={balance.data ? balance.data.assets.slice(0, 3).map((a) => `${a.asset} ${num(a.total, 4)}`).join(" · ") : undefined}
    />
  );
}

export function DashboardPage() {
  const [mode, setMode] = useDefaultMode();
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", mode],
    queryFn: () => api.get<Dashboard>(`/dashboard?mode=${mode}`),
    refetchInterval: 15_000,
  });

  const header = (
    <PageHeader
      title="Painel"
      subtitle="Quanto seus bots estão ganhando, em tempo real."
      actions={
        <Segmented<ModeFilter>
          value={mode}
          onChange={setMode}
          options={[
            { value: "live", label: "Real" },
            { value: "paper", label: "Simulado" },
            { value: "all", label: "Tudo" },
          ]}
        />
      }
    />
  );

  if (isLoading) return <>{header}<Loading /></>;
  if (error || !data) return <>{header}<ErrorBox error={error} /></>;
  const s = data.summary;

  if (s.total_bots === 0) {
    return (
      <>
        {header}
        <Card>
          <Empty icon={<BotIcon className="size-8" />} title={mode === "live" ? "Nenhum bot em modo real" : "Nenhum bot ainda"}>
            Crie um bot em modo simulado para testar sem risco. Ele usa preços reais da Binance, com taxa e slippage.
            <div className="mt-4 flex justify-center gap-2">
              <Button variant="primary" onClick={() => navigate("/bots/new")}><Plus className="size-4" />Criar bot</Button>
              <Button onClick={() => navigate("/lab")}>Testar estratégias</Button>
            </div>
          </Empty>
        </Card>
      </>
    );
  }

  return (
    <>
      {header}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="rounded-xl border border-line bg-surface px-5 py-4 lg:col-span-2">
          <div className="text-xs text-ink-2">Resultado total {mode === "paper" ? "(simulado)" : mode === "live" ? "(real)" : "(real + simulado)"}</div>
          <div className="mt-1 text-5xl font-semibold tracking-tight">
            <Pnl value={s.total_pnl} quote="" proportional />
            <span className="ml-2 text-lg font-normal text-muted">USDT</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2">
            <span>Hoje <Pnl value={s.today_pnl} /></span>
            <span>Realizado <Pnl value={s.realized_pnl} /></span>
            <span>Em aberto <Pnl value={s.unrealized_pnl} /></span>
          </div>
        </div>
        <Stat label="Taxa de acerto" value={s.win_rate == null ? "–" : pct(s.win_rate, false, 0)} sub={`${s.wins} de ${s.trades} operações com lucro`} />
        <Stat label="Bots operando" value={`${s.running_bots} de ${s.total_bots}`} sub={`${s.open_positions} posições abertas · ${money(s.invested)} investidos`} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Resultado acumulado" className="lg:col-span-2">
          {data.equity_curve.length > 1 ? <EquityChart data={data.equity_curve} /> : <Empty title="Sem operações fechadas ainda">A curva aparece depois da primeira venda.</Empty>}
        </Card>
        <Card title="Resultado por dia (30 dias)">
          <DailyPnlChart data={data.daily_pnl} />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Bots" className="lg:col-span-2" action={<Link to="/bots/new" className="text-xs text-accent hover:underline">+ Novo bot</Link>} padded={false}>
          {/* celular: cartões */}
          <ul className="divide-y divide-line md:hidden">
            {data.bots.map((b) => (
              <li key={b.id}>
                <Link to={`/bots/${b.id}`} className="flex items-center justify-between gap-3 px-4 py-3 active:bg-surface-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-ink">{b.name}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      <StatusBadge bot={b} />
                      <TierBadge interval={b.interval} />
                      <ModeBadge mode={b.mode} />
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <Pnl value={b.stats.total_pnl} quote={b.quote_asset} className="text-sm font-semibold" />
                    <div className="text-xs text-muted">{b.stats.trades} operações{b.position ? " · 1 aberta" : ""}</div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto px-4 pb-2 md:block">
            <table className="w-full text-sm tabular">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-2">
                  <th className="py-2 pr-3 font-medium">Bot</th>
                  <th className="py-2 pr-3 font-medium">Estratégia</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 text-right font-medium">Operando há</th>
                  <th className="py-2 pr-3 text-right font-medium">Operações</th>
                  <th className="py-2 text-right font-medium">Resultado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.bots.map((b) => (
                  <tr key={b.id} className="cursor-pointer hover:bg-surface-2" onClick={() => navigate(`/bots/${b.id}`)}>
                    <td className="py-2.5 pr-3">
                      <div className="font-medium text-ink">{b.name}</div>
                      <div className="flex items-center gap-1.5 text-xs text-muted">{b.symbol} · {b.interval} <TierBadge interval={b.interval} /> <ModeBadge mode={b.mode} /></div>
                    </td>
                    <td className="py-2.5 pr-3 text-ink-2">{b.strategy_name}</td>
                    <td className="py-2.5 pr-3"><StatusBadge bot={b} /></td>
                    <td className="py-2.5 pr-3 text-right text-ink-2">{duration(b.runtime_seconds)}</td>
                    <td className="py-2.5 pr-3 text-right text-ink-2">{b.stats.trades}{b.position ? " + 1 aberta" : ""}</td>
                    <td className="py-2.5 text-right"><Pnl value={b.stats.total_pnl} quote={b.quote_asset} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="space-y-4">
          <Balance />
          <MarketCard />
          <Card title="Por estratégia">
            {data.by_strategy.length ? (
              <ul className="space-y-2 text-sm">
                {data.by_strategy.map((st) => (
                  <li key={st.strategy} className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-ink">{st.name}</div>
                      <div className="text-xs text-muted">{st.trades} operações · acerto {pct(st.win_rate, false, 0)}</div>
                    </div>
                    <Pnl value={st.pnl} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">Sem operações fechadas.</p>
            )}
          </Card>
          <Stat label="Taxas pagas" value={signedMoney(-s.fees)} sub="Já descontadas do resultado" />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Últimas operações">
          <PositionsTable positions={data.recent_trades} showBot compact />
        </Card>
        <Card title="Atividade recente">
          <EventsList events={data.recent_events} showBot />
        </Card>
      </div>
    </>
  );
}
