"""Notícias: leitura dos feeds, moedas citadas, classificação e trava no motor."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from defusedxml import EntitiesForbidden
from sqlalchemy import delete, select

from app.core import newsguard
from app.core.engine import BotService
from app.core.exchange import PaperTrader
from app.db import session_scope
from app.models import Bot, BotEvent, NewsItem, Position, User, utcnow
from app.security import hash_password
from app.services import news

from .conftest import FakeMarket
from .test_engine import scripted  # noqa: F401  (fixture)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>Feed</title>
<item><title>Hackers drain $40M from Solana DEX in exploit</title>
<link>https://news.example/a?utm_source=rss&amp;id=7</link>
<description>&lt;p&gt;Attackers &lt;b&gt;exploited&lt;/b&gt; a bug.&lt;/p&gt;</description>
<pubDate>Sat, 26 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Bitcoin atinge nova máxima histórica</title><link>https://news.example/b</link>
<dc:date>2026-09-26T11:30:00Z</dc:date></item>
<item><title></title><link>https://news.example/sem-titulo</link></item>
<item><title>Link inválido</title><link>javascript:alert(1)</link></item>
</channel></rss>""".encode("utf-8")

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry><title>Ethereum upgrade goes live</title><link rel="alternate" href="https://atom.example/eth"/>
<published>2026-09-25T08:00:00Z</published><summary>Pectra is live.</summary></entry>
</feed>"""

BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<rss><channel><item><title>&lol2;</title></item></channel></rss>"""


def test_parse_rss_and_atom():
    items = news.parse_feed(RSS, "Teste", "en")
    assert [i["title"] for i in items] == ["Hackers drain $40M from Solana DEX in exploit", "Bitcoin atinge nova máxima histórica"]
    first = items[0]
    assert first["url"] == "https://news.example/a?id=7"  # sem parâmetros de rastreio
    assert first["summary"] == "Attackers exploited a bug."  # sem HTML
    assert first["published_at"].isoformat().startswith("2026-09-26T10:00")
    assert items[1]["published_at"].isoformat().startswith("2026-09-26T11:30")
    atom = news.parse_feed(ATOM, "Atom", "en")
    assert atom[0]["url"] == "https://atom.example/eth" and atom[0]["summary"] == "Pectra is live."


def test_malicious_xml_is_refused():
    with pytest.raises(EntitiesForbidden):
        news.parse_feed(BOMB, "x", "en")


def test_asset_detection_and_keywords():
    assert news.detect_assets("Hackers drain $40M from Solana-based DEX") == ["SOL"]
    assert news.detect_assets("Fed rate cut lifts crypto market; BTC and ETH rally") == ["BTC", "ETH", "MARKET"]
    assert news.detect_assets("Binance suspende saques após ataque hacker") == ["MARKET"]
    assert news.detect_assets("Binance to delist five tokens") == []  # deslistagem de um token não é o mercado todo
    assert news.detect_assets("Worldcoin WLD jumps", extra={"WLD"}) == ["WLD"]
    assert news.detect_assets("sol e chuva no fim de semana") == []  # "sol" minúsculo não é a moeda
    bad = news.keyword_classify("Hackers drain $40M from Solana DEX in exploit")
    assert bad["impact"] == "high" and bad["sentiment"] < -0.5 and bad["category"] == "security"
    good = news.keyword_classify("Bitcoin dispara e atinge máxima histórica")
    assert good["sentiment"] > 0.3 and good["impact"] != "high"


@pytest.fixture
def clean_news():
    with session_scope() as db:
        db.execute(delete(NewsItem))
    yield
    with session_scope() as db:
        db.execute(delete(NewsItem))


def test_collect_dedupes_and_survives_broken_feed(clean_news):
    feeds = [news.Feed("A", "https://a", "en"), news.Feed("B", "https://b", "en")]

    def fetcher(feed):
        if feed.name == "B":
            raise ConnectionError("fora do ar")
        return news.parse_feed(RSS, feed.name, feed.lang)

    first = news.collect(feeds, fetcher)
    assert first["added"] == 2 and first["serious"] == 1 and "B" in first["errors"]
    assert news.collect(feeds, fetcher)["added"] == 0  # mesma URL não entra de novo
    with session_scope() as db:
        item = db.scalar(select(NewsItem).where(NewsItem.url == "https://news.example/a?id=7"))
        assert item.assets == ["SOL"] and item.impact == "high" and item.classified_by == "keywords"


class FakeAI:
    def __init__(self, reply: dict):
        self.reply = reply
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", model=kwargs["model"], content=[SimpleNamespace(type="text", text=json.dumps(self.reply))])


def _add_news(title: str, assets: list[str], sentiment: float, impact: str = "high", hours_ago: float = 1, by: str = "keywords", source: str = "Teste") -> int:
    with session_scope() as db:
        item = NewsItem(url=f"https://n.example/{source}/{title}", source=source, title=title, published_at=utcnow() - timedelta(hours=hours_ago),
                        assets=assets, sentiment=sentiment, impact=impact, classified_by=by)  # fmt: skip
        db.add(item)
        db.flush()
        return item.id


def test_ai_classification_validates_output(clean_news):
    a = _add_news("Rumor sobre SOL", ["SOL"], 0.0, "low")
    b = _add_news("Outra notícia", [], 0.0, "low")
    reply = {"items": [
        {"id": a, "assets": ["sol", "MARKET", "not a ticker!"], "sentiment": -3.5, "impact": "high", "category": "security", "summary_pt": "<b>Hack</b> na rede"},
        {"id": 999999, "assets": ["BTC"], "sentiment": 1, "impact": "low", "category": "other", "summary_pt": "não existe"},
    ]}  # fmt: skip
    client = FakeAI(reply)
    assert news.classify_with_ai("sk-test", client=client) == 1
    prompt = client.calls[0]["messages"][0]["content"]
    assert "<noticias>" in prompt and "Rumor sobre SOL" in prompt
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"
    with session_scope() as db:
        item_a, item_b = db.get(NewsItem, a), db.get(NewsItem, b)
        assert item_a.assets == ["SOL", "MARKET"] and item_a.sentiment == -1.0 and item_a.classified_by == "ai"
        assert item_a.ai_summary == "Hack na rede"
        assert item_b.classified_by == "keywords*"  # não volta para a fila
    assert news.classify_with_ai("sk-test", client=client) == 0  # nada pendente: não chama a IA de novo
    assert len(client.calls) == 1


def test_news_guard_rules(clean_news):
    with session_scope() as db:
        assert newsguard.entry_block(db, "SOL", "block_entries", 12) is None
    # só palavras-chave e uma fonte: pode ser alarme falso ("Hack VC" é nome de fundo), não bloqueia
    _add_news("Former Hack VC partner dies", ["SOL"], -0.8, source="Cointelegraph")
    with session_scope() as db:
        assert newsguard.entry_block(db, "SOL", "block_entries", 12) is None
    # duas fontes diferentes falando de algo grave com a mesma moeda: bloqueia
    _add_news("Exploit na Solana", ["SOL"], -0.8, source="Decrypt")
    _add_news("Notícia velha", ["ETH"], -0.9, hours_ago=30, by="ai")
    _add_news("Notícia leve", ["ETH"], -0.2, by="ai")
    with session_scope() as db:
        assert newsguard.entry_block(db, "SOL", "block_entries", 12).title == "Exploit na Solana"
        assert newsguard.entry_block(db, "SOL", "off", 12) is None
        assert newsguard.entry_block(db, "ETH", "block_entries", 12) is None  # velha ou fraca
    _add_news("Binance congela saques", ["MARKET"], -0.9, source="CoinDesk")
    _add_news("Binance congela saques!", ["MARKET"], -0.9, source="The Block")
    with session_scope() as db:
        assert newsguard.entry_block(db, "ETH", "block_entries", 12).title.startswith("Binance congela saques")
        # saída só com notícia confirmada pela IA e publicada depois da compra
        assert newsguard.exit_trigger(db, "ETH", "block_and_exit", 12, utcnow() - timedelta(hours=5)) is None
    _add_news("IA confirma: hack", ["ETH"], -0.9, by="ai")
    with session_scope() as db:
        assert newsguard.exit_trigger(db, "ETH", "block_and_exit", 12, utcnow() - timedelta(hours=5)).title == "IA confirma: hack"
        assert newsguard.exit_trigger(db, "ETH", "block_entries", 12, utcnow() - timedelta(hours=5)) is None
        assert newsguard.exit_trigger(db, "ETH", "block_and_exit", 12, utcnow()) is None  # saiu antes da compra


def _bot(risk: dict) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == "news@test.dev"))
        if user is None:
            user = User(email="news@test.dev", name="N", password_hash=hash_password("x" * 8))
            db.add(user)
            db.flush()
        bot = Bot(user_id=user.id, name="SOL", symbol="SOLUSDT", base_asset="SOL", quote_asset="USDT", interval="1h", strategy="scripted",
                  strategy_params={}, risk={"order_size_quote": 100, "cooldown_bars": 0, "sentiment_filter": "off", **risk}, mode="paper",
                  paper_initial_balance=1000, paper_balance=1000, status="running")  # fmt: skip
        db.add(bot)
        db.flush()
        return bot.id


def _step(bot_id: int, market: FakeMarket, evaluate: bool = False) -> None:
    with session_scope() as db:
        bot = db.get(Bot, bot_id)
        if evaluate:
            bot.last_candle_time = None
        BotService(db, bot, market, PaperTrader(market, fee_pct=0.1, slippage_pct=0)).step()


def test_engine_blocks_entry_on_bad_news(scripted, clean_news):  # noqa: F811
    _add_news("Exploit drena rede Solana", ["SOL"], -0.9, by="ai")
    bot_id = _bot({"news_guard": "block_entries"})
    _step(bot_id, FakeMarket())
    with session_scope() as db:
        assert db.scalar(select(Position).where(Position.bot_id == bot_id)) is None
        msgs = [e.message for e in db.scalars(select(BotEvent).where(BotEvent.bot_id == bot_id))]
        assert any("notícia negativa" in m and "Exploit drena" in m for m in msgs)
        market = db.get(Bot, bot_id).last_signal["market"]
        assert market["blocks_entry"] is True and market["news_block"]["title"] == "Exploit drena rede Solana"


def test_engine_exits_on_confirmed_bad_news(scripted, clean_news):  # noqa: F811
    bot_id = _bot({"news_guard": "block_and_exit"})
    market = FakeMarket()
    _step(bot_id, market)
    with session_scope() as db:
        pos = db.scalar(select(Position).where(Position.bot_id == bot_id))
        assert pos.status == "open"
    _add_news("SEC processa fundação Solana", ["SOL"], -0.9, hours_ago=0, by="ai")
    _step(bot_id, market)
    with session_scope() as db:
        pos = db.scalar(select(Position).where(Position.bot_id == bot_id))
        assert pos.status == "closed" and pos.exit_reason == "news"

