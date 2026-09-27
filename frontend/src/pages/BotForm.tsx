import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { defaultParams, HELP, INTERVALS, ParamsForm, RiskForm, StrategyPicker, useStrategies, useSymbols, type Params } from "../components/forms";
import { ProfilePicker } from "../components/profiles";
import { Button, Card, ErrorBox, Field, Input, Loading, PageHeader, Segmented, Select } from "../components/ui";
import { api } from "../lib/api";
import { INTERVAL_LABELS, TIER_OF_INTERVAL } from "../lib/format";
import type { Bot, Credentials, Mode, Profile, RiskConfig, Tier } from "../lib/types";

export interface BotDraft {
  name?: string;
  symbol: string;
  interval: string;
  strategy: string;
  params: Params;
  risk: RiskConfig;
  profile?: string | null;
}

/** Aplica as regras de risco do perfil, preservando tamanho da posição, limites e taxa escolhidos pelo usuário. */
export function mergeProfileRisk(current: RiskConfig, profile: Profile): RiskConfig {
  return {
    ...profile.risk,
    sizing_mode: current.sizing_mode,
    order_size_quote: current.order_size_quote,
    balance_percent: current.balance_percent,
    risk_percent: current.risk_percent,
    max_position_quote: current.max_position_quote,
    max_daily_loss_quote: current.max_daily_loss_quote,
    fee_pct: current.fee_pct,
  };
}

export function BotFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const location = useLocation();
  const draft = (location.state as { draft?: BotDraft } | null)?.draft;
  const qc = useQueryClient();
  const strategies = useStrategies();
  const creds = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  const existing = useQuery({ queryKey: ["bot", id], queryFn: () => api.get<Bot>(`/bots/${id}`), enabled: editing });

  const symbols = useSymbols();
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setTimeframe] = useState("4h");
  const [mode, setMode] = useState<Mode>("paper");
  const [paperBalance, setPaperBalance] = useState(1000);
  const [strategy, setStrategy] = useState("");
  const [params, setParams] = useState<Params>({});
  const [risk, setRisk] = useState<RiskConfig | null>(null);
  const [profileKey, setProfileKey] = useState<string | null>(null);
  const [ackFast, setAckFast] = useState(false);
  const [ready, setReady] = useState(false);

  // preenche o formulário: bot existente, rascunho vindo do laboratório ou padrões
  useEffect(() => {
    if (ready || !strategies.data) return;
    if (editing) {
      if (!existing.data) return;
      const b = existing.data;
      setName(b.name);
      setSymbol(b.symbol);
      setTimeframe(b.interval);
      setMode(b.mode);
      setStrategy(b.strategy);
      setParams(b.strategy_params);
      setRisk(b.risk);
    } else if (draft) {
      setName(draft.name ?? `${draft.symbol} ${draft.interval}`);
      setSymbol(draft.symbol);
      setTimeframe(draft.interval);
      setStrategy(draft.strategy);
      setParams(draft.params);
      setRisk({ ...draft.risk, sizing_mode: "fixed_quote" });
      setProfileKey(draft.profile ?? null);
    } else {
      const key = strategies.data.default;
      setTimeframe(strategies.data.default_interval);
      setStrategy(key);
      setParams(defaultParams(strategies.data.strategies.find((s) => s.key === key)));
      setRisk(strategies.data.default_risk);
      setProfileKey("lento_squeeze_4h");
    }
    setReady(true);
  }, [ready, strategies.data, existing.data, editing, draft]);

  const save = useMutation({
    mutationFn: () => {
      const body = { name: name || `${symbol} ${interval}`, interval, strategy, strategy_params: params, risk, mode };
      return editing
        ? api.put<Bot>(`/bots/${id}`, body)
        : api.post<Bot>("/bots", { ...body, symbol, paper_initial_balance: paperBalance });
    },
    onSuccess: (bot) => {
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["bot", String(bot.id)] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/bots/${bot.id}`);
    },
  });

  if (!ready || !risk) return <Loading />;
  const strategyInfo = strategies.data!.strategies.find((s) => s.key === strategy);
  const quote = symbol.endsWith("USDT") ? "USDT" : "";
  const liveWithoutKeys = mode === "live" && creds.data && !creds.data.okx.configured;
  const fastLive = mode === "live" && TIER_OF_INTERVAL[interval] === "rapido";
  const blocked = Boolean(liveWithoutKeys) || (fastLive && !ackFast);

  function applyProfile(profile: Profile, tier: Tier) {
    setProfileKey(profile.key);
    setTimeframe(profile.interval);
    setStrategy(profile.strategy);
    setParams(profile.params);
    setRisk((current) => mergeProfileRisk(current ?? profile.risk, profile));
    if (tier.key === "rapido" && !editing) setMode("paper"); // nível experimental começa no simulado
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!blocked) save.mutate();
  }

  function openLab() {
    navigate("/lab", { state: { draft: { symbol, interval, strategy, params, risk: risk!, profile: profileKey } satisfies BotDraft } });
  }

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={editing ? `Editar ${existing.data?.name ?? "bot"}` : "Novo bot"}
        subtitle={editing ? "As mudanças valem a partir do próximo ciclo." : "Escolha o nível, teste no laboratório e só então ligue."}
        actions={
          <>
            <Button type="button" onClick={openLab}><FlaskConical className="size-4" />Testar no laboratório</Button>
            <Button type="submit" variant="primary" loading={save.isPending} disabled={blocked}>
              {editing ? "Salvar" : "Criar bot"}
            </Button>
          </>
        }
      />
      <div className="space-y-4">
        <Card title="Nível de risco e prazo">
          <p className="-mt-1 mb-4 text-xs text-ink-2">
            Perfis prontos, testados no histórico: <strong className="text-ink">Rápido</strong> (operações de minutos),{" "}
            <strong className="text-ink">Médio</strong> (horas) ou <strong className="text-ink">Lento</strong> (dias). Ao escolher, o tempo do candle, a
            estratégia e o stop são preenchidos; o tamanho das compras continua o seu. Você pode ajustar tudo depois.
          </p>
          <ProfilePicker selected={profileKey} onPick={applyProfile} />
        </Card>

        <Card title="Básico">
          <div className="grid grid-cols-1 gap-x-3 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Nome" help="Só para você identificar o bot.">
              <Input value={name} placeholder={`${symbol} ${interval}`} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Par" help={editing ? "O par não pode ser alterado depois de criado." : HELP.symbol}>
              <Input
                list="symbols"
                value={symbol}
                disabled={editing}
                onChange={(e) => setSymbol(e.target.value.toUpperCase().replace("/", ""))}
                required
              />
              <datalist id="symbols">
                {symbols.data?.map((s) => <option key={s.symbol} value={s.symbol} />)}
              </datalist>
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
                  <option key={i} value={i}>{INTERVAL_LABELS[i]}{i === strategies.data!.default_interval ? " (recomendado)" : ""}</option>
                ))}
              </Select>
            </Field>
            {!editing && mode === "paper" && (
              <Field label="Saldo simulado (USDT)" help="Dinheiro fictício com que o bot começa no modo simulado.">
                <Input type="number" min={10} value={paperBalance} onChange={(e) => setPaperBalance(Number(e.target.value))} />
              </Field>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Segmented<Mode>
              value={mode}
              onChange={setMode}
              options={[
                { value: "paper", label: "Simulado" },
                { value: "live", label: "Real (dinheiro de verdade)" },
              ]}
            />
            {mode === "paper" && <span className="text-xs text-ink-2">Ordens fictícias com preços reais da OKX, taxa e slippage. Ideal para testar sem risco.</span>}
            {mode === "live" && (
              <span className="flex items-center gap-1.5 text-xs text-warn-text">
                <AlertTriangle className="size-3.5" />
                {liveWithoutKeys ? "Cadastre as chaves da OKX em Configurações." : "Ordens reais serão enviadas à OKX."}
              </span>
            )}
          </div>
          {fastLive && (
            <label className="mt-4 flex gap-3 rounded-lg border border-warn/40 p-3 text-sm text-ink-2">
              <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-[var(--warn)]" checked={ackFast} onChange={(e) => setAckFast(e.target.checked)} />
              <span>
                <strong className="text-warn-text">Nível rápido com dinheiro real.</strong> Nos testes, todas as estratégias de minutos perderam dinheiro depois das
                taxas. Entendo o risco e quero operar mesmo assim, com um valor que aceito perder.
              </span>
            </label>
          )}
        </Card>

        <Card title="Estratégia">
          <p className="-mt-1 mb-3 text-xs text-ink-2">A estratégia decide quando comprar e quando vender. Estão em ordem de desempenho nos testes; a primeira é a recomendada.</p>
          <StrategyPicker
            strategies={strategies.data!.strategies}
            value={strategy}
            onChange={(key) => {
              setStrategy(key);
              setParams(defaultParams(strategies.data!.strategies.find((s) => s.key === key)));
              setProfileKey(null);
            }}
          />
          {strategyInfo && (
            <div className="mt-5 border-t border-line pt-4">
              <p className="mb-4 text-sm text-ink-2">{strategyInfo.description}</p>
              <ParamsForm strategy={strategyInfo} values={params} onChange={setParams} />
            </div>
          )}
        </Card>

        <Card title="Gerenciamento de risco">
          <p className="-mt-1 mb-4 text-xs text-ink-2">Quanto investir em cada compra e como limitar perdas. Os padrões foram os que deram melhor resultado nos testes.</p>
          <RiskForm risk={risk} onChange={setRisk} quote={quote || "USDT"} />
        </Card>
        <ErrorBox error={save.error} />
      </div>
    </form>
  );
}
