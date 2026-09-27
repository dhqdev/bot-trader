import { useQuery } from "@tanstack/react-query";
import { Bot as BotIcon, Plus } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { ModeBadge, StatusBadge } from "../components/bot";
import { TierBadge } from "../components/profiles";
import { Button, Card, Empty, ErrorBox, Loading, PageHeader, Pnl } from "../components/ui";
import { api } from "../lib/api";
import { duration, pct, price } from "../lib/format";
import type { Bot } from "../lib/types";

export function BotsPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({ queryKey: ["bots"], queryFn: () => api.get<Bot[]>("/bots"), refetchInterval: 15_000 });

  return (
    <>
      <PageHeader
        title="Bots"
        subtitle="Cada bot opera um par com uma estratégia e regras de risco próprias."
        actions={<Button variant="primary" onClick={() => navigate("/bots/new")}><Plus className="size-4" />Novo bot</Button>}
      />
      {isLoading && <Loading />}
      <ErrorBox error={error} />
      {data && data.length === 0 && (
        <Card>
          <Empty icon={<BotIcon className="size-8" />} title="Nenhum bot criado">
            Comece pelo modo simulado. Quando estiver confiante, troque para real.
          </Empty>
        </Card>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((b) => (
          <Link key={b.id} to={`/bots/${b.id}`} className="block rounded-xl border border-line bg-surface p-4 transition-colors hover:bg-surface-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium text-ink">{b.name}</div>
                <div className="mt-0.5 text-xs text-muted">{b.symbol} · {b.interval} · {b.strategy_name}</div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <TierBadge interval={b.interval} />
                <ModeBadge mode={b.mode} />
              </div>
            </div>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div>
                <div className="text-xs text-ink-2">Resultado</div>
                <Pnl value={b.stats.total_pnl} quote={b.quote_asset} className="text-lg font-semibold" />
              </div>
              <div className="text-right text-xs text-ink-2">
                <div>{b.stats.trades} operações · acerto {pct(b.stats.win_rate, false, 0)}</div>
                <div>operando há {duration(b.runtime_seconds)}</div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3">
              <StatusBadge bot={b} />
              {b.position ? (
                <span className="text-xs text-ink-2">
                  Posicionado · <Pnl value={b.position.unrealized_pct} percent />
                </span>
              ) : (
                <span className="text-xs text-muted">Aguardando entrada · {price(b.current_price)}</span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
