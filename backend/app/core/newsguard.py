"""Trava de notícias usada pelo motor.

As notícias são coletadas e classificadas em segundo plano (services/news.py).
Aqui só se consulta o que já foi classificado:
- bloquear entradas: há notícia de alto impacto e bem negativa sobre a moeda
  do bot (ou sobre o mercado todo) nas últimas horas, confirmada pela IA ou
  publicada por pelo menos duas fontes;
- sair da posição (opcional): a notícia saiu depois da compra e foi confirmada
  pela IA, não só pelas palavras-chave (menos alarme falso).

Notícias boas não disparam compras: comprar na euforia da manchete costuma ser
comprar no topo. Elas entram na análise da IA.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NewsItem, utcnow

BLOCK_SENTIMENT = -0.5
EXIT_SENTIMENT = -0.6
MARKET = "MARKET"

MODE_LABELS = {
    "off": "desligada",
    "block_entries": "bloqueia compras",
    "block_and_exit": "bloqueia compras e vende a posição",
}


def _about(item: NewsItem, asset: str) -> bool:
    assets = item.assets or []
    return asset.upper() in assets or MARKET in assets


def bad_news(db: Session, asset: str, window_hours: float, now: datetime | None = None, since: datetime | None = None) -> list[NewsItem]:
    """Notícias graves e negativas sobre a moeda (ou o mercado todo) na janela.

    Vale a classificação da IA. Sem ela, as palavras-chave erram bastante
    (ex.: "Hack VC" é nome de um fundo), então só contam quando pelo menos
    duas fontes diferentes publicaram algo grave sobre a mesma moeda.
    """
    now = now or utcnow()
    start = now - timedelta(hours=window_hours)
    if since is not None and since > start:
        start = since
    rows = db.scalars(
        select(NewsItem)
        .where(NewsItem.published_at >= start, NewsItem.published_at <= now + timedelta(minutes=5), NewsItem.impact == "high")
        .order_by(NewsItem.published_at.desc())
        .limit(100)
    )
    items = [n for n in rows if n.sentiment <= BLOCK_SENTIMENT and _about(n, asset)]
    confirmed = [n for n in items if n.classified_by == "ai"]
    keyword_only = [n for n in items if n.classified_by != "ai"]
    if len({n.source for n in keyword_only}) >= 2:
        confirmed += keyword_only
    return sorted(confirmed, key=lambda n: n.published_at, reverse=True)


def entry_block(db: Session, asset: str, mode: str, window_hours: float) -> NewsItem | None:
    if mode == "off":
        return None
    items = bad_news(db, asset, window_hours)
    return items[0] if items else None


def exit_trigger(db: Session, asset: str, mode: str, window_hours: float, opened_at: datetime) -> NewsItem | None:
    if mode != "block_and_exit":
        return None
    for item in bad_news(db, asset, window_hours, since=opened_at):
        if item.classified_by == "ai" and item.sentiment <= EXIT_SENTIMENT:
            return item
    return None


def describe(item: NewsItem) -> str:
    return f"\"{item.title[:140]}\" ({item.source})"
