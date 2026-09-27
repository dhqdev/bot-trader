import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { num } from "../lib/format";
import type { Param, RiskConfig, StrategiesResponse, StrategyInfo } from "../lib/types";
import { Button, Field, Input, Select, Switch } from "./ui";

export function useStrategies() {
  return useQuery({ queryKey: ["strategies"], queryFn: () => api.get<StrategiesResponse>("/strategies"), staleTime: Infinity });
}

export function useSymbols() {
  return useQuery({
    queryKey: ["symbols", "USDT"],
    queryFn: () => api.get<{ symbol: string; base: string; quote: string }[]>("/market/symbols?quote=USDT"),
    staleTime: 3_600_000,
  });
}

export const INTERVALS = ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"];

export type Params = Record<string, number | boolean | string>;

export function defaultParams(s: StrategyInfo | undefined): Params {
  return Object.fromEntries((s?.params ?? []).map((p) => [p.name, p.default]));
}

// textos de ajuda compartilhados entre o laboratório e o formulário do bot
export const HELP = {
  symbol: "Moeda que será comprada e vendida, cotada em dólar (USDT). Ex.: BTCUSDT = Bitcoin, SOLUSDT = Solana.",
  interval:
    "Cada candle resume o preço nesse intervalo, e a estratégia decide a cada candle fechado. 5-15 min = operações de minutos (nível Rápido, que perdeu nos testes por causa das taxas); 1-2 h = operações de horas (Médio); 4 h e 1 dia = operações de dias (Lento, o melhor resultado).",
};

export function StrategyPicker({ strategies, value, onChange }: { strategies: StrategyInfo[]; value: string; onChange: (key: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {strategies.map((s, i) => (
        <button
          key={s.key}
          type="button"
          onClick={() => onChange(s.key)}
          className={clsx(
            "rounded-lg border p-3 text-left transition-colors",
            value === s.key ? "border-accent bg-surface-2" : "border-line hover:bg-surface-2",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-ink">{s.name}</span>
            <span className={clsx("shrink-0 text-xs", i === 0 ? "text-accent" : "text-muted")}>{i === 0 ? "recomendada" : s.style}</span>
          </div>
          <p className="mt-1 line-clamp-3 text-xs text-ink-2">{s.description}</p>
        </button>
      ))}
    </div>
  );
}

function rangeText(p: Param): string | null {
  if (p.min == null || p.max == null) return null;
  return `Aceita de ${num(p.min)} a ${num(p.max)}. Padrão: ${num(Number(p.default))}.`;
}

function ParamInput({ param, value, onChange }: { param: Param; value: Params[string]; onChange: (v: Params[string]) => void }) {
  if (param.type === "bool") {
    return (
      <div>
        <Switch checked={Boolean(value)} onChange={onChange} label={param.label} />
        {param.help && <p className="mt-1 ml-11.5 text-xs text-muted">{param.help}</p>}
      </div>
    );
  }
  if (param.type === "select") {
    return (
      <Field label={param.label} help={param.help}>
        <Select value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {(param.options ?? []).map((o, i) => (
            <option key={o} value={o}>
              {param.labels?.[i] ?? o.toUpperCase()}
            </option>
          ))}
        </Select>
      </Field>
    );
  }
  const range = rangeText(param);
  return (
    <Field
      label={param.label}
      help={
        <>
          {param.help}
          {range && <span className="block text-muted/80">{range}</span>}
        </>
      }
    >
      <Input
        type="number"
        value={value as number}
        min={param.min ?? undefined}
        max={param.max ?? undefined}
        step={param.step ?? (param.type === "int" ? 1 : 0.1)}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    </Field>
  );
}

export function ParamsForm({ strategy, values, onChange }: { strategy: StrategyInfo; values: Params; onChange: (v: Params) => void }) {
  const numeric = strategy.params.filter((p) => p.type !== "bool");
  const flags = strategy.params.filter((p) => p.type === "bool");
  return (
    <div className="space-y-4">
      <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs text-ink-2">
        Os valores já vêm com a configuração que teve o melhor resultado nos testes. Para experimentar, mude <strong className="text-ink">um parâmetro de cada vez</strong> e compare o backtest com o anterior. Mudar vários juntos esconde o que ajudou e o que atrapalhou.
      </p>
      <div className="grid grid-cols-1 gap-x-3 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        {numeric.map((p) => (
          <ParamInput key={p.name} param={p} value={values[p.name] ?? p.default} onChange={(v) => onChange({ ...values, [p.name]: v })} />
        ))}
      </div>
      {flags.length > 0 && (
        <div className="flex flex-col gap-3">
          {flags.map((p) => (
            <ParamInput key={p.name} param={p} value={values[p.name] ?? p.default} onChange={(v) => onChange({ ...values, [p.name]: v })} />
          ))}
        </div>
      )}
      <button type="button" className="text-xs text-accent hover:underline" onClick={() => onChange(defaultParams(strategy))}>
        Restaurar padrões
      </button>
    </div>
  );
}

function NumberField({ label, value, onChange, step = 0.1, min = 0, help, suffix }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  help?: ReactNode;
  suffix?: string;
}) {
  return (
    <Field label={suffix ? `${label} (${suffix})` : label} help={help}>
      <Input type="number" value={Number.isFinite(value) ? value : ""} step={step} min={min} onChange={(e) => onChange(Number(e.target.value))} />
    </Field>
  );
}

function Section({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">{title}</h3>
        <p className="mt-1 text-xs text-ink-2">{intro}</p>
      </div>
      {children}
    </section>
  );
}

export function RiskForm({ risk, onChange, quote = "USDT", lab = false }: { risk: RiskConfig; onChange: (r: RiskConfig) => void; quote?: string; lab?: boolean }) {
  const set = <K extends keyof RiskConfig>(k: K, v: RiskConfig[K]) => onChange({ ...risk, [k]: v });
  const tps = risk.take_profits;
  return (
    <div className="space-y-7">
      <Section
        title="Tamanho da posição"
        intro={
          lab
            ? "Quanto do capital cada compra usa. No laboratório o padrão é 100% do saldo, para o retorno refletir só a estratégia."
            : "Quanto dinheiro cada compra usa. Comece pequeno no modo real."
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field
            label="Modo"
            help={
              risk.sizing_mode === "fixed_quote"
                ? "Sempre compra o mesmo valor."
                : risk.sizing_mode === "percent_balance"
                  ? "Usa uma fração do saldo livre no momento da compra."
                  : "Calcula o tamanho para que, se o stop for atingido, a perda seja no máximo X% do patrimônio."
            }
          >
            <Select value={risk.sizing_mode} onChange={(e) => set("sizing_mode", e.target.value as RiskConfig["sizing_mode"])}>
              <option value="fixed_quote">Valor fixo por compra</option>
              <option value="percent_balance">% do saldo disponível</option>
              <option value="risk_percent">% de risco até o stop</option>
            </Select>
          </Field>
          {risk.sizing_mode === "fixed_quote" && (
            <NumberField label="Valor por compra" suffix={quote} value={risk.order_size_quote} onChange={(v) => set("order_size_quote", v)} step={1} help="Quanto cada compra gasta. A Binance recusa ordens abaixo de ~5 USDT." />
          )}
          {risk.sizing_mode === "percent_balance" && (
            <NumberField label="% do saldo" value={risk.balance_percent} onChange={(v) => set("balance_percent", v)} step={1} help="Ex.: 25 = cada compra usa um quarto do saldo livre." />
          )}
          {risk.sizing_mode === "risk_percent" && (
            <NumberField label="Risco por operação" suffix="%" value={risk.risk_percent} onChange={(v) => set("risk_percent", v)} help="1% é o limite usado por muitos traders profissionais. Exige stop loss ligado." />
          )}
          <NumberField label="Limite por posição" suffix={quote} value={risk.max_position_quote} onChange={(v) => set("max_position_quote", v)} step={1} help="Teto de segurança para uma única compra. 0 = sem limite." />
        </div>
      </Section>

      <Section title="Stop loss" intro="Vende automaticamente se o preço cair até certo ponto, para limitar o prejuízo de uma operação. É conferido a cada ~15 segundos, não só no fechamento do candle.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Tipo" help="ATR é a variação média de um candle: o stop fica mais longe em moedas agitadas e mais perto nas calmas, se adaptando a cada ativo.">
            <Select value={risk.stop_loss_mode} onChange={(e) => set("stop_loss_mode", e.target.value as RiskConfig["stop_loss_mode"])}>
              <option value="atr">Pela volatilidade (ATR)</option>
              <option value="percent">Percentual fixo</option>
              <option value="none">Sem stop (não recomendado)</option>
            </Select>
          </Field>
          {risk.stop_loss_mode === "atr" && (
            <NumberField label="Distância" suffix="× ATR" value={risk.stop_loss_atr_mult} onChange={(v) => set("stop_loss_atr_mult", v)} help="3 = três vezes a variação média de um candle abaixo da compra (mínimo 0,5%). Stops curtos demais são atingidos pelo ruído normal." />
          )}
          {risk.stop_loss_mode === "percent" && (
            <NumberField label="Distância" suffix="%" value={risk.stop_loss_pct} onChange={(v) => set("stop_loss_pct", v)} help="Vende se o preço cair esta % abaixo do preço de compra." />
          )}
        </div>
      </Section>

      <Section title="Proteção de lucro (opcional)" intro="Tudo desligado por padrão: nos testes, proteger o lucro cedo cortou as tendências que mais rendiam. Ligue se preferir um resultado mais estável, mesmo que menor.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NumberField label="Break-even após" suffix="% de lucro" value={risk.breakeven_at_pct} onChange={(v) => set("breakeven_at_pct", v)} help="Ao atingir esse lucro, o stop sobe para o preço de compra (+ taxas) e a operação não vira mais prejuízo. 0 = desligado." />
        </div>
        <div>
          <Switch checked={risk.trailing_enabled} onChange={(v) => set("trailing_enabled", v)} label="Trailing stop (stop que sobe junto com o preço)" />
          <p className="mt-1 ml-11.5 text-xs text-muted">Acompanha a máxima desde a compra e vende se o preço devolver uma parte da alta.</p>
        </div>
        {risk.trailing_enabled && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Tipo" help="Distância fixa em % ou adaptada à volatilidade (ATR).">
              <Select value={risk.trailing_mode} onChange={(e) => set("trailing_mode", e.target.value as RiskConfig["trailing_mode"])}>
                <option value="atr">Pela volatilidade (ATR)</option>
                <option value="percent">Percentual</option>
              </Select>
            </Field>
            {risk.trailing_mode === "atr" ? (
              <NumberField label="Distância da máxima" suffix="× ATR" value={risk.trailing_atr_mult} onChange={(v) => set("trailing_atr_mult", v)} help="Quanto o preço pode recuar da máxima antes de vender." />
            ) : (
              <NumberField label="Distância da máxima" suffix="%" value={risk.trailing_pct} onChange={(v) => set("trailing_pct", v)} help="Ex.: 5 = vende se cair 5% a partir da máxima." />
            )}
            <NumberField label="Começa a seguir após" suffix="% de lucro" value={risk.trailing_activation_pct} onChange={(v) => set("trailing_activation_pct", v)} help="Antes disso vale só o stop loss normal." />
          </div>
        )}
        <div className="space-y-2">
          <div className="text-xs font-medium text-ink-2">Alvos parciais</div>
          <p className="text-xs text-muted">Vende uma parte da posição quando o lucro chega em X%. O restante segue até o sinal de saída ou o stop.</p>
          {tps.map((tp, i) => (
            <div key={i} className="flex items-end gap-2">
              <NumberField label="Lucro" suffix="%" value={tp.pct} onChange={(v) => set("take_profits", tps.map((t, j) => (j === i ? { ...t, pct: v } : t)))} />
              <NumberField label="Vender" suffix="% da posição" value={tp.size_pct} step={5} onChange={(v) => set("take_profits", tps.map((t, j) => (j === i ? { ...t, size_pct: v } : t)))} />
              <Button type="button" variant="ghost" size="sm" className="mb-0.5" onClick={() => set("take_profits", tps.filter((_, j) => j !== i))} aria-label="Remover alvo">
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          {tps.length < 5 && (
            <Button type="button" size="sm" variant="ghost" onClick={() => set("take_profits", [...tps, { pct: (tps.at(-1)?.pct ?? 5) + 5, size_pct: 25 }])}>
              <Plus className="size-4" /> Adicionar alvo
            </Button>
          )}
        </div>
      </Section>

      <Section title="Disciplina" intro="Regras que evitam excessos depois de perdas ou de saídas.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NumberField label="Pausa após vender" suffix="candles" value={risk.cooldown_bars} step={1} onChange={(v) => set("cooldown_bars", Math.round(v))} help="Espera N candles antes de comprar de novo, para não reentrar no mesmo movimento que acabou de sair." />
          <NumberField label="Perda diária máxima" suffix={quote} value={risk.max_daily_loss_quote} step={1} onChange={(v) => set("max_daily_loss_quote", v)} help="Se as operações fechadas no dia somarem essa perda, não compra mais até o dia seguinte (horário UTC). 0 = desligado." />
          <NumberField label="Taxa da corretora" suffix="% por ordem" value={risk.fee_pct} step={0.01} onChange={(v) => set("fee_pct", v)} help="Descontada de cada compra e venda no resultado. Binance: 0,1% (0,075% pagando a taxa com BNB)." />
        </div>
      </Section>
    </div>
  );
}
