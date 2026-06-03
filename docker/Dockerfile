# ai-engineer-research app image — runs the deep researcher in a container (no host venv).
# deepagents requires Python >= 3.11.
#
# M0/M1: lean base deps only (deepagents + langchain-openai). M2 adds the web/rerank extras
# (crawl4ai + torch + playwright chromium) — flip the install line to ".[all]" and re-enable the
# playwright step below when you reach M2.
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
RUN pip install --upgrade pip && pip install -e .

# --- M2: uncomment for the full web/rerank stack ---
# RUN pip install -e ".[all]"
# Chromium + OS deps for Crawl4AI. Non-fatal: some networks block the Playwright CDN.
# RUN python -m playwright install --with-deps chromium || echo "WARN: chromium not installed"

# Runtime assets
COPY config ./config
COPY scripts ./scripts

# Default: print the M0 probe usage. Override the command per run.
CMD ["python", "scripts/m0_toolcall_probe.py", "--help"]
