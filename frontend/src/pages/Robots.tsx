import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot as BotIcon, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ModeBadge, StatusBadge, VolatilityBadge } from "../components/bot";
import { Button, Card, Confirm, Empty, ErrorBox, Loading, PageHeader, Pnl, Switch } from "../components/ui";
import { api } from "../lib/api";
import { duration, money, pct, timeAgo } from "../lib/format";
import type { Bot } from "../lib/types";

function RobotCard({ bot }: { bot: Bot }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<"start" | "stop" | null>(null);
  const toggle = useMutation({
    mutationFn: (action: "start" | "stop") => api.post<Bot>(`/bots/${bot.id}/${action}`),
    onSuccess: () => {
      setConfirm(null);
      for (const k of ["bots", "dashboard", "system"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
  const on = bot.status === "running";
  const pos = bot.position;
  const onToggle = (next: boolean) => {
    // ligar em dinheiro real e desligar com posição aberta pedem confirmação
    if (next && bot.mode === "live") setConfirm("start");
    else if (!next && pos) setConfirm("stop");
    else toggle.mutate(next ? "start" : "stop");
  };
  return (
    <Card className="transition-colors hover:border-accent/50">
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <button type="button" className="min-w-0 text-left" onClick={() => navigate(`/bots/${bot.id}`)}>
            <div className="truncate text-base font-semibold text-ink">{bot.name}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
              {bot.symbol} <ModeBadge mode={bot.mode} /> <VolatilityBadge interval={bot.interval} /> <StatusBadge bot={bot} />
            </div>
          </button>
          <Switch checked={on} onChange={onToggle} disabled={toggle.isPending} label={<span className="text-xs text-ink-2">{on ? "Ligado" : "Desligado"}</span>} />
        </div>
        <button type="button" className="grid w-full grid-cols-3 gap-2 text-left" onClick={() => navigate(`/bots/${bot.id}`)}>
          <div>
            <div className="text-xs text-ink-2">Resultado</div>
            <Pnl value={bot.stats.total_pnl} quote={bot.quote_asset} className="font-medium" />
          </div>
          <div>
            <div className="text-xs text-ink-2">Por operação</div>
            <div className="font-medium text-ink tabular">{money(bot.risk.order_size_quote, bot.quote_asset)}</div>
          </div>
          <div>
            <div className="text-xs text-ink-2">Operações</div>
            <div className="font-medium text-ink tabular">{bot.stats.trades}{bot.stats.win_rate != null ? ` · ${pct(bot.stats.win_rate, false, 0)}` : ""}</div>
          </div>
        </button>
        <p className="text-xs text-ink-2">
          {pos ? (
            <>
              Comprado há {duration(pos.duration_seconds)}: <Pnl value={pos.unrealized_pct} percent />
            </>
          ) : on ? (
            `Aguardando oportunidade${bot.last_tick_at ? ` · checado ${timeAgo(bot.last_tick_at)}` : ""}`
          ) : (
            "Desligado: não compra nem vende."
          )}
        </p>
        <ErrorBox error={toggle.error} />
      </div>
      <Confirm
        open={confirm != null}
        title={confirm === "start" ? "Ligar com dinheiro real?" : "Desligar o robô?"}
        message={
          confirm === "start"
            ? `O robô vai enviar ordens reais à OKX: cada compra usa ${money(bot.risk.order_size_quote, bot.quote_asset)}.`
            : "A posição aberta continua aberta e deixa de ser acompanhada (sem stop automático) até você ligar de novo."
        }
        confirmLabel={confirm === "start" ? "Ligar" : "Desligar"}
        danger={confirm === "stop"}
        loading={toggle.isPending}
        onConfirm={() => confirm && toggle.mutate(confirm)}
        onClose={() => setConfirm(null)}
      />
    </Card>
  );
}

export function RobotsPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({ queryKey: ["bots"], queryFn: () => api.get<Bot[]>("/bots"), refetchInterval: 15_000 });
  return (
    <>
      <PageHeader
        title="Robôs"
        subtitle="Ligue, desligue e acompanhe. Para um robô novo, você escolhe a moeda, o valor e a volatilidade."
        actions={<Button variant="primary" onClick={() => navigate("/bots/new")}><Plus className="size-4" />Novo robô</Button>}
      />
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && data.length === 0 && (
        <Card>
          <Empty icon={<BotIcon className="size-8" />} title="Nenhum robô ainda">
            Escolha uma moeda, quanto investir e a volatilidade: o sistema testa todos os robôs e mostra o melhor.
            <div className="mt-4">
              <Button variant="primary" onClick={() => navigate("/bots/new")}><Plus className="size-4" />Criar o primeiro robô</Button>
            </div>
          </Empty>
        </Card>
      )}
      {data && data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {data.map((b) => (
            <RobotCard key={b.id} bot={b} />
          ))}
        </div>
      )}
    </>
  );
}
