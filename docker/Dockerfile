# Trial image. Stage 1 matches CI (Node 22). Stage 2 is Python 3.12.
# fonts-noto-cjk installs NotoSansCJK-Regular.ttc on the path pdf_font.py
# already searches. That face covers everyday Chinese and circled numbers
# U+2460 through U+2473. The font file is not copied into the repository.

FROM node:22-alpine AS web
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
# esbuild's postinstall can hit ETXTBSY on Docker Desktop. One retry is enough.
RUN npm ci --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 \
    || (sleep 3 && npm ci --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000)
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends -o Acquire::Retries=5 \
        ca-certificates \
        curl \
        fonts-noto-cjk \
        openssl \
    && rm -rf /var/lib/apt/lists/* \
    && test -f /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY backend ./backend
COPY scripts ./scripts
COPY --from=web /src/apps/web/dist ./apps/web/dist

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin k12 \
    && mkdir -p /data/files /data/logs \
    && chown -R k12:k12 /data

USER k12
EXPOSE 8765
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
    CMD ["curl", "-fsS", "http://127.0.0.1:8765/health"]
CMD ["uvicorn", "backend.bootstrap.http_app:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log"]
