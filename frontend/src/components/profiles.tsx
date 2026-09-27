import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { holdingTime, INTERVAL_LABELS, pct, TIER_OF_INTERVAL } from "../lib/format";
import type { Profile, Tier } from "../lib/types";
import { Badge, Button, InfoTip, Pnl, Segmented } from "./ui";

export function useProfiles() {
  return useQuery({ queryKey: ["profiles"], queryFn: () => api.get<{ tiers: Tier[] }>("/profiles"), staleTime: Infinity });
}

const TIER_LABEL = { rapido: "Rápido", medio: "Médio", lento: "Lento" } as const;

/** Nível do bot, deduzido do tempo do candle. */
export function TierBadge({ interval }: { interval: string }) {
  const tier = TIER_OF_INTERVAL[interval] ?? "lento";
  return <Badge tone={tier === "rapido" ? "warn" : "neutral"}>{TIER_LABEL[tier]}</Badge>;
}

function periodLabel(days: number): string {
  if (days < 60) return `${days} dias`;
  const months = Math.round(days / 30);
  return months === 12 ? "1 ano" : `${months} meses`;
}

function Metric({ label, value, sub, info }: { label: string; value: ReactNode; sub?: string; info?: string }) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-ink-2">
        {label}
        {info && <InfoTip>{info}</InfoTip>}
      </dt>
      <dd className="mt-0.5 font-semibold text-ink tabular">{value}</dd>
      {sub && <dd className="text-muted">{sub}</dd>}
    </div>
  );
}

function ProfileCard({ profile, active, onPick }: { profile: Profile; active: boolean; onPick: () => void }) {
  const s = profile.stats;
  const period = periodLabel(s.period_days);
  return (
    <div className={clsx("rounded-lg border p-3", active ? "border-accent bg-surface-2" : "border-line")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
            {profile.name}
            {profile.recommended && <Badge tone="accent">recomendado</Badge>}
          </div>
          <div className="text-xs text-muted">
            {profile.strategy_name} · candles de {INTERVAL_LABELS[profile.interval]}
          </div>
        </div>
        <Button type="button" size="sm" variant={active ? "primary" : "secondary"} onClick={onPick}>
          {active ? (
            <>
              <Check className="size-3.5" /> Em uso
            </>
          ) : (
            "Usar"
          )}
        </Button>
      </div>
      <p className="mt-2 text-xs text-ink-2">{profile.description}</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 text-xs sm:grid-cols-3">
        <Metric
          label="Resultado típico"
          value={<Pnl value={s.median_return_pct} percent />}
          sub={`em ${period}`}
          info="Mediana dos testes: metade dos pares e períodos foi melhor que isso, metade foi pior. Já descontadas taxas e slippage."
        />
        <Metric label="Casos com lucro" value={`${s.profitable_pct}%`} sub={`de ${s.cases} testes`} info="Em quantos dos testes (pares e períodos diferentes) o perfil terminou com lucro." />
        <Metric label="Cada operação dura" value={`~${holdingTime(s.avg_trade_minutes)}`} sub="em média" />
        <Metric label="Operações" value={`~${s.trades_per_period}`} sub={`em ${period}`} />
        <Metric label="Queda máx. média" value={pct(s.avg_drawdown_pct)} info="Quanto o capital caiu, do pico ao fundo, em média, durante os testes. Mede o quanto você precisa aguentar no caminho." />
        {s.median_return_bnb_pct != null ? (
          <Metric label="Com taxa reduzida" value={<Pnl value={s.median_return_bnb_pct} percent />} info="Mesmo teste com taxa menor (0,075%, como nos níveis VIP da corretora) e slippage menor, como em pares com muita liquidez." />
        ) : (
          <Metric label="Só segurar a moeda" value={pct(s.buy_hold_median_pct, true)} sub="mesmo período" info="Quanto teria rendido só comprar e segurar, nos mesmos testes." />
        )}
      </dl>
    </div>
  );
}

/** Escolha de nível (Rápido/Médio/Lento) e perfil pronto. */
export function ProfilePicker({ selected, onPick }: { selected: string | null; onPick: (profile: Profile, tier: Tier) => void }) {
  const { data } = useProfiles();
  const [tierKey, setTierKey] = useState<Tier["key"]>("lento");
  useEffect(() => {
    const owner = data?.tiers.find((t) => t.profiles.some((p) => p.key === selected));
    if (owner) setTierKey(owner.key);
  }, [data, selected]);
  if (!data) return null;
  const tier = data.tiers.find((t) => t.key === tierKey) ?? data.tiers[0];
  return (
    <div className="space-y-4">
      <Segmented<Tier["key"]>
        value={tier.key}
        onChange={setTierKey}
        options={data.tiers.map((t) => ({ value: t.key, label: `${t.name} · ${t.holding}` }))}
      />
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        <Badge tone={tier.risk === "Alto" ? "warn" : tier.risk === "Baixo" ? "good" : "neutral"}>Risco {tier.risk.toLowerCase()}</Badge>
        <span>{tier.description}</span>
      </div>
      {tier.warning && (
        <div className="flex gap-2 rounded-lg border border-warn/40 px-3 py-2 text-xs text-warn-text">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{tier.warning}</span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {tier.profiles.map((p) => (
          <ProfileCard key={p.key} profile={p} active={selected === p.key} onPick={() => onPick(p, tier)} />
        ))}
      </div>
      <p className="text-xs text-muted">
        Números de backtest com histórico real de 14 pares, já com taxa de 0,1% e slippage, investindo 100% do capital em cada operação. Com valores
        fixos menores por compra, as oscilações da sua carteira são proporcionalmente menores. Resultado passado não garante resultado futuro.
      </p>
    </div>
  );
}
