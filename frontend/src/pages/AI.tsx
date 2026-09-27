import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, FileText, Loader2, Send, Sparkles, Square, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { useLocation, useNavigate } from "react-router";
import remarkGfm from "remark-gfm";
import { Badge, Button, Card, Empty, Modal, PageHeader, Switch } from "../components/ui";
import { api, streamChat } from "../lib/api";
import { dateTime } from "../lib/format";
import type { AIReportItem, BacktestResult } from "../lib/types";

interface ToolCall {
  name: string;
  label: string;
  ok: boolean | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  tools?: ToolCall[];
  status?: string;
  error?: string;
}

interface NavState {
  botId?: number;
  backtest?: BacktestResult;
  prompt?: string;
}

const SUGGESTIONS = [
  "Como estão meus bots? O que está funcionando e o que não está?",
  "Qual estratégia funciona melhor para SOLUSDT no 4h? Compare todas.",
  "Analise o momento atual do BTC e diga se é um bom mercado para as minhas estratégias.",
  "Minha configuração de risco está adequada? Sugira ajustes com base em backtests.",
];

function MarkdownView({ text }: { text: string }) {
  return (
    <div className="prose-bt text-sm">
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
}

function ReportModal({ id, onClose }: { id: number | null; onClose: () => void }) {
  const report = useQuery({ queryKey: ["report", id], queryFn: () => api.get<AIReportItem>(`/ai/reports/${id}`), enabled: id != null });
  return (
    <Modal open={id != null} onClose={onClose} title={report.data?.title ?? "Relatório"} wide>
      {report.data ? (
        <div className="max-h-[70vh] overflow-y-auto">
          <p className="mb-3 text-xs text-muted">{dateTime(report.data.created_at)} · {report.data.model}</p>
          <MarkdownView text={report.data.content ?? ""} />
        </div>
      ) : (
        <Loader2 className="size-5 animate-spin text-muted" />
      )}
    </Modal>
  );
}

export function AIPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const nav = (location.state as NavState | null) ?? {};
  const [context, setContext] = useState<{ botId?: number; backtest?: BacktestResult }>({ botId: nav.botId, backtest: nav.backtest });
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [saveReport, setSaveReport] = useState(true);
  const [openReport, setOpenReport] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const autoSent = useRef(false);

  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api.get<{ configured: boolean; model: string }>("/ai/status") });
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api.get<AIReportItem[]>("/ai/reports") });
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/ai/reports/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [messages]);

  // "Analisar com IA" vindo de um bot ou backtest: envia a pergunta automaticamente
  useEffect(() => {
    if (nav.prompt && status.data?.configured && !autoSent.current) {
      autoSent.current = true;
      void send(nav.prompt);
      navigate(".", { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.data?.configured]);

  function patchLast(fn: (m: Message) => Message) {
    setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || streaming) return;
    const history = [...messages.filter((m) => !m.error && m.content), { role: "user" as const, content: question }];
    setMessages([...messages, { role: "user", content: question }, { role: "assistant", content: "", tools: [], status: "Pensando…" }]);
    setInput("");
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const body = {
        messages: history.map((m) => ({ role: m.role, content: m.content })),
        context: { bot_id: context.botId ?? null, backtest: context.backtest ? { request: context.backtest.request, metrics: context.backtest.metrics, trades: context.backtest.trades.slice(-30) } : null },
        save_report: saveReport,
        title: question.slice(0, 120),
      };
      for await (const ev of streamChat(body, controller.signal)) {
        if (ev.type === "text") patchLast((m) => ({ ...m, content: m.content + ev.text, status: undefined }));
        else if (ev.type === "status") patchLast((m) => ({ ...m, status: m.content ? undefined : ev.text }));
        else if (ev.type === "tool") patchLast((m) => ({ ...m, status: `${ev.label}…`, tools: [...(m.tools ?? []), { name: ev.name, label: ev.label, ok: null }] }));
        else if (ev.type === "tool_done")
          patchLast((m) => {
            const tools = [...(m.tools ?? [])];
            const idx = tools.findLastIndex((t) => t.name === ev.name && t.ok === null);
            if (idx >= 0) tools[idx] = { ...tools[idx], ok: ev.ok };
            return { ...m, tools, status: "Pensando…" };
          });
        else if (ev.type === "error") patchLast((m) => ({ ...m, error: ev.message, status: undefined }));
        else if (ev.type === "done") {
          patchLast((m) => ({ ...m, status: undefined }));
          if (ev.report_id) qc.invalidateQueries({ queryKey: ["reports"] });
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        patchLast((m) => ({ ...m, error: err instanceof Error ? err.message : String(err), status: undefined }));
      } else {
        patchLast((m) => ({ ...m, status: undefined, error: m.content ? undefined : "Interrompido." }));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  if (status.data && !status.data.configured) {
    return (
      <>
        <PageHeader title="Análise com IA" />
        <Card>
          <Empty icon={<Sparkles className="size-8" />} title="Configure a IA">
            Cadastre sua chave da API da Anthropic (Claude) em Configurações. A IA analisa seus bots, o mercado e roda backtests para embasar as sugestões.
            <div className="mt-4">
              <Button variant="primary" onClick={() => navigate("/settings")}>Ir para Configurações</Button>
            </div>
          </Empty>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Análise com IA" subtitle={`Pergunte sobre seus bots, estratégias e o mercado. A IA consulta dados reais e roda backtests, mas não envia ordens.${status.data ? ` · ${status.data.model}` : ""}`} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
        <Card padded={false} className="flex min-h-[70vh] flex-col">
          <div className="flex-1 space-y-5 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="py-6">
                <Empty icon={<Sparkles className="size-8" />} title="Como posso ajudar?" />
                <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-lg border border-line p-3 text-left text-sm text-ink-2 hover:bg-surface-2 hover:text-ink">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="ml-auto max-w-[85%] rounded-xl bg-surface-2 px-4 py-2.5 text-sm whitespace-pre-wrap text-ink">{m.content}</div>
              ) : (
                <div key={i} className="max-w-full space-y-2">
                  {m.tools && m.tools.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.tools.map((t, j) => (
                        <Badge key={j} tone={t.ok === false ? "bad" : "neutral"}>
                          {t.ok === null ? <Loader2 className="size-3 animate-spin" /> : t.ok ? <Check className="size-3 text-good-text" /> : <X className="size-3" />}
                          {t.label}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {m.content && <MarkdownView text={m.content} />}
                  {m.status && (
                    <div className="flex items-center gap-2 text-sm text-muted">
                      <Loader2 className="size-4 animate-spin" /> {m.status}
                    </div>
                  )}
                  {m.error && <div className="rounded-lg border border-bad/40 px-3 py-2 text-sm text-bad-text">{m.error}</div>}
                </div>
              ),
            )}
            <div ref={endRef} />
          </div>

          <div className="border-t border-line p-3">
            {(context.botId || context.backtest) && (
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-muted">Contexto:</span>
                <Badge tone="accent">
                  {context.botId ? `Bot #${context.botId}` : `Backtest ${context.backtest?.request.strategy_name} · ${context.backtest?.request.symbol}`}
                  <button onClick={() => setContext({})} aria-label="Remover contexto"><X className="size-3" /></button>
                </Badge>
              </div>
            )}
            <form
              className="flex items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void send(input);
              }}
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(input);
                  }
                }}
                rows={2}
                placeholder="Pergunte algo… (Enter envia, Shift+Enter quebra linha)"
                className="min-h-[44px] flex-1 resize-y rounded-lg border border-line bg-page px-3 py-2 text-base text-ink placeholder:text-muted focus:border-accent focus:outline-none sm:text-sm"
              />
              {streaming ? (
                <Button type="button" onClick={() => abortRef.current?.abort()} aria-label="Parar"><Square className="size-4" /></Button>
              ) : (
                <Button type="submit" variant="primary" disabled={!input.trim()} aria-label="Enviar"><Send className="size-4" /></Button>
              )}
            </form>
            <div className="mt-2 flex items-center justify-between gap-2">
              <Switch checked={saveReport} onChange={setSaveReport} label={<span className="text-xs text-ink-2">Salvar respostas como relatório</span>} />
              {messages.length > 0 && !streaming && (
                <button className="text-xs text-ink-2 hover:text-ink" onClick={() => setMessages([])}>Nova conversa</button>
              )}
            </div>
          </div>
        </Card>

        <Card title="Relatórios salvos">
          {reports.data?.length ? (
            <ul className="-mx-2 space-y-0.5">
              {reports.data.map((r) => (
                <li key={r.id} className="group flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2">
                  <FileText className="mt-0.5 size-4 shrink-0 text-muted" />
                  <button className="min-w-0 flex-1 text-left" onClick={() => setOpenReport(r.id)}>
                    <div className={clsx("line-clamp-2 text-sm text-ink")}>{r.title}</div>
                    <div className="text-xs text-muted">{dateTime(r.created_at)}</div>
                  </button>
                  <button className="opacity-0 group-hover:opacity-100 focus:opacity-100" onClick={() => del.mutate(r.id)} aria-label="Excluir relatório">
                    <Trash2 className="size-3.5 text-muted hover:text-bad-text" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">As análises salvas aparecem aqui.</p>
          )}
        </Card>
      </div>
      <ReportModal id={openReport} onClose={() => setOpenReport(null)} />
    </>
  );
}
