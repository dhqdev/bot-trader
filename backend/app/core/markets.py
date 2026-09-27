"""A corretora do sistema: OKX. (A Binance foi removida em set/2026.)"""

from app.core.okx import OkxMarketData, get_okx_market

EXCHANGE = "okx"
EXCHANGE_LABEL = "OKX"


def get_market(demo: bool = False, region: str = "global") -> OkxMarketData:
    """Dados de mercado da OKX (conta de demonstração e região da conta, quando houver)."""
    return get_okx_market(demo, region)
