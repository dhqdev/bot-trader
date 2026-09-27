import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ExternalLink, Newspaper, RefreshCw, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { AITabs } from "../components/aitabs";
import { useTokens } from "../components/charts";
import { Badge, Button, Card, Empty, ErrorBox, InfoTip, Loading, PageHeader, Select } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, fearGreedTone, num, shortDate, timeAgo } from "../lib/format";
import type { BotAlert, FearGreed, NewsItem, NewsStatus, SentimentResponse } from "../lib/types";

const TONE_TEXT = { bad: "text-bad-text", warn: "text-warn-text", neutral: "text-ink", good: "text-good-text" } as const;

function sentimentBadge(v: number) {
  const value = num(v, 2);
  if (v <= -0.5) return <Badge tone="bad">Muito negativa {value}</Badge>;
  if (v < -0.15) return <Badge tone="warn">Negativa {value}</Badge>;
  if (v >= 0.5) return <Badge tone="good">Muito positiva +{value}</Badge>;
  if (v > 0.15) return <Badge tone="good">Positiva +{value}</Badge>;
  return <Badge>Neutra</Badge>;
}

function FearGreedCard({ data }: { data: SentimentResponse | undefined }) {
  const t = useTokens();
  const latest: FearGreed | null | undefined = data?.latest;
  const tone = fearGreedTone(latest?.value);
  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          Medo e Ganância
          <InfoTip>
            Índice diário do mercado cripto (alternative.me), de 0 (medo extremo) a 100 (ganância extrema). Os bots usam como filtro: por padrão não compram com medo
            extremo (≤ 20), o que nos testes manteve ou melhorou o resultado com quedas menores.
          </InfoTip>
        </span>
      }
    >
      {latest ? (
        <div className="space-y-3">
          <div className="flex items-end gap-3">
            <span className={clsx("text-4xl font-semibold tabular", TONE_TEXT[tone])}>{latest.value}</span>
            <div className="pb-1 text-sm">
              <div className={clsx("font-medium", TONE_TEXT[tone])}>{latest.label}</div>
              <div className="text-xs text-muted">
                {latest.change_7d != null ? `${latest.change_7d > 0 ? "+" : ""}${latest.change_7d} na semana` : "sem comparação semanal"}
                {latest.stale ? " · dado antigo" : ""}
              </div>
            </div>
          </div>
          {data && data.history.length > 1 && (
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={data.history} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={t.grid} vertical={false} />
                <XAxis dataKey="date" tickFormatter={(d) => shortDate(`${d}T12:00:00`)} tick={{ fill: t.muted, fontSize: 11 }} stroke={t.axis} tickLine={false} minTickGap={32} />
                <YAxis domain={[0, 100]} ticks={[0, 20, 50, 80, 100]} tick={{ fill: t.muted, fontSize: 11 }} stroke={t.axis} tickLine={false} axisLine={false} width={28} />
                <ReferenceLine y={20} stroke={t.bad} strokeDasharray="4 4" />
                <Tooltip
                  cursor={{ stroke: t.muted, strokeWidth: 1 }}
                  content={({ active, payload }: TooltipContentProps<ValueType, NameType>) =>
                    active && payload?.length ? (
                      <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
                        <div className="text-muted">{shortDate(`${payload[0].payload.date}T12:00:00`)}</div>
                        <div className="font-medium text-ink tabular">{String(payload[0].value)}</div>
                      </div>
                    ) : null
                  }
                />
                <Area type="monotone" dataKey="value" stroke={t.accent} strokeWidth={2} fill={t.accent} fillOpacity={0.08} dot={false} activeDot={{ r: 4, stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
          <p className="text-xs text-muted">Linha tracejada: limite de medo extremo usado pelos bots (20).</p>
        </div>
      ) : (
        <p className="text-sm text-muted">O índice ainda não foi baixado. Ele é atualizado automaticamente a cada hora.</p>
      )}
    </Card>
  );
}

function AlertsCard({ alerts }: { alerts: BotAlert[] | undefined }) {
  return (
    <Card title="Travas nos bots agora">
      {!alerts?.length ? (
        <p className="text-sm text-muted">Nenhum bot criado.</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {alerts.map((a) => (
            <li key={a.bot_id} className="py-2">
              <div className="flex items-center justify-between gap-2">
                <Link to={`/bots/${a.bot_id}`} className="min-w-0 truncate font-medium text-ink hover:underline">{a.name}</Link>
                {a.blocked ? (
                  <Badge tone="warn"><ShieldAlert className="size-3" />Compras travadas</Badge>
                ) : (
                  <Badge tone="good"><ShieldCheck className="size-3" />Liberado</Badge>
                )}
              </div>
              {a.blocked && <p className="mt-1 text-xs text-ink-2">{a.reason}</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">As travas só impedem novas compras (e, se você escolheu, vendem a posição com notícia grave confirmada). Mudam nas configurações de risco de cada bot.</p>
    </Card>
  );
}

function SourcesCard({ status, onRefresh, refreshing, error }: { status: NewsStatus | undefined; onRefresh: () => void; refreshing: boolean; error: unknown }) {
  const errors = Object.entries(status?.last_fetch?.errors ?? {});
  return (
    <Card title="Fontes">
      <div className="space-y-3 text-sm">
        <p className="text-ink-2">
          {status?.feeds.map((f) => f.name).join(", ")}. Coletadas a cada 15 minutos
          {status?.last_fetch ? ` · última ${timeAgo(status.last_fetch.at)}` : ""}.
        </p>
        {status?.last_ai ? (
          <p className="flex gap-1.5 text-xs text-ink-2"><Sparkles className="mt-0.5 size-3.5 shrink-0 text-accent" />Classificadas pela IA ({status.last_ai.model}) {timeAgo(status.last_ai.at)}.</p>
        ) : (
          <p className="text-xs text-muted">Sem a chave da Anthropic, a classificação é só por palavras-chave (menos precisa). Para travar compras, a mesma notícia grave precisa aparecer em duas fontes.</p>
        )}
        {errors.length > 0 && (
          <ul className="space-y-0.5 text-xs text-warn-text">
            {errors.map(([name, msg]) => (
              <li key={name}>{name}: fora do ar ({msg.slice(0, 80)})</li>
            ))}
          </ul>
        )}
        <Button size="sm" onClick={onRefresh} loading={refreshing}><RefreshCw className="size-3.5" />Atualizar agora</Button>
        <ErrorBox error={error} />
      </div>
    </Card>
  );
}

function NewsRow({ n }: { n: NewsItem }) {
  const text = n.ai_summary || n.summary;
  return (
    <li className="py-3">
      <a href={n.url} target="_blank" rel="noopener noreferrer" className="group inline-flex items-start gap-1.5 font-medium text-ink hover:underline">
        <span>{n.title}</span>
        <ExternalLink className="mt-1 size-3 shrink-0 text-muted group-hover:text-ink" />
      </a>
      {text && <p className={clsx("mt-1 text-sm", n.ai_summary ? "text-ink-2" : "line-clamp-2 text-muted")}>{text}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
        {sentimentBadge(n.sentiment)}
        {n.impact !== "low" && <Badge tone={n.impact === "high" && n.sentiment < 0 ? "bad" : "neutral"}>Impacto {n.impact === "high" ? "alto" : "médio"}</Badge>}
        {n.assets.map((a) => (
          <Badge key={a} tone="accent">{a === "MARKET" ? "Mercado todo" : a}</Badge>
        ))}
        <span className="text-muted" title={dateTime(n.published_at)}>{n.source} · {timeAgo(n.published_at)}</span>
        <span className="text-muted">· {n.classified_by === "ai" ? "classificada pela IA" : "palavras-chave"}</span>
      </div>
    </li>
  );
}

export function NewsPage() {
  const qc = useQueryClient();
  const [asset, setAsset] = useState("");
  const [impact, setImpact] = useState("");
  const [hours, setHours] = useState(72);
  const sentiment = useQuery({ queryKey: ["sentiment"], queryFn: () => api.get<SentimentResponse>("/news/sentiment?days=120"), refetchInterval: 600_000 });
  const alerts = useQuery({ queryKey: ["news-alerts"], queryFn: () => api.get<BotAlert[]>("/news/alerts"), refetchInterval: 60_000 });
  const status = useQuery({ queryKey: ["news-status"], queryFn: () => api.get<NewsStatus>("/news/status"), refetchInterval: 60_000 });
  const params = new URLSearchParams({ hours: String(hours), limit: "150" });
  if (asset) params.set("asset", asset);
  if (impact) params.set("impact", impact);
  const news = useQuery({ queryKey: ["news", asset, impact, hours], queryFn: () => api.get<NewsItem[]>(`/news?${params}`), refetchInterval: 60_000 });
  const refresh = useMutation({
    mutationFn: () => api.post("/news/refresh"),
    onSuccess: () => {
      for (const key of ["news", "news-status", "sentiment", "news-alerts"]) qc.invalidateQueries({ queryKey: [key] });
    },
  });
  const assets = useMemo(() => {
    const set = new Set(["BTC", "ETH", "SOL", ...(alerts.data ?? []).map((a) => a.asset)]);
    return [...set].sort();
  }, [alerts.data]);

  return (
    <>
      <PageHeader title="Análise com IA" subtitle="Notícias do mercado e o humor dos investidores. Os bots usam os dois para decidir quando não comprar." />
      <AITabs />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
        <Card title="Notícias">
          <div className="mb-2 grid grid-cols-3 gap-2">
            <Select value={asset} onChange={(e) => setAsset(e.target.value)} aria-label="Moeda">
              <option value="">Todas</option>
              {assets.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </Select>
            <Select value={impact} onChange={(e) => setImpact(e.target.value)} aria-label="Impacto">
              <option value="">Impacto</option>
              <option value="high">Alto</option>
              <option value="medium">Médio</option>
            </Select>
            <Select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Período">
              <option value={24}>24 h</option>
              <option value={72}>3 dias</option>
              <option value={168}>7 dias</option>
            </Select>
          </div>
          {news.isLoading ? (
            <Loading />
          ) : news.data?.length ? (
            <ul className="divide-y divide-line">
              {news.data.map((n) => (
                <NewsRow key={n.id} n={n} />
              ))}
            </ul>
          ) : (
            <Empty icon={<Newspaper className="size-8" />} title="Nenhuma notícia neste filtro">
              As notícias são coletadas automaticamente a cada 15 minutos. Se o sistema acabou de iniciar, toque em Atualizar agora.
            </Empty>
          )}
          <ErrorBox error={news.error} />
        </Card>
        <div className="space-y-4">
          <FearGreedCard data={sentiment.data} />
          <AlertsCard alerts={alerts.data} />
          <SourcesCard status={status.data} onRefresh={() => refresh.mutate()} refreshing={refresh.isPending} error={refresh.error} />
        </div>
      </div>
    </>
  );
}
