FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

ENV UV_CACHE_DIR=/home/vscode/.cache/uv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && uv pip install --system ruff==0.16.0

WORKDIR /workspace
