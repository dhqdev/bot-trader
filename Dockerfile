# ---- 1) compila o frontend ----
# roda na plataforma nativa do build (o resultado é HTML/JS, igual para amd64 e arm64)
FROM --platform=$BUILDPLATFORM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2) backend + frontend compilado, numa única imagem ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BT_ENV=production \
    BT_FRONTEND_DIST=/app/frontend/dist

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=web /web/dist /app/frontend/dist

RUN useradd --create-home --uid 1000 bot && mkdir -p /app/backend/data && chown -R bot:bot /app/backend/data
USER bot

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Um único worker: o motor dos bots roda dentro do processo da API.
# Mais de um worker duplicaria os bots (e as ordens).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
