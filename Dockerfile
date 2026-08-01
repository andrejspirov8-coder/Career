FROM python:3.11-slim-bookworm

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV NODE_VERSION=22.22.2
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1 \
    && node --version && npm --version

ENV UV_VERSION=0.6.10
RUN curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-$(uname -m)-unknown-linux-gnu.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv \
    && uv --version

WORKDIR /app

COPY job-search/pyproject.toml job-search/uv.lock job-search/.python-version /app/job-search/
RUN uv sync --locked --no-dev --no-group supabase

COPY job-search/dashboard/package.json job-search/dashboard/package-lock.json /app/job-search/dashboard/
RUN cd /app/job-search/dashboard && npm ci --include=dev

COPY job-search/src /app/job-search/src
COPY job-search/dashboard /app/job-search/dashboard
COPY job-search/cv /app/job-search/cv
COPY job-search/config /app/job-search/config
COPY job-search/tools /app/job-search/tools
COPY job-search/scripts /app/job-search/scripts

RUN cd /app/job-search/dashboard && npm run build

EXPOSE 8000

WORKDIR /app/job-search
CMD ["uv", "run", "python", "src/career_job_search/api/main.py"]
