# Tayf Studio backend — production image (multi-stage, non-root).
# NOTE: the compose stack and CI build/prove this image; Termux users keep
# using `scripts/dev.sh` (plain uvicorn) which stays the primary target.

# --- stage 1: wheels ---------------------------------------------------------
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt requirements-s3.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt -r requirements-s3.txt

# --- stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim
# ffmpeg is REQUIRED for real MP4 composition (services/compose.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 tayf
WORKDIR /app
COPY --from=build /wheels /wheels
COPY requirements.txt requirements-s3.txt ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -r requirements.txt -r requirements-s3.txt \
    && rm -rf /wheels

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Writable home for the SQLite DB + local storage when volumes are not mounted.
RUN mkdir -p /app/data/storage && chown -R tayf:tayf /app
USER tayf

ENV APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"

# Migrations run on every start (idempotent), then the API serves.
CMD ["sh", "-c", "alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
