# syntax=docker/dockerfile:1.7

# ── Build stage ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the project source and install it
COPY src ./src
COPY README.md ./README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ── Runtime stage ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DB_PATH=/data/golf_scorecards.db \
    APP_ENV=production

WORKDIR /app

# Run as non-root
RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src ./src

# Mount point for Fly volume; created at image build time so the
# fallback path works even without a volume attached.
RUN mkdir -p /data && chown app:app /data

USER app
EXPOSE 8080

CMD ["uvicorn", "golf_scorecards.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
