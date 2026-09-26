from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.risk import RiskConfig
from app.core.strategies import DEFAULT_INTERVAL, DEFAULT_STRATEGY, STRATEGIES
from app.deps import get_current_user
from app.schemas import BacktestIn
from app.services import backtesting

router = APIRouter(tags=["strategies"], dependencies=[Depends(get_current_user)])


@router.get("/strategies")
def list_strategies():
    return {
        "default": DEFAULT_STRATEGY,
        "default_interval": DEFAULT_INTERVAL,
        "strategies": [s.describe() for s in STRATEGIES.values()],
        "default_risk": RiskConfig().model_dump(),
    }


@router.post("/backtest")
async def run_backtest(body: BacktestIn):
    try:
        return await run_in_threadpool(
            backtesting.backtest,
            body.symbol,
            body.interval,
            body.strategy,
            body.params,
            body.risk,
            body.days,
            body.initial_capital,
            True,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha no backtest: {exc}") from exc


class CompareIn(BaseModel):
    symbol: str = Field(min_length=4, max_length=32)
    interval: str = "1h"
    days: int = Field(90, ge=3, le=730)
    risk: RiskConfig = Field(default_factory=RiskConfig)


@router.post("/backtest/compare")
async def compare(body: CompareIn):
    try:
        return await run_in_threadpool(backtesting.compare, body.symbol.upper(), body.interval, body.days, body.risk)
    except Exception as exc:
        raise HTTPException(502, f"Falha na comparação: {exc}") from exc
