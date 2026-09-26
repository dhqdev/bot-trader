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
}

export interface StrategiesResponse {
  default: string;
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

export interface OrderRow {
  id: number;
  position_id: number | null;
  side: "BUY" | "SELL";
  price: number;
  qty: number;
  quote_qty: number;
  fee_quote: number;
  reason: string;
  status: string;
  exchange_order_id: string;
  mode: Mode;
  created_at: string;
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

export interface Credentials {
  binance: { configured: boolean; api_key: string | null; testnet: boolean; updated_at: string | null };
  anthropic: { configured: boolean; api_key: string | null; source: "db" | "env" | null; model: string };
}

export interface BacktestTrade {
  entry_time: number;
  entry_price: number;
  exit_time: number;
  exit_price: number;
  exit_reason: string;
  partial_exits: number;
  cost: number;
  pnl: number;
  pnl_pct: number;
  fees: number;
  bars: number;
}

export interface BacktestMetrics {
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  buy_hold_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number;
  trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_trade_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  fees_paid: number;
  exposure_pct: number;
  avg_bars_in_trade: number;
  exit_reasons: Record<string, number>;
  bars: number;
  period_start: number;
  period_end: number;
}

export interface BacktestRequest {
  symbol: string;
  interval: string;
  strategy: string;
  params: Record<string, number | boolean | string>;
  risk: RiskConfig;
  days: number;
  initial_capital: number;
}

export interface BacktestResult {
  metrics: BacktestMetrics;
  equity_curve: { time: number; equity: number; buy_hold: number }[];
  trades: BacktestTrade[];
  request: BacktestRequest & { strategy_name: string };
  candles?: Candle[];
  overlays?: Record<string, LinePoint[]>;
}

export interface CompareRow {
  strategy: string;
  name: string;
  total_return_pct?: number;
  buy_hold_return_pct?: number;
  max_drawdown_pct?: number;
  sharpe?: number;
  trades?: number;
  win_rate_pct?: number;
  profit_factor?: number | null;
  exposure_pct?: number;
  error?: string;
}

export interface AIReportItem {
  id: number;
  title: string;
  bot_id: number | null;
  model: string;
  created_at: string;
  question?: string;
  content?: string;
}

export type AIEvent =
  | { type: "status"; text: string }
  | { type: "text"; text: string }
  | { type: "tool"; name: string; label: string; input: unknown }
  | { type: "tool_done"; name: string; ok: boolean }
  | { type: "done"; model?: string; report_id?: number }
  | { type: "error"; message: string };
