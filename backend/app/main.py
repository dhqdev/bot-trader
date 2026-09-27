import logging
import mimetypes
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import api_router
from app.config import get_settings
from app.core.engine import manager, migrate_to_okx
from app.db import init_db, session_scope
from app.services.scheduler import scheduler

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por notícia/feed baixado polui o log
log = logging.getLogger("bot_trader")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db()
    with session_scope() as db:
        moved = migrate_to_okx(db)  # a Binance foi removida: bots antigos passam para a OKX
    if moved:
        log.info("%s bot(s) migrado(s) da Binance para a OKX.", moved)
    if settings.engine_autostart:
        manager.start()
        log.info("Motor iniciado (%s bots ativos).", manager.running_count())
    if settings.scheduler_enabled:
        scheduler.start()
    yield
    scheduler.stop()
    manager.shutdown()


settings = get_settings()
app = FastAPI(
    title="Bot Trader",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY = 1_000_000
MAX_BODY_CHAT = 5_000_000  # conversa com a IA pode levar o resultado de um backtest

# Só scripts e estilos do próprio site; nada de iframes, plugins ou envio de formulários para fora.
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def _origin_allowed(request: Request) -> bool:
    """Proteção contra CSRF: ações que mudam algo só podem vir das páginas do próprio sistema.

    O cookie de sessão já é SameSite=Strict; isto cobre também subdomínios
    (ex.: outro serviço em *.tekvosoft.com), que o navegador considera "mesmo site".
    """
    origin = request.headers.get("origin")
    if origin:
        if origin in settings.cors_origin_list:
            return True
        return urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
    site = request.headers.get("sec-fetch-site")
    return site in (None, "same-origin", "none")


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        if request.method in UNSAFE_METHODS and not _origin_allowed(request):
            return JSONResponse({"detail": "Origem da requisição não permitida."}, status_code=403)
        length = request.headers.get("content-length")
        limit = MAX_BODY_CHAT if path == "/api/ai/chat" else MAX_BODY
        if length and length.isdigit() and int(length) > limit:
            return JSONResponse({"detail": "Requisição grande demais."}, status_code=413)

    response = await call_next(request)

    headers = response.headers
    if path.startswith("/api/"):
        headers.setdefault("Cache-Control", "no-store")
    elif path.startswith("/assets/"):
        # nomes com hash: o conteúdo nunca muda
        headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif path in ("/sw.js", "/manifest.webmanifest") or "text/html" in headers.get("content-type", ""):
        # service worker, manifesto e páginas sempre revalidados, para as atualizações chegarem
        headers.setdefault("Cache-Control", "no-cache")
    if not path.startswith("/api/docs"):
        headers.setdefault("Content-Security-Policy", CSP)
    if settings.cookie_secure:
        headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "same-origin")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    return response


app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Erro não tratado: %s", exc)
    return JSONResponse({"detail": "Erro interno do servidor."}, status_code=500)


# Frontend compilado (produção): o FastAPI serve a SPA na mesma origem da API.
dist = settings.frontend_dist
if dist.exists():
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):
            return FileResponse(file)
        return FileResponse(dist / "index.html")
