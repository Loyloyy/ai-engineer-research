# ai-engineer-research app image — runs the deep researcher in a container (no host venv).
# deepagents requires Python >= 3.11.
#
# M1: base + web extras (httpx for search, crawl4ai + playwright chromium for fetch_url).
# M2 adds rerank/vault/ui — flip the install to ".[all]" then.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (better layer caching)
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[web]"

# Chromium + OS deps for Crawl4AI's fetch_url. Non-fatal: some networks block the Playwright
# CDN — if so the build still succeeds; fetch_url then degrades to "could not retrieve" and the
# run continues on search snippets. (M2: switch the install above to ".[all]".)
RUN python -m playwright install --with-deps chromium || echo "WARN: chromium not installed; fetch_url will degrade"

# Runtime assets
COPY config ./config
COPY scripts ./scripts

# Default: print the M0 probe usage. Override the command per run.
CMD ["python", "scripts/m0_toolcall_probe.py", "--help"]
