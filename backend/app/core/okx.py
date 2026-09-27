"""OKX (API v5): dados de mercado e execução Spot. É a corretora do sistema.

O sistema usa símbolos sem hífen (BTCUSDT) em todo lugar; aqui eles são
convertidos para o formato da OKX (BTC-USDT) pela lista de instrumentos.

Autenticação (documentação oficial da OKX):
- cabeçalhos OK-ACCESS-KEY, OK-ACCESS-SIGN, OK-ACCESS-TIMESTAMP e OK-ACCESS-PASSPHRASE;
- assinatura = Base64(HMAC-SHA256(segredo, timestamp + MÉTODO + caminho com query + corpo));
- timestamp ISO 8601 em UTC com milissegundos (2020-12-08T09:08:57.715Z);
- conta de demonstração (Demo Trading): cabeçalho x-simulated-trading: 1.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import pandas as pd

from app.core.exchange import KLINE_COLUMNS, Fill, SymbolRules, interval_ms, now_ms

log = logging.getLogger("bot_trader.okx")

# A OKX tem domínios por região: a conta só funciona no domínio em que foi criada.
REGIONS = {"global": "https://www.okx.com", "eea": "https://eea.okx.com", "us": "https://us.okx.com"}
REGION_LABELS = {
    "global": "Global: okx.com (Brasil e demais países)",
    "eea": "Europa: my.okx.com",
    "us": "EUA e Austrália: app.okx.com",
}

# candles: 6h, 12h e 1d da OKX começam no horário de Hong Kong; usamos as versões "utc" (dia começando à meia-noite UTC)
BARS = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6Hutc", "12h": "12Hutc", "1d": "1Dutc",
}  # fmt: skip

STABLE_QUOTES = {"USDT", "USDC", "USD", "EUR", "BRL", "TUSD", "FDUSD", "DAI"}
# intervalo mínimo entre chamadas públicas (a OKX limita por IP: ~20 a cada 2 s no histórico)
MIN_INTERVAL = {"/api/v5/market/history-candles": 0.11, "/api/v5/market/candles": 0.055}
RATE_LIMITED = "50011"
ACCOUNT_MODES = {"1": "Spot (simples)", "2": "Spot e futuros", "3": "Margem multimoeda", "4": "Margem de portfólio"}
DONE_STATES = ("filled", "canceled", "mmp_canceled")


class OkxError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"OKX {code}: {message}")
        self.code = code
        self.message = message


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def okx_timestamp(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


class OkxClient:
    """Cliente REST mínimo (httpx), com assinatura e sincronia de relógio."""

    def __init__(self, api_key: str = "", secret: str = "", passphrase: str = "", demo: bool = False, region: str = "global",
                 transport: httpx.BaseTransport | None = None, timeout: float = 15.0):  # fmt: skip
        self.api_key, self.secret, self.passphrase = api_key, secret, passphrase
        self.demo = demo
        self.base_url = REGIONS.get(region, REGIONS["global"])
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport, headers={"User-Agent": "BotTrader"})
        self._offset_ms = 0
        self._synced = False
        self._throttle_lock = threading.Lock()
        self._last_call: dict[str, float] = {}

    def _throttle(self, path: str) -> None:
        wait = MIN_INTERVAL.get(path)
        if not wait:
            return
        with self._throttle_lock:
            elapsed = time.monotonic() - self._last_call.get(path, 0.0)
            if elapsed < wait:
                time.sleep(wait - elapsed)
            self._last_call[path] = time.monotonic()

    def _base_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.demo:
            headers["x-simulated-trading"] = "1"
        return headers

    def sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        prehash = f"{timestamp}{method.upper()}{path}{body}"
        digest = hmac.new(self.secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    @staticmethod
    def _payload(res: httpx.Response) -> dict:
        try:
            payload = res.json()
        except ValueError as exc:
            raise OkxError(str(res.status_code), f"resposta inválida da OKX (HTTP {res.status_code})") from exc
        if not isinstance(payload, dict):
            raise OkxError(str(res.status_code), "resposta inválida da OKX")
        if res.status_code >= 400 and str(payload.get("code", "")) in ("", "0"):
            payload["code"] = str(res.status_code)
        return payload

    @staticmethod
    def _data(payload: dict) -> list:
        code = str(payload.get("code", ""))
        data = payload.get("data") or []
        if code != "0":
            # ordens recusadas: o motivo detalhado vem em data[0].sCode / sMsg
            if data and isinstance(data[0], dict) and str(data[0].get("sCode", "0")) not in ("", "0"):
                raise OkxError(str(data[0]["sCode"]), data[0].get("sMsg") or payload.get("msg") or "ordem recusada")
            raise OkxError(code or "?", payload.get("msg") or "erro desconhecido")
        return data

    def public(self, path: str, params: dict | None = None) -> list:
        for attempt in range(4):
            self._throttle(path)
            res = self._http.get(path, params=params, headers=self._base_headers())
            try:
                return self._data(self._payload(res))
            except OkxError as exc:
                if exc.code not in (RATE_LIMITED, "429") or attempt == 3:
                    raise
                time.sleep(0.5 * 2**attempt)  # limite de requisições: espera e tenta de novo
        raise OkxError(RATE_LIMITED, "limite de requisições")

    def sync_time(self) -> None:
        server = int(self.public("/api/v5/public/time")[0]["ts"])
        self._offset_ms = server - now_ms()
        self._synced = True

    def private(self, method: str, path: str, params: dict | None = None, body: dict | None = None, _retry: bool = True) -> list:
        if not (self.api_key and self.secret and self.passphrase):
            raise OkxError("auth", "chaves da OKX não configuradas")
        if not self._synced:
            self.sync_time()
        request_path = path + ("?" + urlencode(params) if params else "")
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        timestamp = okx_timestamp(now_ms() + self._offset_ms)
        headers = {
            **self._base_headers(),
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self.sign(timestamp, method, request_path, body_str),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }
        res = self._http.request(method.upper(), self.base_url + request_path, content=body_str.encode("utf-8") if body_str else None, headers=headers)
        try:
            return self._data(self._payload(res))
        except OkxError as exc:
            if exc.code == "50102" and _retry:  # horário fora da janela aceita: sincroniza e tenta de novo
                self.sync_time()
                return self.private(method, path, params, body, _retry=False)
            raise


# ---------------------------------------------------------------------------
# Dados de mercado (públicos)


def candles_to_df(rows: list, interval: str, closed_only: bool) -> pd.DataFrame:
    step = interval_ms(interval)
    records = []
    for r in rows:
        confirmed = str(r[8]) == "1" if len(r) > 8 else True
        if closed_only and not confirmed:
            continue
        t = int(r[0])
        records.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), t + step - 1))
    df = pd.DataFrame(records, columns=KLINE_COLUMNS)
    if df.empty:
        return df
    df["time"] = df["time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if closed_only:
        df = df[df["close_time"] < now_ms()]
    return df


class OkxMarketData:
    """Dados de mercado públicos da OKX (candles, preços, regras dos pares)."""

    exchange = "okx"

    def __init__(self, demo: bool = False, region: str = "global", client: OkxClient | None = None):
        self.demo = demo
        self.region = region
        self.client = client or OkxClient(demo=demo, region=region)
        self._lock = threading.Lock()
        self._instruments: tuple[float, dict[str, dict]] | None = None
        self._rules: dict[str, tuple[float, SymbolRules]] = {}

    def instruments(self) -> dict[str, dict]:
        with self._lock:
            cached = self._instruments
        if cached is not None and time.time() - cached[0] < 3600:
            return cached[1]
        data = self.client.public("/api/v5/public/instruments", {"instType": "SPOT"})
        items = {f"{i['baseCcy']}{i['quoteCcy']}".upper(): i for i in data if i.get("baseCcy") and i.get("quoteCcy")}
        with self._lock:
            self._instruments = (time.time(), items)
        return items

    def inst(self, symbol: str) -> dict:
        item = self.instruments().get(symbol.upper().replace("-", "").replace("/", ""))
        if item is None:
            raise ValueError(f"Par não encontrado na OKX: {symbol}")
        return item

    def inst_id(self, symbol: str) -> str:
        return self.inst(symbol)["instId"]

    def klines(self, symbol: str, interval: str, limit: int = 500, closed_only: bool = True, before: int | None = None) -> pd.DataFrame:
        """Últimos `limit` candles (ou os `limit` anteriores ao horário `before`, em ms).

        Pagina para trás; além dos ~1440 mais recentes usa o endpoint de histórico.
        """
        bar = BARS.get(interval)
        if bar is None:
            raise ValueError(f"A OKX não tem candles de {interval}. Use: {', '.join(BARS)}.")
        inst_id = self.inst_id(symbol)
        step = interval_ms(interval)
        wanted = limit + (1 if closed_only and before is None else 0)
        rows: list = []
        seen: set[int] = set()

        def add(batch: list) -> list:
            fresh = [r for r in batch if int(r[0]) not in seen]
            seen.update(int(r[0]) for r in fresh)
            rows.extend(fresh)
            return fresh

        def history_page(after_ms: int) -> list:
            params = {"instId": inst_id, "bar": bar, "limit": "100", "after": str(after_ms)}
            return self.client.public("/api/v5/market/history-candles", params)

        # 1) os ~1440 candles mais recentes, 300 por vez
        after = before
        while len(rows) < wanted:
            params = {"instId": inst_id, "bar": bar, "limit": "300"}
            if after is not None:
                params["after"] = str(after)
            fresh = add(self.client.public("/api/v5/market/candles", params))
            if not fresh:
                break
            after = min(int(r[0]) for r in fresh)

        # 2) histórico, 100 por vez. Os candles têm espaçamento fixo, então o início de
        #    cada página é previsível e dá para pedir várias em paralelo (respeitando o
        #    limite da OKX). Se houver buraco, as páginas se sobrepõem, nunca deixam falha.
        missing = wanted - len(rows)
        if missing > 0:
            start = after if after is not None else (before if before is not None else now_ms())
            afters = [start - k * 100 * step for k in range(math.ceil(missing / 100) + 1)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                for batch in pool.map(history_page, afters):
                    add(batch)
            oldest = min(seen) if seen else None
            while len(rows) < wanted and oldest is not None:  # buracos no histórico: completa em sequência
                fresh = add(history_page(oldest))
                if not fresh:
                    break
                oldest = min(int(r[0]) for r in fresh)
        return candles_to_df(rows, interval, closed_only).tail(limit).reset_index(drop=True)

    def price(self, symbol: str) -> float:
        return _num(self.client.public("/api/v5/market/ticker", {"instId": self.inst_id(symbol)})[0]["last"])

    def ticker_24h(self, symbol: str) -> dict:
        t = self.client.public("/api/v5/market/ticker", {"instId": self.inst_id(symbol)})[0]
        last, open_ = _num(t.get("last")), _num(t.get("open24h"))
        return {
            "price": last,
            "change_pct": (last / open_ - 1) * 100 if open_ else 0.0,
            "high": _num(t.get("high24h")),
            "low": _num(t.get("low24h")),
            "quote_volume": _num(t.get("volCcy24h")),
        }

    def tickers(self) -> dict[str, dict]:
        """Preço, variação em 24 h e volume em 24 h (na moeda de cotação) de todos os pares Spot."""
        out = {}
        for t in self.client.public("/api/v5/market/tickers", {"instType": "SPOT"}):
            inst = t.get("instId") or ""
            last, open_ = _num(t.get("last")), _num(t.get("open24h"))
            out[inst.replace("-", "")] = {
                "price": last,
                "change_pct": (last / open_ - 1) * 100 if open_ else 0.0,
                "quote_volume": _num(t.get("volCcy24h")),
            }
        return out

    def prices(self) -> dict[str, float]:
        data = self.client.public("/api/v5/market/tickers", {"instType": "SPOT"})
        return {t["instId"].replace("-", ""): _num(t.get("last")) for t in data if t.get("instId")}

    def symbol_rules(self, symbol: str) -> SymbolRules:
        key = symbol.upper()
        cached = self._rules.get(key)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        inst = self.inst(key)
        min_sz = _num(inst.get("minSz"))
        try:
            price = self.price(key)
        except Exception:
            price = 0.0
        quote = inst["quoteCcy"]
        stable = quote in STABLE_QUOTES
        # a OKX define o mínimo pela quantidade (minSz); em valor, com folga para o preço mudar
        min_value = min_sz * price * 1.05
        rules = SymbolRules(
            symbol=key,
            base=inst["baseCcy"],
            quote=quote,
            tick_size=_num(inst.get("tickSz")) or 1e-8,
            step_size=_num(inst.get("lotSz")) or 1e-8,
            min_qty=min_sz,
            min_notional=max(1.0, min_value) if stable else min_value,
            quote_precision=2 if stable else 8,
        )
        self._rules[key] = (time.time(), rules)
        return rules

    def symbols(self, quote: str | None = None) -> list[dict]:
        items = [
            {"symbol": s, "base": i["baseCcy"], "quote": i["quoteCcy"]}
            for s, i in self.instruments().items()
            if i.get("state", "live") == "live"
        ]
        return sorted((s for s in items if quote is None or s["quote"] == quote.upper()), key=lambda s: s["symbol"])


_markets: dict[tuple[bool, str], OkxMarketData] = {}


def get_okx_market(demo: bool = False, region: str = "global") -> OkxMarketData:
    key = (demo, region if region in REGIONS else "global")
    if key not in _markets:
        _markets[key] = OkxMarketData(demo=key[0], region=key[1])
    return _markets[key]


# ---------------------------------------------------------------------------
# Execução real


def _perm_list(value) -> list[str]:
    return [p.strip().lower() for p in str(value or "").split(",") if p.strip()]


class OkxTrader:
    """Ordens a mercado na OKX Spot (sem margem: tdMode = cash)."""

    mode = "live"
    exchange = "okx"
    poll_delay = 0.3  # a ordem a mercado é assíncrona: consulta até ela terminar

    def __init__(self, api_key: str, secret: str, passphrase: str, demo: bool = False, region: str = "global",
                 client: OkxClient | None = None, market: OkxMarketData | None = None):  # fmt: skip
        self.demo = demo
        self.client = client or OkxClient(api_key, secret, passphrase, demo=demo, region=region)
        self.market = market or get_okx_market(demo, region)
        self.client.sync_time()

    # ------------------------------------------------------------ conta

    def config(self) -> dict:
        data = self.client.private("GET", "/api/v5/account/config")
        return data[0] if data else {}

    def balances(self) -> dict[str, tuple[float, float]]:
        data = self.client.private("GET", "/api/v5/account/balance")
        out: dict[str, tuple[float, float]] = {}
        for d in (data[0].get("details") if data else None) or []:
            frozen = _num(d.get("frozenBal"))
            avail = d.get("availBal")
            free = _num(avail) if avail not in (None, "") else _num(d.get("cashBal")) - frozen
            out[d.get("ccy", "")] = (max(free, 0.0), frozen)
        return out

    def free(self, asset: str) -> float:
        return self.balances().get(asset, (0.0, 0.0))[0]

    def account_summary(self) -> dict:
        cfg = self.config()
        perms = _perm_list(cfg.get("perm"))
        balances = [{"asset": a, "free": f, "locked": locked} for a, (f, locked) in self.balances().items() if f + locked > 0]
        return {
            "can_trade": "trade" in perms,
            "account_type": ACCOUNT_MODES.get(str(cfg.get("acctLv")), f"modo {cfg.get('acctLv')}"),
            "permissions": perms,
            "balances": balances,
        }

    def api_permissions(self) -> dict:
        cfg = self.config()
        perms = _perm_list(cfg.get("perm"))
        mode = str(cfg.get("acctLv") or "")
        return {
            "reading": True,
            "spot_trading": "trade" in perms,
            "withdrawals": any("withdraw" in p for p in perms),
            "internal_transfer": False,
            "universal_transfer": False,
            "margin": mode in ("3", "4"),
            "futures": mode in ("2", "3", "4"),
            "ip_restricted": bool(str(cfg.get("ip") or "").strip()),
            "account_mode": ACCOUNT_MODES.get(mode, mode),
        }

    # ------------------------------------------------------------ ordens

    def _order(self, inst_id: str, **ids: str) -> dict | None:
        data = self.client.private("GET", "/api/v5/trade/order", {"instId": inst_id, **ids})
        return data[0] if data else None

    def _place(self, symbol: str, side: str, sz: str, target: str, rules: SymbolRules) -> Fill:
        inst_id = self.market.inst_id(symbol)
        client_id = f"bt{side[0]}{now_ms()}{secrets.token_hex(3)}"[:32]
        body = {"instId": inst_id, "tdMode": "cash", "side": side, "ordType": "market", "sz": sz, "tgtCcy": target, "clOrdId": client_id}
        try:
            order_id = self.client.private("POST", "/api/v5/trade/order", body=body)[0]["ordId"]
        except httpx.TransportError:
            # a ordem pode ter chegado à OKX mesmo sem resposta: procura pelo nosso id antes de desistir
            time.sleep(self.poll_delay)
            try:
                found = self._order(inst_id, clOrdId=client_id)
            except (OkxError, httpx.HTTPError):
                found = None
            if not found:
                raise
            order_id = found["ordId"]
        order: dict = {}
        for _ in range(12):
            order = self._order(inst_id, ordId=order_id) or {}
            if order.get("state") in DONE_STATES:
                break
            time.sleep(self.poll_delay)
        else:
            log.warning("Ordem %s ainda em aberto na OKX (%s); registrando o que já foi executado.", order_id, order.get("state"))
        return self._parse(order, rules)

    def _price_in_quote(self, asset: str, quote: str) -> float:
        try:
            return self.market.price(f"{asset}{quote}")
        except Exception:
            return 0.0

    def _parse(self, order: dict, rules: SymbolRules) -> Fill:
        qty = _num(order.get("accFillSz"))  # sempre na moeda base no Spot
        avg = _num(order.get("avgPx"))
        quote = qty * avg
        fee = _num(order.get("fee"))
        fee_cost = -fee if fee < 0 else 0.0  # a OKX informa a taxa cobrada como número negativo
        fee_ccy = order.get("feeCcy") or ""
        fee_base = fee_cost if fee_ccy == rules.base else 0.0
        if fee_ccy == rules.quote:
            fee_quote = fee_cost
        elif fee_ccy == rules.base:
            fee_quote = fee_cost * avg
        else:
            fee_quote = fee_cost * self._price_in_quote(fee_ccy, rules.quote) if fee_cost else 0.0
        side = "BUY" if order.get("side") == "buy" else "SELL"
        if side == "BUY":
            net_quote = quote + max(fee_quote - fee_base * avg, 0.0)
            net_qty = qty - fee_base
        else:
            net_quote = quote - fee_quote
            net_qty = qty
        state = str(order.get("state", ""))
        return Fill(side, str(order.get("ordId", "")), "FILLED" if state == "filled" else state.upper(), qty, net_qty, quote, avg, fee_quote, net_quote, raw=order)

    def market_buy_quote(self, symbol: str, quote_amount: float, rules: SymbolRules) -> Fill:
        return self._place(symbol, "buy", rules.format_quote(quote_amount), "quote_ccy", rules)

    def market_sell_qty(self, symbol: str, qty: float, rules: SymbolRules) -> Fill:
        return self._place(symbol, "sell", rules.format_qty(qty), "base_ccy", rules)


def inspect_okx_key(api_key: str, secret: str, passphrase: str, demo: bool = False, region: str = "global") -> dict:
    """Confere a chave na OKX: se ela lê a conta e quais permissões tem."""
    trader = OkxTrader(api_key, secret, passphrase, demo=demo, region=region)
    summary = trader.account_summary()
    return {"can_trade": summary["can_trade"], "account_type": summary["account_type"], "permissions": trader.api_permissions()}
