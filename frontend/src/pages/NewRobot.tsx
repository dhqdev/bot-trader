import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, ArrowLeft, Check, ChevronDown, Crown, Loader2, RefreshCw, Search, Sparkles, ThumbsDown, Wallet } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { BacktestEquityChart } from "../components/charts";
import { Badge, Button, Card, ErrorBox, Field, Input, Loading, Modal, PageHeader, Pnl, Segmented, Switch } from "../components/ui";
import { api } from "../lib/api";
import { holdingTime, money, num, pct, price } from "../lib/format";
import type { Advice, Bot, CoinInfo, CoinTicker, Credentials, Level, LevelInfo, Mode, RankedRobot, Ranking } from "../lib/types";

type Step = "coin" | "amount" | "level" | "result";
const STEPS: { key: Step; label: string }[] = [
  { key: "coin", label: "Moeda" },
  { key: "amount", label: "Valor" },
  { key: "level", label: "Volatilidade" },
  { key: "result", label: "Robôs" },
];
const QUICK_AMOUNTS = [25, 50, 100, 250, 500, 1000];

function Steps({ step, onGo, done }: { step: Step; onGo: (s: Step) => void; done: Record<Step, boolean> }) {
  const current = STEPS.findIndex((s) => s.key === step);
  return (
    <ol className="mb-5 flex gap-1.5 overflow-x-auto text-xs">
      {STEPS.map((s, i) => (
        <li key={s.key}>
          <button
            type="button"
            disabled={i > current && !done[s.key]}
            onClick={() => onGo(s.key)}
            className={clsx(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-medium whitespace-nowrap transition-colors disabled:cursor-default",
              i === current ? "border-accent bg-surface-2 text-ink" : i < current ? "border-line text-ink-2 hover:text-ink" : "border-line text-muted",
            )}
          >
            <span className={clsx("grid size-4 place-items-center rounded-full text-[10px]", i < current ? "bg-good text-white" : "bg-surface-2 text-ink-2")}>
              {i < current ? <Check className="size-3" /> : i + 1}
            </span>
            {s.label}
          </button>
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------ 1. moeda

function CoinStep({ onPick }: { onPick: (symbol: string) => void }) {
  const coins = useQuery({ queryKey: ["robot-coins"], queryFn: () => api.get<CoinTicker[]>("/robots/coins"), staleTime: 60_000 });
  const symbols = useQuery({
    queryKey: ["symbols", "USDT"],
    queryFn: () => api.get<{ symbol: string; base: string }[]>("/market/symbols?quote=USDT"),
    staleTime: 3_600_000,
  });
  const [query, setQuery] = useState("");
  const typed = query.trim().toUpperCase().replace(/[/-]/g, "");
  const match = symbols.data?.find((s) => s.symbol === typed || s.symbol === `${typed}USDT`);
  return (
    <Card title="Qual criptomoeda o robô vai operar?">
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (match) onPick(match.symbol);
        }}
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar moeda (ex.: SOL, PEPE, TON)" className="pl-9" list="okx-symbols" aria-label="Buscar moeda" />
          <datalist id="okx-symbols">
            {symbols.data?.map((s) => <option key={s.symbol} value={s.base} />)}
          </datalist>
        </div>
        <Button type="submit" variant="primary" disabled={!match}>Escolher</Button>
      </form>
      {coins.isLoading && <Loading label="Buscando as moedas mais negociadas na OKX…" />}
      <ErrorBox error={coins.error} />
      {coins.data && (
        <>
          <p className="mb-2 text-xs text-muted">As mais negociadas na OKX agora:</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {coins.data.map((c) => (
              <button
                key={c.symbol}
                type="button"
                onClick={() => onPick(c.symbol)}
                className="rounded-lg border border-line p-3 text-left transition-colors hover:border-accent hover:bg-surface-2"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-ink">{c.base}</span>
                  <Pnl value={c.change_24h_pct} percent className="text-xs" />
                </div>
                <div className="truncate text-xs text-ink-2">{c.name}</div>
                <div className="mt-1 text-sm text-ink tabular">{price(c.price)}</div>
              </button>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ 2. valor

function AmountStep({ symbol, amount, onAmount, simulated, onSimulated, onNext }: {
  symbol: string;
  amount: number;
  onAmount: (v: number) => void;
  simulated: boolean;
  onSimulated: (v: boolean) => void;
  onNext: () => void;
}) {
  const coin = useQuery({ queryKey: ["robot-coin", symbol], queryFn: () => api.get<CoinInfo>(`/robots/coin/${symbol}`), staleTime: 60_000 });
  const c = coin.data;
  const wallet = c?.wallet;
  const valid = amount >= 5;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
      <Card title="Quanto o robô vai usar?">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) onNext();
          }}
        >
          <Switch checked={simulated} onChange={onSimulated} label={<>Valor simulado <span className="text-ink-2">(dinheiro de mentira)</span></>} />
          <Field
            label={simulated ? "Valor simulado (USDT)" : "Valor por operação (USDT)"}
            help={
              simulated
                ? "O robô opera no mercado real da OKX, com os preços ao vivo, a taxa da sua conta e slippage, mas com esse valor de mentira: não usa o seu saldo."
                : "Cada compra do robô usa esse valor. Ele só compra com USDT e só vende o que ele mesmo comprou."
            }
          >
            <Input type="number" min={5} step={1} value={Number.isFinite(amount) ? amount : ""} onChange={(e) => onAmount(Number(e.target.value))} required autoFocus />
          </Field>
          <div className="flex flex-wrap gap-2">
            {QUICK_AMOUNTS.map((v) => (
              <Button key={v} type="button" size="sm" variant={amount === v ? "primary" : "secondary"} onClick={() => onAmount(v)}>
                {num(v, 0)} USDT
              </Button>
            ))}
            {wallet?.usdt != null && wallet.usdt >= 5 && (
              <Button type="button" size="sm" onClick={() => onAmount(Math.floor(wallet.usdt ?? 0))}>
                Tudo ({num(Math.floor(wallet.usdt), 0)} USDT)
              </Button>
            )}
          </div>
          {!valid && <p className="text-xs text-bad-text">O mínimo é 5 USDT.</p>}
          {!simulated && wallet?.usdt != null && amount > wallet.usdt && (
            <p className="flex gap-1.5 text-xs text-warn-text">
              <AlertTriangle className="size-3.5 shrink-0" /> Na OKX você tem {money(wallet.usdt)} livres: no modo real, o robô só compra se tiver saldo.
            </p>
          )}
          <Button type="submit" variant="primary" disabled={!valid}>Continuar</Button>
        </form>
      </Card>
      <Card title={c ? `${c.base} · ${c.name}` : symbol}>
        {coin.isLoading && <Loading />}
        <ErrorBox error={coin.error} />
        {c && (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-ink-2">Preço</dt><dd className="text-ink tabular">{price(c.price)} USDT</dd></div>
            <div className="flex justify-between"><dt className="text-ink-2">Últimas 24 h</dt><dd><Pnl value={c.change_24h_pct} percent /></dd></div>
            {c.return_30d_pct != null && <div className="flex justify-between"><dt className="text-ink-2">Últimos 30 dias</dt><dd><Pnl value={c.return_30d_pct} percent /></dd></div>}
            {c.daily_volatility_pct != null && (
              <div className="flex justify-between gap-3"><dt className="text-ink-2">Oscila por dia</dt><dd className="text-right text-ink">cerca de {pct(c.daily_volatility_pct, false, 1)}</dd></div>
            )}
            <div className="flex gap-2 border-t border-line pt-3 text-xs text-ink-2">
              <Wallet className="size-4 shrink-0 text-accent" />
              {wallet == null ? (
                <span>Cadastre a chave da OKX em <Link to="/settings" className="text-accent hover:underline">Configurações</Link> para ver seu saldo.</span>
              ) : wallet.error ? (
                <span className="text-warn-text">{wallet.error}</span>
              ) : (
                <span>
                  Na sua OKX: <strong className="text-ink">{money(wallet.usdt)}</strong> livres
                  {wallet.coin ? <> e <strong className="text-ink">{num(wallet.coin, 6)} {c.base}</strong></> : null}.
                </span>
              )}
            </div>
          </dl>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ 3. volatilidade

function LevelStep({ symbol, onPick }: { symbol: string; onPick: (level: Level) => void }) {
  const levels = useQuery({ queryKey: ["robot-levels"], queryFn: () => api.get<LevelInfo[]>("/robots/levels"), staleTime: Infinity });
  const tone: Record<Level, string> = { baixa: "text-good-text", media: "text-warn-text", alta: "text-bad-text" };
  return (
    <Card title="Qual volatilidade você aceita?">
      <p className="-mt-1 mb-4 text-sm text-ink-2">
        Define quanto tempo cada operação dura e quanto o resultado oscila. Ao escolher, o sistema testa todos os robôs desse grupo em {symbol.replace(/USDT$/, "")}.
      </p>
      {levels.isLoading && <Loading />}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {levels.data?.map((l) => (
          <button key={l.key} type="button" onClick={() => onPick(l.key)} className="rounded-xl border border-line p-4 text-left transition-colors hover:border-accent hover:bg-surface-2">
            <div className={clsx("text-lg font-semibold", tone[l.key])}>{l.label}</div>
            <div className="mt-1 text-xs text-muted">Cada operação dura {l.holding}</div>
            <p className="mt-2 text-sm text-ink-2">{l.description}</p>
          </button>
        ))}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ 4. ranking

function hours(h: number): string {
  return h > 0 ? holdingTime(h * 60) : "–";
}

function RobotRow({ r, best, worst, recommended, amount, onUse }: {
  r: RankedRobot;
  best: boolean;
  worst: boolean;
  recommended: boolean;
  amount: number;
  onUse: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li className={clsx("rounded-lg border p-3", recommended ? "border-accent" : "border-line")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted tabular">{r.position}º</span>
            <span className="font-semibold text-ink">{r.name}</span>
            {recommended && <Badge tone="accent"><Sparkles className="size-3" />Recomendado</Badge>}
            {best && !recommended && <Badge tone="good"><Crown className="size-3" />Melhor</Badge>}
            {worst && <Badge tone="bad"><ThumbsDown className="size-3" />Pior</Badge>}
            {!r.eligible && <Badge>Poucas operações</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
            <span>Recente: <Pnl value={r.recent_return_pct} percent /></span>
            <span>Queda máx.: <span className="text-ink tabular">{pct(r.drawdown_pct, false, 1)}</span></span>
            <span>{r.trades} operações · acerto {pct(r.win_rate_pct, false, 0)}</span>
            <span>dura ~{hours(r.avg_trade_hours)}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <Pnl value={r.return_pct} percent className="text-base font-semibold" />
            <div className="text-xs text-muted tabular">{num(amount, 0)} → {num(r.final_usdt, 2)} USDT</div>
          </div>
          <Button size="sm" variant={recommended || best ? "primary" : "secondary"} onClick={onUse}>Usar</Button>
        </div>
      </div>
      <button type="button" className="mt-2 flex items-center gap-1 text-xs text-accent" onClick={() => setOpen(!open)} aria-expanded={open}>
        <ChevronDown className={clsx("size-3.5 transition-transform", open && "rotate-180")} /> {open ? "Esconder" : "Ver"} como ele se saiu
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-ink-2">{r.description}</p>
          <BacktestEquityChart data={r.curve} height={200} />
        </div>
      )}
    </li>
  );
}

function AdviceCard({ advice, loading, robots, onUse }: { advice: Advice | undefined; loading: boolean; robots: RankedRobot[]; onUse: (r: RankedRobot) => void }) {
  if (loading && !advice) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin" /> A IA está analisando o resultado…</div>
      </Card>
    );
  }
  if (!advice) return null;
  const robot = robots.find((r) => r.key === advice.recommended_key);
  const conf = { baixa: "Confiança baixa", media: "Confiança média", alta: "Confiança alta" }[advice.confidence];
  return (
    <Card className="border-accent/60">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <Sparkles className="size-4 text-accent" />
          {advice.source === "ai" ? `Recomendação da IA (${advice.provider ?? "IA"})` : "Recomendação do sistema"}
          <Badge>{conf}</Badge>
        </div>
        <p className="text-base font-semibold text-ink">{advice.headline}</p>
        <p className="text-sm text-ink-2">{advice.why}</p>
        <p className="flex gap-1.5 text-sm text-warn-text"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{advice.watch_out}</p>
        {advice.source !== "ai" && (
          <p className="text-xs text-muted">
            {advice.note ?? "Cadastre uma chave de IA (Claude ou GPT) em Configurações para a IA analisar o ranking junto com as notícias e o humor do mercado."}
          </p>
        )}
        {robot && <Button variant="primary" onClick={() => onUse(robot)}><Check className="size-4" />Usar o {robot.name}</Button>}
      </div>
    </Card>
  );
}

function CreateModal({ robot, symbol, level, amount, initialMode, onClose }: {
  robot: RankedRobot | null;
  symbol: string;
  level: Level;
  amount: number;
  initialMode: Mode;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const creds = useQuery({ queryKey: ["credentials"], queryFn: () => api.get<Credentials>("/settings/credentials") });
  const base = symbol.replace(/USDT$/, "");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<Mode>(initialMode);
  const [start, setStart] = useState(true);
  const [ack, setAck] = useState(false);
  const create = useMutation({
    mutationFn: () => api.post<Bot>("/robots/create", { symbol, level, amount, robot_key: robot!.key, mode, start, name: name || `${base} · ${robot!.name}` }),
    onSuccess: (bot) => {
      for (const k of ["bots", "dashboard", "system"]) qc.invalidateQueries({ queryKey: [k] });
      navigate(`/bots/${bot.id}`);
    },
  });
  const noKeys = mode === "live" && creds.data && !creds.data.okx.configured;
  const needAck = mode === "live" && level === "alta";
  return (
    <Modal open={robot != null} onClose={onClose} title={robot ? `Usar o ${robot.name} em ${base}` : ""}>
      {robot && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome">
            <Input value={name} placeholder={`${base} · ${robot.name}`} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="space-y-2">
            <Segmented<Mode>
              value={mode}
              onChange={setMode}
              options={[
                { value: "paper", label: "Simulado" },
                { value: "live", label: "Dinheiro real" },
              ]}
            />
            <p className="text-xs text-ink-2">
              {mode === "paper"
                ? `Simulação com ${money(amount)} de mentira: ordens fictícias com os preços reais da OKX, a taxa da sua conta e slippage. Bom para acompanhar antes de arriscar.`
                : `Ordens reais na OKX: cada compra usa ${money(amount)}.`}
            </p>
            {noKeys && (
              <p className="flex gap-1.5 text-xs text-warn-text">
                <AlertTriangle className="size-3.5 shrink-0" /> Cadastre a chave da OKX em <Link to="/settings" className="underline">Configurações</Link> para operar com dinheiro real.
              </p>
            )}
          </div>
          {needAck && (
            <label className="flex gap-3 rounded-lg border border-warn/40 p-3 text-sm text-ink-2">
              <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-[var(--warn)]" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>Entendo que, nos testes, os robôs de volatilidade alta perderam dinheiro por causa das taxas, e quero usar mesmo assim com um valor que aceito perder.</span>
            </label>
          )}
          <Switch checked={start} onChange={setStart} label="Ligar o robô agora" />
          <ErrorBox error={create.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button type="submit" variant="primary" loading={create.isPending} disabled={Boolean(noKeys) || (needAck && !ack)}>Criar robô</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function ResultStep({ symbol, level, amount, mode }: { symbol: string; level: Level; amount: number; mode: Mode }) {
  const qc = useQueryClient();
  const base = symbol.replace(/USDT$/, "");
  const [chosen, setChosen] = useState<RankedRobot | null>(null);
  const rankKey = ["robot-rank", symbol, level, amount];
  const rank = useQuery({
    queryKey: rankKey,
    queryFn: () => api.post<Ranking>("/robots/rank", { symbol, level, amount }),
    staleTime: 10 * 60_000,
    retry: false,
  });
  const retest = useMutation({
    mutationFn: () => api.post<Ranking>("/robots/rank", { symbol, level, amount, refresh: true }),
    onSuccess: (data) => qc.setQueryData(rankKey, data),
  });
  const advice = useQuery({
    queryKey: ["robot-advice", symbol, level, amount, rank.data?.tested_at],
    queryFn: () => api.post<Advice>("/robots/advice", { symbol, level, amount }),
    enabled: Boolean(rank.data),
    staleTime: 30 * 60_000,
    retry: false,
  });
  const robots = rank.data?.robots ?? [];
  const bh = robots[0];
  const recommended = advice.data?.recommended_key;
  if (rank.isLoading) {
    return (
      <Card>
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <Loader2 className="size-8 animate-spin text-accent" />
          <p className="font-medium text-ink">Testando todos os robôs em {base} no histórico real da OKX…</p>
          <p className="max-w-md text-sm text-ink-2">Na primeira vez de cada moeda o sistema baixa o histórico, o que pode levar até 1 minuto. Depois fica guardado e é instantâneo.</p>
        </div>
      </Card>
    );
  }
  if (rank.error) {
    return (
      <Card>
        <ErrorBox error={rank.error} />
        <Button className="mt-3" onClick={() => rank.refetch()}><RefreshCw className="size-4" />Tentar de novo</Button>
      </Card>
    );
  }
  if (!rank.data) return null;
  return (
    <div className="space-y-4">
      <AdviceCard advice={advice.data} loading={advice.isLoading} robots={robots} onUse={setChosen} />
      <Card
        title={`${robots.length} robôs testados em ${base} · volatilidade ${rank.data.level_label.toLowerCase()} · últimos ${rank.data.days} dias`}
        action={
          <Button size="sm" variant="ghost" onClick={() => retest.mutate()} loading={retest.isPending}>
            <RefreshCw className="size-3.5" />Testar de novo
          </Button>
        }
      >
        {bh && (
          <p className="mb-3 rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink-2">
            Para comparar: só comprar {base} e segurar teria dado <Pnl value={bh.buy_hold_pct} percent /> ({num(amount, 0)} → {num(bh.buy_hold_final_usdt, 2)} USDT).
            Os robôs ficam em USDT parte do tempo, então costumam perder menos nas quedas e ganhar menos nas altas fortes.
          </p>
        )}
        <ul className="space-y-2">
          {robots.map((r) => (
            <RobotRow key={r.key} r={r} amount={amount} best={r.key === rank.data.best} worst={r.key === rank.data.worst} recommended={r.key === recommended} onUse={() => setChosen(r)} />
          ))}
        </ul>
        <p className="mt-3 text-xs text-muted">
          Ranking: resultado no período todo e no período recente, descontando metade da maior queda. Já inclui slippage e a taxa de{" "}
          {pct(rank.data.fee_pct, false, 2)} por ordem (a da sua conta na OKX, se a chave estiver cadastrada). Resultado passado não garante o futuro.
        </p>
      </Card>
      <CreateModal robot={chosen} symbol={symbol} level={level} amount={amount} initialMode={mode} onClose={() => setChosen(null)} />
    </div>
  );
}

// ------------------------------------------------------------------ página

export function NewRobotPage() {
  const [step, setStep] = useState<Step>("coin");
  const [symbol, setSymbol] = useState("");
  const [amount, setAmount] = useState(100);
  const [simulated, setSimulated] = useState(true);
  const [level, setLevel] = useState<Level | null>(null);
  const done = useMemo(() => ({ coin: Boolean(symbol), amount: Boolean(symbol) && amount >= 5, level: Boolean(level), result: Boolean(level) }), [symbol, amount, level]);
  const base = symbol.replace(/USDT$/, "");
  return (
    <>
      <PageHeader
        title="Novo robô"
        subtitle="Escolha a moeda, o valor e a volatilidade. O sistema testa todos os robôs e mostra do melhor ao pior."
        actions={
          <Link to="/bots" className="flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
            <ArrowLeft className="size-4" /> Robôs
          </Link>
        }
      />
      <Steps step={step} onGo={setStep} done={done} />
      {symbol && step !== "coin" && (
        <p className="-mt-2 mb-4 text-sm text-ink-2">
          {base}
          {step !== "amount" && <> · {money(amount)} {simulated ? "simulados" : "por operação"}</>}
          {step === "result" && level && <> · volatilidade {level === "media" ? "média" : level}</>}
        </p>
      )}
      {step === "coin" && (
        <CoinStep
          onPick={(s) => {
            setSymbol(s);
            setStep("amount");
          }}
        />
      )}
      {step === "amount" && symbol && (
        <AmountStep symbol={symbol} amount={amount} onAmount={setAmount} simulated={simulated} onSimulated={setSimulated} onNext={() => setStep("level")} />
      )}
      {step === "level" && symbol && (
        <LevelStep
          symbol={symbol}
          onPick={(l) => {
            setLevel(l);
            setStep("result");
          }}
        />
      )}
      {step === "result" && symbol && level && <ResultStep symbol={symbol} level={level} amount={amount} mode={simulated ? "paper" : "live"} />}
    </>
  );
}
