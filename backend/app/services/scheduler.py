"""Tarefas em segundo plano, numa única thread:

- índice de medo e ganância: a cada hora;
- notícias (RSS): a cada 15 minutos;
- classificação das notícias pela IA: a cada 30 minutos (se houver chave da Anthropic);
- piloto automático: confere a cada minuto se algum bot ligado chegou na hora do ciclo;
- limpeza de registros antigos: uma vez por dia.

Uma tarefa que falha (ex.: site de notícias fora do ar) só é tentada de novo
no próximo horário; nunca derruba o servidor nem os bots.
"""

import logging
import threading
import time

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Bot, utcnow

log = logging.getLogger("bot_trader.scheduler")


def _fng() -> None:
    from app.core.sentiment import sentiment

    sentiment.refresh()


def _news() -> None:
    from app.services import news

    if get_settings().news_enabled:
        result = news.collect()
        if result.get("serious"):
            scheduler.run_now("news_ai")  # notícia que parece grave: a IA confirma logo


def _news_ai() -> None:
    from app.services import news
    from app.services.llm import any_ai

    ai = any_ai()
    if ai is not None and get_settings().news_enabled:
        news.classify_with_ai(ai)


def autopilot_tick() -> int | None:
    """Roda o ciclo do bot mais atrasado (um por vez). Devolve o id do ciclo ou None."""
    from app.services import optimizer
    from app.services.llm import resolve_ai

    run_id = user_id = None
    with session_scope() as db:
        now = utcnow()
        for bot in db.scalars(select(Bot).where(Bot.status == "running").order_by(Bot.id)):
            cfg = optimizer.get_autopilot(db, bot)
            if cfg.mode == "off" or (cfg.next_run_at is not None and cfg.next_run_at > now):
                continue
            if optimizer.is_running(db, bot.id):
                continue
            run = optimizer.start_run(db, bot, "schedule")
            run_id, user_id = run.id, bot.user_id
            break
    if run_id is None:
        return None
    try:
        ai = resolve_ai(user_id)
    except Exception:
        ai = None
    optimizer.execute(run_id, ai)
    return run_id


_prewarm_thread: threading.Thread | None = None


def _prewarm() -> None:
    """Histórico das moedas populares, numa thread à parte (a primeira vez leva alguns minutos)."""
    global _prewarm_thread
    from app.services import ranking

    if _prewarm_thread is not None and _prewarm_thread.is_alive():
        return
    _prewarm_thread = threading.Thread(target=ranking.prewarm, daemon=True, name="prewarm")
    _prewarm_thread.start()


def _prune() -> None:
    from app.account import prune_events

    with session_scope() as db:
        prune_events(db)


class Scheduler:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last: dict[str, float] = {}
        self.tasks = [
            ("fng", 3600, _fng),
            ("news", 900, _news),
            ("news_ai", 1800, _news_ai),
            ("autopilot", 60, autopilot_tick),
            ("prewarm", 6 * 3600, _prewarm),
            ("prune", 86400, _prune),
        ]

    def start(self) -> None:
        from app.services.optimizer import mark_stuck_runs

        if self._thread is not None and self._thread.is_alive():
            return
        mark_stuck_runs()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_now(self, name: str) -> None:
        """Marca a tarefa para rodar no próximo giro do laço."""
        self._last.pop(name, None)

    def _loop(self) -> None:
        if self._stop.wait(10):  # deixa o servidor terminar de subir
            return
        while not self._stop.is_set():
            for name, every, fn in self.tasks:
                if self._stop.is_set():
                    break
                if time.monotonic() - self._last.get(name, -1e12) < every:
                    continue
                self._last[name] = time.monotonic()
                try:
                    fn()
                except Exception as exc:
                    log.warning("Tarefa %s falhou: %s", name, exc)
            self._stop.wait(20)


scheduler = Scheduler()
