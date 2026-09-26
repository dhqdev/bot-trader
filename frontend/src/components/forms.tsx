import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
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
            <span className="text-xs text-muted">{i === 0 ? "recomendada" : s.style}</span>
          </div>
          <p className="mt-1 line-clamp-3 text-xs text-ink-2">{s.description}</p>
        </button>
      ))}
    </div>
  );
}

function ParamInput({ param, value, onChange }: { param: Param; value: Params[string]; onChange: (v: Params[string]) => void }) {
  if (param.type === "bool") {
    return <Switch checked={Boolean(value)} onChange={onChange} label={param.label} />;
  }
  if (param.type === "select") {
    return (
      <Field label={param.label} help={param.help}>
        <Select value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {(param.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o.toUpperCase()}
            </option>
          ))}
        </Select>
      </Field>
    );
  }
  return (
    <Field label={param.label} help={param.help || (param.min != null && param.max != null ? `${param.min} a ${param.max}` : undefined)}>
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
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {numeric.map((p) => (
          <ParamInput key={p.name} param={p} value={values[p.name] ?? p.default} onChange={(v) => onChange({ ...values, [p.name]: v })} />
        ))}
      </div>
      {flags.length > 0 && (
        <div className="flex flex-col gap-2.5">
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
  help?: string;
  suffix?: string;
}) {
  return (
    <Field label={suffix ? `${label} (${suffix})` : label} help={help}>
      <Input type="number" value={Number.isFinite(value) ? value : ""} step={step} min={min} onChange={(e) => onChange(Number(e.target.value))} />
    </Field>
  );
}

export function RiskForm({ risk, onChange, quote = "USDT" }: { risk: RiskConfig; onChange: (r: RiskConfig) => void; quote?: string }) {
  const set = <K extends keyof RiskConfig>(k: K, v: RiskConfig[K]) => onChange({ ...risk, [k]: v });
  const tps = risk.take_profits;
  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Tamanho da posição</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Modo">
            <Select value={risk.sizing_mode} onChange={(e) => set("sizing_mode", e.target.value as RiskConfig["sizing_mode"])}>
              <option value="fixed_quote">Valor fixo por compra</option>
              <option value="percent_balance">% do saldo disponível</option>
              <option value="risk_percent">% de risco até o stop</option>
            </Select>
          </Field>
          {risk.sizing_mode === "fixed_quote" && (
            <NumberField label="Valor por compra" suffix={quote} value={risk.order_size_quote} onChange={(v) => set("order_size_quote", v)} step={1} help="Mínimo da Binance ≈ 5 USDT" />
          )}
          {risk.sizing_mode === "percent_balance" && (
            <NumberField label="% do saldo" value={risk.balance_percent} onChange={(v) => set("balance_percent", v)} step={1} />
          )}
          {risk.sizing_mode === "risk_percent" && (
            <NumberField label="Risco por operação" suffix="%" value={risk.risk_percent} onChange={(v) => set("risk_percent", v)} help="Perda máxima se o stop for atingido" />
          )}
          <NumberField label="Limite por posição" suffix={quote} value={risk.max_position_quote} onChange={(v) => set("max_position_quote", v)} step={1} help="0 = sem limite" />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Stop loss</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Tipo">
            <Select value={risk.stop_loss_mode} onChange={(e) => set("stop_loss_mode", e.target.value as RiskConfig["stop_loss_mode"])}>
              <option value="atr">Pela volatilidade (ATR)</option>
              <option value="percent">Percentual fixo</option>
              <option value="none">Sem stop (não recomendado)</option>
            </Select>
          </Field>
          {risk.stop_loss_mode === "atr" && (
            <NumberField label="Distância" suffix="× ATR" value={risk.stop_loss_atr_mult} onChange={(v) => set("stop_loss_atr_mult", v)} help="3 × ATR deixa a tendência respirar" />
          )}
          {risk.stop_loss_mode === "percent" && (
            <NumberField label="Distância" suffix="%" value={risk.stop_loss_pct} onChange={(v) => set("stop_loss_pct", v)} />
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Proteção de lucro</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <NumberField label="Break-even após" suffix="%" value={risk.breakeven_at_pct} onChange={(v) => set("breakeven_at_pct", v)} help="Move o stop para a entrada. 0 = desligado" />
        </div>
        <Switch checked={risk.trailing_enabled} onChange={(v) => set("trailing_enabled", v)} label="Trailing stop (stop que acompanha a alta)" />
        {risk.trailing_enabled && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Tipo">
              <Select value={risk.trailing_mode} onChange={(e) => set("trailing_mode", e.target.value as RiskConfig["trailing_mode"])}>
                <option value="atr">Pela volatilidade (ATR)</option>
                <option value="percent">Percentual</option>
              </Select>
            </Field>
            {risk.trailing_mode === "atr" ? (
              <NumberField label="Distância da máxima" suffix="× ATR" value={risk.trailing_atr_mult} onChange={(v) => set("trailing_atr_mult", v)} />
            ) : (
              <NumberField label="Distância da máxima" suffix="%" value={risk.trailing_pct} onChange={(v) => set("trailing_pct", v)} />
            )}
            <NumberField label="Ativa após lucro de" suffix="%" value={risk.trailing_activation_pct} onChange={(v) => set("trailing_activation_pct", v)} />
          </div>
        )}
        <div className="space-y-2">
          <div className="text-xs font-medium text-ink-2">Alvos parciais (vende parte da posição ao atingir o lucro)</div>
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
            <Button type="button" size="sm" variant="ghost" onClick={() => set("take_profits", [...tps, { pct: (tps.at(-1)?.pct ?? 0) + 5, size_pct: 25 }])}>
              <Plus className="size-4" /> Adicionar alvo
            </Button>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Disciplina</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <NumberField label="Pausa após saída" suffix="candles" value={risk.cooldown_bars} step={1} onChange={(v) => set("cooldown_bars", Math.round(v))} />
          <NumberField label="Perda diária máxima" suffix={quote} value={risk.max_daily_loss_quote} step={1} onChange={(v) => set("max_daily_loss_quote", v)} help="Bloqueia novas compras no dia. 0 = desligado" />
          <NumberField label="Taxa da corretora" suffix="%" value={risk.fee_pct} step={0.01} onChange={(v) => set("fee_pct", v)} help="Binance: 0,1% (0,075% com BNB)" />
        </div>
      </section>
    </div>
  );
}
