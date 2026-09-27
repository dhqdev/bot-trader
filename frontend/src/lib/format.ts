const nf = (min: number, max: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: min, maximumFractionDigits: max });

const n2 = nf(2, 2);

export function money(v: number | null | undefined, quote = "USDT"): string {
  if (v == null || Number.isNaN(v)) return "–";
  return `${n2.format(v)} ${quote}`;
}

export function signedMoney(v: number | null | undefined, quote = "USDT"): string {
  if (v == null || Number.isNaN(v)) return "–";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${n2.format(Math.abs(v))} ${quote}`;
}

export function pct(v: number | null | undefined, signed = false, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "–";
  const sign = signed ? (v > 0 ? "+" : v < 0 ? "−" : "") : v < 0 ? "−" : "";
  return `${sign}${nf(digits, digits).format(Math.abs(v))}%`;
}

/** Preço com casas decimais adaptadas à grandeza (BTC vs. moedas baratas). */
export function price(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  const digits = a >= 1000 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : 8;
  return nf(Math.min(2, digits), digits).format(v);
}

export function qty(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "–";
  return nf(0, v >= 100 ? 2 : 6).format(v);
}

export function num(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "–";
  return nf(0, digits).format(v);
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "–";
  const s = Math.floor(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m}min`;
  return `${s}s`;
}

export function dateTime(v: string | number | null | undefined): string {
  if (v == null) return "–";
  const d = typeof v === "number" ? new Date(v) : new Date(v);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function shortDate(v: string | number): string {
  const d = new Date(v);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

export function timeAgo(v: string | null | undefined): string {
  if (!v) return "–";
  const diff = (Date.now() - new Date(v).getTime()) / 1000;
  if (diff < 60) return "agora";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} d`;
}

export const REASONS: Record<string, string> = {
  signal: "Sinal",
  stop_loss: "Stop loss",
  breakeven: "Break-even",
  trailing_stop: "Trailing stop",
  take_profit: "Alvo parcial",
  manual: "Manual",
  news: "Notícia",
  end: "Fim do teste",
};

export const SENTIMENT_FILTER_LABELS: Record<string, string> = {
  off: "desligado",
  avoid_extreme_fear: "evita medo extremo",
  rising: "só com sentimento subindo",
  both: "evita medo extremo e só subindo",
};

export const NEWS_GUARD_LABELS: Record<string, string> = {
  off: "desligada",
  block_entries: "bloqueia compras",
  block_and_exit: "bloqueia compras e vende",
};

/** Cor do índice de medo e ganância: medo = vermelho, ganância = verde. */
export function fearGreedTone(v: number | null | undefined): "bad" | "warn" | "neutral" | "good" {
  if (v == null) return "neutral";
  if (v <= 24) return "bad";
  if (v <= 45) return "warn";
  if (v <= 55) return "neutral";
  return "good";
}

export const INTERVAL_LABELS: Record<string, string> = {
  "1m": "1 minuto",
  "3m": "3 minutos",
  "5m": "5 minutos",
  "15m": "15 minutos",
  "30m": "30 minutos",
  "1h": "1 hora",
  "2h": "2 horas",
  "4h": "4 horas",
  "6h": "6 horas",
  "8h": "8 horas",
  "12h": "12 horas",
  "1d": "1 dia",
};

/** Duração típica de uma operação: "46 min", "16 h", "3 dias", "3 semanas". */
export function holdingTime(minutes: number): string {
  if (minutes < 90) return `${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 36) return `${Math.round(hours)} h`;
  const days = hours / 24;
  if (days < 14) return `${Math.round(days)} dias`;
  return `${Math.round(days / 7)} semanas`;
}
