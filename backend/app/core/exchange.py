"""Acesso à Binance: dados públicos de mercado, execução real e simulada."""

import math
import threading
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

INTERVAL_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440,
}  # fmt: skip

KLINE_COLUMNS = ["time", "open", "high", "low", "close", "volume", "close_time"]


def interval_ms(interval: str) -> int:
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Intervalo inválido: {interval}")
    return INTERVAL_MINUTES[interval] * 60_000


def now_ms() -> int:
    return int(time.time() * 1000)


def _decimals(step: float) -> int:
    if step <= 0 or step >= 1:
        return 0
    return max(0, -int(math.floor(math.log10(step) + 1e-9)))


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    d_step = Decimal(str(step))
    return float((Decimal(str(value)) / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step)


@dataclass
class SymbolRules:
    symbol: str
    base: str
    quote: str
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float
    quote_precision: int = 8

    def floor_qty(self, qty: float) -> float:
        return _floor_to_step(qty, self.step_size)

    def format_qty(self, qty: float) -> str:
        return f"{self.floor_qty(qty):.{_decimals(self.step_size)}f}"

    def format_quote(self, amount: float) -> str:
        decimals = min(self.quote_precision, 8)
        return f"{_floor_to_step(amount, 10 ** -decimals):.{decimals}f}"

    def is_tradeable(self, qty: float, price: float) -> bool:
        q = self.floor_qty(qty)
        return q >= self.min_qty and q > 0 and q * price >= self.min_notional


@dataclass
class Fill:
    side: str
    order_id: str
    status: str
    qty: float  # quantidade executada (bruta)
    net_qty: float  # quantidade recebida após taxa cobrada no ativo base
    quote: float  # valor bruto em moeda de cotação
    avg_price: float
    fee_quote: float  # taxa convertida para a moeda de cotação
    net_quote: float  # compra: custo total | venda: valor líquido recebido
    raw: dict = field(default_factory=dict)


def klines_to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=KLINE_COLUMNS)
    df = pd.DataFrame([r[:7] for r in rows], columns=KLINE_COLUMNS)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["time"] = df["time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


class MarketData:
    """Dados públicos (não precisa de chave)."""

    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self._client: Client | None = None
        self._lock = threading.Lock()
        self._rules: dict[str, SymbolRules] = {}
        self._symbols: tuple[float, list[dict]] | None = None

    @property
    def client(self) -> Client:
        with self._lock:
            if self._client is None:
                self._client = Client(testnet=self.testnet, ping=False)
            return self._client

    def klines(self, symbol: str, interval: str, limit: int = 500, closed_only: bool = True) -> pd.DataFrame:
        """Últimos `limit` candles; pagina automaticamente acima de 1000."""
        wanted = limit + (1 if closed_only else 0)
        rows: list = []
        end_time = None
        while len(rows) < wanted:
            batch_size = min(1000, wanted - len(rows))
            params = {"symbol": symbol, "interval": interval, "limit": batch_size}
            if end_time is not None:
                params["endTime"] = end_time
            batch = self.client.get_klines(**params)
            if not batch:
                break
            rows = batch + rows
            if len(batch) < batch_size:
                break
            end_time = batch[0][0] - 1
        df = klines_to_df(rows)
        if closed_only and not df.empty:
            df = df[df["close_time"] < now_ms()]
        return df.tail(limit).reset_index(drop=True)

    def price(self, symbol: str) -> float:
        return float(self.client.get_symbol_ticker(symbol=symbol)["price"])

    def ticker_24h(self, symbol: str) -> dict:
        t = self.client.get_ticker(symbol=symbol)
        return {
            "price": float(t["lastPrice"]),
            "change_pct": float(t["priceChangePercent"]),
            "high": float(t["highPrice"]),
            "low": float(t["lowPrice"]),
            "quote_volume": float(t["quoteVolume"]),
        }

    def prices(self) -> dict[str, float]:
        return {t["symbol"]: float(t["price"]) for t in self.client.get_all_tickers()}

    def symbol_rules(self, symbol: str) -> SymbolRules:
        if symbol in self._rules:
            return self._rules[symbol]
        info = self.client.get_symbol_info(symbol)
        if not info:
            raise ValueError(f"Par não encontrado na Binance: {symbol}")
        filters = {f["filterType"]: f for f in info["filters"]}
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
        rules = SymbolRules(
            symbol=symbol,
            base=info["baseAsset"],
            quote=info["quoteAsset"],
            tick_size=float(filters.get("PRICE_FILTER", {}).get("tickSize", 0.00000001)),
            step_size=float(filters.get("LOT_SIZE", {}).get("stepSize", 0.00000001)),
            min_qty=float(filters.get("LOT_SIZE", {}).get("minQty", 0)),
            min_notional=float(notional.get("minNotional", 5)),
            quote_precision=int(info.get("quoteAssetPrecision", info.get("quotePrecision", 8))),
        )
        self._rules[symbol] = rules
        return rules

    def symbols(self, quote: str | None = None) -> list[dict]:
        if self._symbols is None or time.time() - self._symbols[0] > 3600:
            info = self.client.get_exchange_info()
            items = [
                {"symbol": s["symbol"], "base": s["baseAsset"], "quote": s["quoteAsset"]}
                for s in info["symbols"]
                if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", True)
            ]
            self._symbols = (time.time(), items)
        items = self._symbols[1]
        return [s for s in items if quote is None or s["quote"] == quote.upper()]


_markets: dict[bool, MarketData] = {}


def get_market(testnet: bool = False) -> MarketData:
    if testnet not in _markets:
        _markets[testnet] = MarketData(testnet=testnet)
    return _markets[testnet]


# ---------------------------------------------------------------------------
# Execução


class BinanceTrader:
    """Ordens reais a mercado na Binance Spot."""

    mode = "live"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.testnet = testnet
        self.client = Client(api_key, api_secret, testnet=testnet, ping=False)
        self.market = get_market(testnet)
        self._sync_time()

    def _sync_time(self) -> None:
        server = self.client.get_server_time()["serverTime"]
        self.client.timestamp_offset = server - now_ms()

    def _call(self, fn, **params):
        try:
            return fn(**params)
        except BinanceAPIException as e:
            if e.code == -1021:  # relógio fora de sincronia
                self._sync_time()
                return fn(**params)
            raise

    def balances(self) -> dict[str, tuple[float, float]]:
        account = self._call(self.client.get_account)
        return {b["asset"]: (float(b["free"]), float(b["locked"])) for b in account["balances"]}

    def free(self, asset: str) -> float:
        return self.balances().get(asset, (0.0, 0.0))[0]

    def account_summary(self) -> dict:
        account = self._call(self.client.get_account)
        balances = [
            {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
            for b in account["balances"]
            if float(b["free"]) + float(b["locked"]) > 0
        ]
        return {
            "can_trade": bool(account.get("canTrade")),
            "account_type": account.get("accountType", ""),
            "permissions": account.get("permissions", []),
            "balances": balances,
        }

    def api_permissions(self) -> dict | None:
        """Permissões da chave (a testnet não tem esse endpoint)."""
        if self.testnet:
            return None
        raw = self._call(self.client.get_account_api_permissions)
        return {
            "reading": bool(raw.get("enableReading")),
            "spot_trading": bool(raw.get("enableSpotAndMarginTrading")),
            "withdrawals": bool(raw.get("enableWithdrawals")),
            "internal_transfer": bool(raw.get("enableInternalTransfer")),
            "universal_transfer": bool(raw.get("permitsUniversalTransfer")),
            "margin": bool(raw.get("enableMargin")),
            "futures": bool(raw.get("enableFutures")),
            "ip_restricted": bool(raw.get("ipRestrict")),
        }

    def _fee_to_quote(self, amount: float, asset: str, rules: SymbolRules, price: float) -> float:
        if amount == 0:
            return 0.0
        if asset == rules.quote:
            return amount
        if asset == rules.base:
            return amount * price
        try:  # ex.: taxa paga em BNB
            return amount * self.market.price(f"{asset}{rules.quote}")
        except Exception:
            return 0.0

    def _parse(self, order: dict, rules: SymbolRules) -> Fill:
        qty = float(order.get("executedQty", 0))
        quote = float(order.get("cummulativeQuoteQty", 0))
        avg = quote / qty if qty else 0.0
        fee_quote = fee_base = 0.0
        for f in order.get("fills", []):
            c, asset = float(f["commission"]), f["commissionAsset"]
            if asset == rules.base:
                fee_base += c
            fee_quote += self._fee_to_quote(c, asset, rules, float(f["price"]))
        side = order["side"]
        if side == "BUY":
            # taxa no ativo base já reduz a quantidade; em outra moeda (BNB) soma ao custo
            extra = fee_quote - fee_base * avg
            net_quote = quote + max(extra, 0.0)
        else:
            net_quote = quote - fee_quote
        return Fill(
            side=side,
            order_id=str(order.get("orderId", "")),
            status=order.get("status", ""),
            qty=qty,
            net_qty=qty - fee_base if side == "BUY" else qty,
            quote=quote,
            avg_price=avg,
            fee_quote=fee_quote,
            net_quote=net_quote,
            raw=order,
        )

    def market_buy_quote(self, symbol: str, quote_amount: float, rules: SymbolRules) -> Fill:
        order = self._call(
            self.client.create_order,
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quoteOrderQty=rules.format_quote(quote_amount),
            newOrderRespType="FULL",
        )
        return self._parse(order, rules)

    def market_sell_qty(self, symbol: str, qty: float, rules: SymbolRules) -> Fill:
        order = self._call(
            self.client.create_order,
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=rules.format_qty(qty),
            newOrderRespType="FULL",
        )
        return self._parse(order, rules)


def inspect_api_key(api_key: str, api_secret: str, testnet: bool = False) -> dict:
    """Confere a chave na Binance: se ela lê a conta e quais permissões tem."""
    trader = BinanceTrader(api_key, api_secret, testnet=testnet)
    summary = trader.account_summary()
    return {"can_trade": summary["can_trade"], "account_type": summary["account_type"], "permissions": trader.api_permissions()}


class PaperTrader:
    """Execução simulada com preço real, taxa e slippage."""

    mode = "paper"

    def __init__(self, market: MarketData, fee_pct: float = 0.1, slippage_pct: float = 0.05):
        self.market = market
        self.fee = fee_pct / 100
        self.slippage = slippage_pct / 100

    def market_buy_quote(self, symbol: str, quote_amount: float, rules: SymbolRules) -> Fill:
        price = self.market.price(symbol) * (1 + self.slippage)
        qty = rules.floor_qty(quote_amount / (price * (1 + self.fee)))
        gross = qty * price
        fee = gross * self.fee
        return Fill("BUY", f"paper-{now_ms()}", "FILLED", qty, qty, gross, price, fee, gross + fee)

    def market_sell_qty(self, symbol: str, qty: float, rules: SymbolRules) -> Fill:
        price = self.market.price(symbol) * (1 - self.slippage)
        qty = rules.floor_qty(qty)
        gross = qty * price
        fee = gross * self.fee
        return Fill("SELL", f"paper-{now_ms()}", "FILLED", qty, qty, gross, price, fee, gross - fee)
