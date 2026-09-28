import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Info, Loader2, Play, Sparkles, XCircle } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { dateTime, timeAgo } from "../lib/format";
import type { BotAutopilot, Finding, OptimizationRun, RunStatus, SecurityStatus } from "../lib/types";
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, Select } from "./ui";

export const RUN_STATUS: Record<RunStatus, { label: string; tone: "good" | "bad" | "warn" | "neutral" | "accent" }> = {
  running: { label: "Testando…", tone: "accent" },
  suggested: { label: "Sugestão pendente", tone: "warn" },
  applied: { label: "Aplicada", tone: "good" },
  rejected: { label: "Recusada", tone: "neutral" },
  reverted: { label: "Desfeita", tone: "neutral" },
  no_change: { label: "Sem mudança", tone: "neutral" },
  failed: { label: "Falhou", tone: "bad" },
  superseded: { label: "Substituída", tone: "neutral" },
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const s = RUN_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return (
    <Badge tone={s.tone}>
      {status === "running" && <Loader2 className="size-3 animate-spin" />}
      {s.label}
    </Badge>
  );
}

const FINDING_ICON = {
  bad: <XCircle className="mt-0.5 size-4 shrink-0 text-bad-text" aria-label="problema" />,
  warn: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-text" aria-label="atenção" />,
  info: <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-label="informação" />,
};

export function Findings({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <p className="text-sm text-good-text">Nenhum problema encontrado no histórico do robô.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {findings.map((f) => (
        <li key={f.code} className="flex gap-2 text-ink-2">
          {FINDING_ICON[f.level]}
          <span>{f.text}</span>
        </li>
      ))}
    </ul>
  );
}

function useRunActions(botId: number) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["bot", String(botId)] });
    qc.invalidateQueries({ queryKey: ["bots"] });
  };
  const act = useMutation({
    mutationFn: ({ runId, action }: { runId: number; action: "apply" | "reject" | "revert" }) => api.post(`/autopilot/runs/${runId}/${action}`),
    onSuccess: refresh,
  });
  const run = useMutation({ mutationFn: () => api.post(`/autopilot/bots/${botId}/run`), onSuccess: refresh });
  return { act, run };
}

function SuggestionBox({ run, botId }: { run: OptimizationRun; botId: number }) {
  const { act } = useRunActions(botId);
  return (
    <div className="space-y-2 rounded-lg border border-warn/40 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
        <Sparkles className="size-4 text-warn-text" /> A IA sugere: {run.candidate?.label}
      </div>
      <p className="text-xs text-ink-2">{run.summary}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" onClick={() => act.mutate({ runId: run.id, action: "apply" })} loading={act.isPending && act.variables?.action === "apply"}>
          <Check className="size-3.5" />Aplicar
        </Button>
        <Button size="sm" onClick={() => act.mutate({ runId: run.id, action: "reject" })} loading={act.isPending && act.variables?.action === "reject"}>
          Recusar
        </Button>
      </div>
      <ErrorBox error={act.error} />
    </div>
  );
}

type Choice = "auto" | "suggest" | "off";

function AuthorizeModal({ open, onConfirm, onClose, error, loading }: {
  open: boolean;
  onConfirm: (password: string, code: string) => void;
  onClose: () => void;
  error: unknown;
  loading: boolean;
}) {
  const security = useQuery({ queryKey: ["security"], queryFn: () => api.get<SecurityStatus>("/security/status"), enabled: open });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  return (
    <Modal open={open} onClose={onClose} title="Deixar a IA ajustar um robô com dinheiro real?">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(password, code);
        }}
      >
        <p className="text-sm text-ink-2">
          A IA poderá mudar as regras deste robô sozinha, sem pedir aprovação a cada vez. Ela nunca muda a moeda, o valor por operação nem o modo, e troca de
          estratégia sempre espera você. No máximo uma mudança a cada 5 dias, e dá para desfazer.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Sua senha">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" autoFocus />
          </Field>
          {security.data?.two_factor.enabled && (
            <Field label="Código de 2 etapas">
              <Input value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" className="font-mono" />
            </Field>
          )}
        </div>
        <ErrorBox error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" loading={loading}>Autorizar</Button>
        </div>
      </form>
    </Modal>
  );
}

/** A IA de cada robô: testa melhorias, sugere ou aplica, e mostra o que encontrou. */
export function AutopilotCard({ botId, live }: { botId: number; live: boolean }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["bot", String(botId), "autopilot"],
    queryFn: () => api.get<BotAutopilot>(`/autopilot/bots/${botId}`),
    refetchInterval: (q) => (q.state.data?.running ? 4000 : 30_000),
  });
  const { run } = useRunActions(botId);
  const [authorize, setAuthorize] = useState(false);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put(`/autopilot/bots/${botId}`, body),
    onSuccess: () => {
      setAuthorize(false);
      qc.invalidateQueries({ queryKey: ["bot", String(botId), "autopilot"] });
    },
  });
  if (!data) return null;
  const cfg = data.autopilot;
  const choice: Choice =
    cfg.mode === "off" ? "off" : cfg.mode === "suggest" ? "suggest" : live ? (cfg.mode === "auto_all" && cfg.live_authorized ? "auto" : "suggest") : "auto";
  const base = { interval_hours: cfg.interval_hours, allow_strategy_change: cfg.allow_strategy_change };
  const change = (next: Choice) => {
    if (next === "off" || next === "suggest") save.mutate({ ...base, mode: next });
    else if (!live) save.mutate({ ...base, mode: "auto_paper" });
    else if (cfg.mode === "auto_all" && cfg.live_authorized) save.mutate({ ...base, mode: "auto_all" });
    else setAuthorize(true);
  };
  const last = data.last_run;
  return (
    <Card title={<span className="flex items-center gap-1.5"><Sparkles className="size-4 text-accent" />IA do robô</span>}>
      <div className="space-y-3 text-sm">
        <p className="text-xs text-ink-2">
          A IA testa melhorias neste robô no histórico e só troca o que se confirma no período recente. Ela ajusta stop, trailing, filtros e
          parâmetros, mas nunca troca a estratégia escolhida.
          {cfg.next_run_at && cfg.mode !== "off" ? ` Próximo teste: ${dateTime(cfg.next_run_at)}.` : ""}
        </p>
        <Field label="O que a IA pode fazer">
          <Select value={choice} onChange={(e) => change(e.target.value as Choice)} disabled={save.isPending}>
            <option value="auto">Ajustar sozinha{live ? " (pede sua senha)" : ""}</option>
            <option value="suggest">Só sugerir (eu aprovo)</option>
            <option value="off">Nada (desligada)</option>
          </Select>
        </Field>
        <ErrorBox error={save.error && !authorize ? save.error : null} />
        {data.suggestion && <SuggestionBox run={data.suggestion} botId={botId} />}
        {last && last.id !== data.suggestion?.id && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs">
              <RunStatusBadge status={last.status} />
              <span className="text-muted">{timeAgo(last.created_at)}</span>
            </div>
            {last.summary && <p className="line-clamp-4 text-xs text-ink-2">{last.summary}</p>}
          </div>
        )}
        {last && last.status !== "running" && last.findings.some((f) => f.level !== "info") && (
          <div className="border-t border-line pt-3">
            <div className="mb-1.5 text-xs font-medium text-ink-2">O que a IA encontrou</div>
            <Findings findings={last.findings.filter((f) => f.level !== "info")} />
          </div>
        )}
        <Button size="sm" onClick={() => run.mutate()} loading={run.isPending} disabled={data.running}>
          <Play className="size-3.5" />
          {data.running ? "Testando…" : "Testar melhorias agora"}
        </Button>
        <ErrorBox error={run.error} />
      </div>
      <AuthorizeModal
        open={authorize}
        loading={save.isPending}
        error={save.error}
        onClose={() => {
          setAuthorize(false);
          save.reset();
        }}
        onConfirm={(password, code) => save.mutate({ ...base, mode: "auto_all", password, code: code || null })}
      />
    </Card>
  );
}
