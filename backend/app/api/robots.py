"""Escolha de robô em 3 perguntas: moeda, valor e volatilidade.

O sistema testa todos os robôs na moeda escolhida, mostra do melhor ao pior e a
IA explica qual faz mais sentido. Criar o robô é um clique.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.bots import create_bot_record, start_bot_record
from app.core.engine import make_live_trader, okx_credential
from app.core.markets import get_market
from app.core.risk import RiskConfig
from app.db import get_db
from app.deps import get_current_user
from app.models import Bot, User
from app.schemas import BotIn, CreateRobotIn, RankIn, normalize_symbol
from app.services import ranking
from app.services.llm import resolve_ai
from app.services.stats import bot_summary

router = APIRouter(prefix="/robots", tags=["robots"])

COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP", "DOGE": "Dogecoin", "ADA": "Cardano",
    "AVAX": "Avalanche", "LINK": "Chainlink", "LTC": "Litecoin", "TRX": "Tron", "DOT": "Polkadot", "TON": "Toncoin",
    "SUI": "Sui", "PEPE": "Pepe", "SHIB": "Shiba Inu", "NEAR": "Near", "BNB": "BNB", "OKB": "OKB", "UNI": "Uniswap",
    "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism", "BCH": "Bitcoin Cash", "ETC": "Ethereum Classic",
    "XLM": "Stellar", "HBAR": "Hedera", "FIL": "Filecoin", "ATOM": "Cosmos", "AAVE": "Aave", "WLD": "Worldcoin",
    "POL": "Polygon", "ENA": "Ethena", "WIF": "dogwifhat", "BONK": "Bonk", "TRUMP": "Trump", "JUP": "Jupiter",
    "ZEC": "Zcash", "HYPE": "Hyperliquid", "PUMP": "Pump.fun", "XPL": "Plasma", "ONDO": "Ondo", "ICP": "Internet Computer",
    "RENDER": "Render", "TIA": "Celestia", "INJ": "Injective", "SEI": "Sei", "PENGU": "Pudgy Penguins", "LDO": "Lido",
    "CRV": "Curve", "STX": "Stacks", "IMX": "Immutable", "SAND": "The Sandbox", "MANA": "Decentraland", "GRT": "The Graph",
    "ALGO": "Algorand", "FLOKI": "Floki", "STRK": "Starknet", "TAO": "Bittensor", "XAUT": "Tether Gold", "PAXG": "PAX Gold",
}  # fmt: skip


@router.get("/levels")
def levels(_: User = Depends(get_current_user)):
    return [{k: v for k, v in level.items()} for level in ranking.LEVELS.values()]


@router.get("/coins")
def coins(_: User = Depends(get_current_user)):
    """As moedas mais negociadas na OKX contra USDT, com preço e variação em 24 h."""
    try:
        tickers = get_market().tickers()
    except Exception as exc:
        raise HTTPException(502, f"OKX indisponível: {exc}") from exc
    return [
        {
            "symbol": s,
            "base": s[:-4],
            "name": COIN_NAMES.get(s[:-4], s[:-4]),
            "price": t["price"],
            "change_24h_pct": round(t["change_pct"], 2),
            "volume_usdt": round(t["quote_volume"]),
        }
        for s, t in ranking.liquid_coins(tickers, 24)
    ]


@router.get("/coin/{symbol}")
async def coin(symbol: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quanto a moeda oscila e quanto você tem dela (e de USDT) na OKX."""
    symbol = normalize_symbol(symbol)
    try:
        market = get_market()
        inst = await run_in_threadpool(market.inst, symbol)
        ticker = await run_in_threadpool(market.ticker_24h, symbol)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"OKX indisponível: {exc}") from exc
    profile = await run_in_threadpool(ranking.coin_profile, symbol)
    base = inst["baseCcy"]
    wallet = None
    if okx_credential(db, user.id) is not None:
        try:
            trader = make_live_trader(db, Bot(user_id=user.id, mode="live"))
            balances = await run_in_threadpool(trader.balances)
            wallet = {"usdt": balances.get("USDT", (0.0, 0.0))[0], "coin": balances.get(base, (0.0, 0.0))[0]}
        except Exception as exc:
            wallet = {"error": f"Não foi possível ler a carteira na OKX: {exc}"[:200]}
    return {
        "symbol": symbol,
        "base": base,
        "name": COIN_NAMES.get(base, base),
        "price": ticker["price"],
        "change_24h_pct": round(ticker["change_pct"], 2),
        **profile,
        "wallet": wallet,
    }


@router.post("/rank")
async def rank(body: RankIn, _: User = Depends(get_current_user)):
    """Testa todos os robôs do nível de volatilidade na moeda e ordena do melhor ao pior."""
    try:
        result = await run_in_threadpool(ranking.rank, body.symbol, body.level, body.refresh)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao testar os robôs: {exc}") from exc
    return ranking.with_amount(result, body.amount)


@router.post("/advice")
async def advice(body: RankIn, user: User = Depends(get_current_user)):
    """Qual robô faz mais sentido (IA, se houver chave; senão, as regras do ranking)."""
    try:
        result = await run_in_threadpool(ranking.rank, body.symbol, body.level, False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    ai = resolve_ai(user.id)
    return await run_in_threadpool(ranking.advise, result, body.amount, ai)


@router.post("/create")
def create(body: CreateRobotIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cria o robô escolhido no ranking. A configuração vem do catálogo do servidor, nunca do navegador."""
    robot = ranking.find_robot(body.level, body.robot_key)
    if robot is None:
        raise HTTPException(400, "Robô inválido para essa volatilidade.")
    risk = RiskConfig(**{**robot["risk"], "sizing_mode": "fixed_quote", "order_size_quote": body.amount})
    base = body.symbol.removesuffix("USDT")
    bot_in = BotIn(
        name=(body.name.strip() or f"{base} · {robot['name']}")[:120],
        symbol=body.symbol,
        interval=robot["interval"],
        strategy=robot["strategy"],
        strategy_params=robot["params"],
        risk=risk,
        mode=body.mode,
        paper_initial_balance=body.amount,
    )
    bot = create_bot_record(db, user, bot_in)
    if body.start:
        start_bot_record(db, bot)
    return bot_summary(db, bot)
