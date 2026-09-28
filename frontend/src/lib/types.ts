export type Mode = "paper" | "live";

export interface User {
  id: number;
  email: string;
  name: string;
  created_at: string;
}

export interface AuthStatus {
  has_users: boolean;
  registration_open: boolean;
  user: User | null;
}

export interface Param {
  name: string;
  label: string;
  type: "int" | "float" | "bool" | "select";
  default: number | boolean | string;
  min: number | null;
  max: number | null;
  step: number | null;
  options: string[] | null;
  labels?: string[] | null;
  help: string;
}

export interface StrategyInfo {
  key: string;
  name: string;
  style: string;
  description: string;
  params: Param[];
}

export interface TakeProfit {
  pct: number;
  size_pct: number;
}

export interface RiskConfig {
  sizing_mode: "fixed_quote" | "percent_balance" | "risk_percent";
  order_size_quote: number;
  balance_percent: number;
  risk_percent: number;
  max_position_quote: number;
  stop_loss_mode: "none" | "percent" | "atr";
  stop_loss_pct: number;
  stop_loss_atr_mult: number;
  take_profits: TakeProfit[];
  breakeven_at_pct: number;
  trailing_enabled: boolean;
  trailing_mode: "percent" | "atr";
  trailing_pct: number;
  trailing_atr_mult: number;
  trailing_activation_pct: number;
  cooldown_bars: number;
  max_daily_loss_quote: number;
  fee_pct: number;
  sentiment_filter: SentimentFilter;
  fear_threshold: number;
  news_guard: NewsGuard;
  news_window_hours: number;
}

export type SentimentFilter = "off" | "avoid_extreme_fear" | "rising" | "both";
export type NewsGuard = "off" | "block_entries" | "block_and_exit";

export interface StrategiesResponse {
  default: string;
  default_interval: string;
  strategies: StrategyInfo[];
  default_risk: RiskConfig;
}

export interface Check {
  label: string;
  ok: boolean;
}

export interface Snapshot {
  entry: boolean;
  exit: boolean;
  entry_checks: Check[];
  exit_checks: Check[];
  values: Record<string, number | null>;
  candle_time?: number;
  close?: number;
  evaluated_at?: string;
  market?: MarketFilters;
}

export interface FearGreed {
  value: number;
  label: string;
  day: string;
  value_7d_ago: number | null;
  change_7d: number | null;
  stale: boolean;
}

/** Filtros de mercado no último candle avaliado pelo bot. */
export interface MarketFilters {
  sentiment_filter: SentimentFilter;
  news_guard: NewsGuard;
  sentiment?: FearGreed | null;
  news_block?: { title: string; source: string; url: string; published_at: string; sentiment: number };
  blocks_entry: boolean;
  reason: string;
}

export interface Position {
  id: number;
  bot_id: number;
  bot_name?: string;
  symbol: string;
  mode: Mode;
  strategy: string;
  status: "open" | "closed";
  entry_price: number;
  entry_time: string;
  initial_qty: number;
  qty: number;
  cost_quote: number;
  proceeds_quote: number;
  fees_quote: number;
  highest_price: number;
  stop_price: number | null;
  stop_kind: string;
  trailing_active: boolean;
  tp_index: number;
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string;
  pnl_quote: number | null;
  pnl_pct: number | null;
  duration_seconds: number | null;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  unrealized_pct?: number;
}

export interface BotStats {
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  today_pnl: number;
  trades: number;
  wins: number;
  win_rate: number | null;
  best_trade: number | null;
  worst_trade: number | null;
}

export interface Bot {
  id: number;
  name: string;
  symbol: string;
  base_asset: string;
  quote_asset: string;
  interval: string;
  strategy: string;
  strategy_name: string;
  strategy_params: Record<string, number | boolean | string>;
  risk: RiskConfig;
  mode: Mode;
  status: "stopped" | "running" | "paused" | "error";
  status_reason: string;
  running: boolean;
  paper_initial_balance: number;
  paper_balance: number;
  started_at: string | null;
  runtime_seconds: number;
  last_tick_at: string | null;
  last_signal: Snapshot | null;
  last_error: string;
  created_at: string;
  current_price: number | null;
  position: Position | null;
  stats: BotStats;
}

export interface BotEvent {
  id: number;
  level: "info" | "signal" | "trade" | "warn" | "error";
  message: string;
  data?: unknown;
  created_at: string;
  bot_id?: number;
  bot_name?: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LinePoint {
  time: number;
  value: number;
}

export interface ChartMarker {
  time: number;
  side: "BUY" | "SELL";
  price: number;
  reason: string;
}

export interface BotChart {
  candles: Candle[];
  overlays: Record<string, LinePoint[]>;
  markers: ChartMarker[];
  lines: { label: string; price: number; kind: "entry" | "stop" | "target" }[];
  preview: Snapshot;
}

export interface Dashboard {
  mode: "all" | Mode;
  summary: {
    realized_pnl: number;
    unrealized_pnl: number;
    total_pnl: number;
    today_pnl: number;
    trades: number;
    wins: number;
    win_rate: number | null;
    open_positions: number;
    invested: number;
    running_bots: number;
    total_bots: number;
    fees: number;
  };
  equity_curve: { time: string; pnl: number; live?: boolean }[];
  daily_pnl: { date: string; pnl: number }[];
  by_strategy: { strategy: string; name: string; pnl: number; trades: number; wins: number; win_rate: number | null }[];
  bots: Bot[];
  recent_trades: Position[];
  recent_events: BotEvent[];
}

export interface SystemInfo {
  engine_enabled: boolean;
  engine_started_at: string | null;
  uptime_seconds: number;
  running_bots: number;
  total_bots: number;
  server_time: string;
  version: string;
}

export interface Wallet {
  exchange: "okx";
  label: string;
  testnet: boolean;
  total_usdt: number | null;
  assets: { asset: string; total: number; value_usdt: number | null }[];
  error: string | null;
}

export interface KeyPermissions {
  account_mode?: string;
  reading: boolean;
  spot_trading: boolean;
  withdrawals: boolean;
  internal_transfer: boolean;
  universal_transfer: boolean;
  margin: boolean;
  futures: boolean;
  ip_restricted: boolean;
}

export interface Credentials {
  okx: {
    configured: boolean;
    api_key: string | null;
    demo: boolean;
    region: string | null;
    updated_at: string | null;
    permissions: KeyPermissions | null;
    warnings: string[];
    checked_at: string | null;
    regions: Record<string, string>;
  };
  anthropic: { configured: boolean; api_key: string | null; source: "db" | "env" | null; model: string };
  openai: {
    configured: boolean;
    api_key: string | null;
    source: "db" | "env" | null;
    model: string;
    fast_model: string;
    models: { id: string; label: string }[];
  };
  ai: { active: AIProvider | null; active_label: string | null; labels: Record<AIProvider, string> };
}

export type AIProvider = "anthropic" | "openai";

export type LoginResult = User | { two_factor_required: true; ticket: string };

export interface SecurityStatus {
  two_factor: { enabled: boolean; recovery_codes_left: number };
}

export interface SecurityEvent {
  id: number;
  kind: string;
  label: string;
  ip: string;
  user_agent: string;
  detail: string;
  created_at: string;
}

export interface TwoFactorSetup {
  secret: string;
  uri: string;
  qr: string;
}

export interface NewsItem {
  id: number;
  url: string;
  source: string;
  lang: string;
  title: string;
  summary: string;
  ai_summary: string;
  published_at: string;
  assets: string[];
  sentiment: number;
  impact: "low" | "medium" | "high";
  category: string;
  classified_by: "ai" | "keywords";
}

export interface SentimentResponse {
  latest: FearGreed | null;
  history: { date: string; value: number }[];
  filters: Record<SentimentFilter, string>;
}

export interface BotAlert {
  bot_id: number;
  name: string;
  symbol: string;
  asset: string;
  status: Bot["status"];
  blocked: boolean;
  reason: string;
  news: NewsItem | null;
  sentiment_filter: SentimentFilter;
  news_guard: NewsGuard;
}

export type AutopilotMode = "off" | "suggest" | "auto_paper" | "auto_all";

export interface AutopilotConfig {
  mode: AutopilotMode;
  mode_label: string;
  interval_hours: number;
  allow_strategy_change: boolean;
  live_authorized: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface RunMetrics {
  return_pct: number;
  drawdown_pct: number;
  trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  buy_hold_pct: number;
  score: number;
}

export interface RunChange {
  field: string;
  label: string;
  from: unknown;
  to: unknown;
}

export interface RunResults {
  in?: RunMetrics;
  out?: RunMetrics;
  full?: RunMetrics;
  cross?: { delta: number; pairs?: { symbol: string; base: RunMetrics; candidate: RunMetrics }[] } | null;
  passed?: boolean;
  reasons?: string[];
}

export interface RunCandidate {
  key: string;
  label: string;
  kind: string;
  source: string;
  note: string;
  changes: RunChange[];
  results: RunResults;
  gain: number;
}

export interface TestedRow {
  key: string;
  label: string;
  kind: string;
  source: string;
  changes: RunChange[];
  in: RunMetrics | null;
  out: RunMetrics | null;
  full: RunMetrics | null;
  cross: { delta: number } | null;
  passed: boolean;
  reasons: string[];
  note: string;
}

export interface Finding {
  level: "info" | "warn" | "bad";
  code: string;
  text: string;
}

export interface Followup {
  days: number;
  trades: number;
  pnl_quote: number;
  avg_trade_pct: number | null;
}

export type RunStatus = "running" | "suggested" | "applied" | "rejected" | "reverted" | "no_change" | "failed" | "superseded";

export interface OptimizationRun {
  id: number;
  bot_id: number;
  trigger: "manual" | "schedule";
  status: RunStatus;
  summary: string;
  candidate: RunCandidate | null;
  baseline: RunResults | null;
  created_at: string;
  finished_at: string | null;
  applied_at: string | null;
  reverted_at: string | null;
  ai_model: string;
  error: string;
  findings: Finding[];
  // só no detalhe
  diagnostics?: { stats: Record<string, unknown>; findings: Finding[] } | null;
  tested?: TestedRow[] | null;
  ai_notes?: string;
  baseline_full?: { period?: { start: number; split: number; end: number; bars: number; sentiment_data: boolean } } | null;
  followup?: Followup | null;
}

export interface BotAutopilot {
  autopilot: AutopilotConfig;
  running: boolean;
  last_run: OptimizationRun | null;
  suggestion: OptimizationRun | null;
}

// ------------------------------------------------------------------ escolha de robô

export type Level = "baixa" | "media" | "alta";

export interface LevelInfo {
  key: Level;
  label: string;
  intervals: string[];
  days: number;
  holding: string;
  description: string;
}

export interface CoinTicker {
  symbol: string;
  base: string;
  name: string;
  price: number;
  change_24h_pct: number;
  volume_usdt: number;
}

export interface CoinProfile {
  price?: number;
  daily_volatility_pct?: number;
  typical_day_range_pct?: number;
  return_30d_pct?: number;
}

export interface CoinInfo extends CoinProfile {
  symbol: string;
  base: string;
  name: string;
  change_24h_pct: number;
  wallet: { usdt?: number; coin?: number; error?: string } | null;
}

export interface RankedRobot {
  key: string;
  name: string;
  strategy: string;
  strategy_name: string;
  style: string;
  description: string;
  interval: string;
  return_pct: number;
  drawdown_pct: number;
  trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_trade_hours: number;
  exposure_pct: number;
  recent_return_pct: number;
  recent_drawdown_pct: number;
  recent_trades: number;
  buy_hold_pct: number;
  curve: { time: number; equity: number; buy_hold: number }[];
  score: number;
  eligible: boolean;
  position: number;
  final_usdt: number;
  profit_usdt: number;
  buy_hold_final_usdt: number;
}

export interface Ranking {
  symbol: string;
  level: Level;
  level_label: string;
  days: number;
  periods: Record<string, { start: number; split: number; end: number }>;
  robots: RankedRobot[];
  best: string;
  worst: string;
  coin: CoinProfile;
  fee_pct: number;
  tested_at: string;
  amount: number;
}

// ------------------------------------------------------------------ modo automático

export interface AutoConfig {
  enabled: boolean;
  mode: Mode;
  budget: number;
  slots: number;
  allocation: number;
  paused_reason: string;
  live_authorized: boolean;
  started_at: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface AutoLimits {
  robot_loss_pct: number;
  total_loss_pct: number;
  min_per_robot: number;
  max_robots: number;
  cycle_hours: number;
  min_age_days: number;
  cooldown_days: number;
  default_paper_budget: number;
}

export interface AutoAction {
  type: "create" | "retire" | "keep" | "pause" | "error";
  bot_id?: number;
  name?: string;
  text: string;
  state?: "retired" | "retiring";
}

export interface AutoPoolRow {
  pick: string;
  symbol: string;
  name: string;
  level: Level;
  interval: string;
  return_pct: number;
  recent_return_pct: number;
  drawdown_pct: number;
  trades: number;
  win_rate_pct: number;
  buy_hold_pct: number;
  days: number;
  yearly_score: number;
}

export interface AutoCycle {
  id: number;
  trigger: "start" | "manual" | "schedule";
  status: "running" | "done" | "failed";
  summary: string;
  actions: AutoAction[];
  ai_model: string;
  error: string;
  created_at: string;
  finished_at: string | null;
  pool?: AutoPoolRow[];
}

export interface AutoRobot {
  bot_id: number;
  state: "active" | "retiring" | "retired";
  allocation: number;
  level: string;
  reason: string;
  retire_reason: string;
  expected: {
    return_pct: number;
    recent_return_pct: number;
    drawdown_pct: number;
    trades: number;
    win_rate_pct: number;
    buy_hold_pct: number;
    days: number;
    fee_pct?: number;
  } | null;
  created_at: string;
  retired_at: string | null;
  pnl_pct: number | null;
  bot: Pick<Bot, "id" | "name" | "symbol" | "interval" | "strategy" | "strategy_name" | "mode" | "status" | "status_reason" | "position" | "stats" | "last_tick_at">;
}

export interface AutoOverview {
  config: AutoConfig;
  limits: AutoLimits;
  running: boolean;
  performance: {
    total_pnl: number;
    realized_pnl: number;
    unrealized_pnl: number;
    total_pct: number | null;
    today_pnl: number;
    trades: number;
    wins: number;
    win_rate: number | null;
    invested: number;
    active_robots: number;
  };
  equity_curve: { time: string; pnl: number; live?: boolean }[];
  robots: AutoRobot[];
  cycles: AutoCycle[];
  ai_configured: boolean;
  ai_label: string | null;
}

export interface Advice {
  recommended_key: string;
  headline: string;
  why: string;
  watch_out: string;
  confidence: "baixa" | "media" | "alta";
  source: "ai" | "rules";
  model?: string;
  provider?: string;
  note?: string;
}
