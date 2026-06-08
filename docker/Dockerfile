# ai-engineer-research app image — runs the deep researcher in a container (no host venv).
# deepagents requires Python >= 3.11.
#
# M1: base + web (httpx + trafilatura, the default browserless fetch_url backend) + browser
# (crawl4ai, the optional JS-rendering backend selected via AER_FETCH_BACKEND). M2 adds rerank/
# vault/ui — flip to ".[all]". Set --build-arg WITH_BROWSER=0 to skip the heavy browser path.
FROM python:3.11-slim

ARG WITH_BROWSER=1

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
# web = default fetch backend; obs = optional Langfuse tracing (lazy-imported, enabled via AER_TRACING).
RUN pip install --upgrade pip && pip install -e ".[web,obs]"

# Optional browser backend (crawl4ai + Playwright chromium). The chromium download CDN must be
# reachable from the build environment or the install step fails (non-fatal: fetch_url then stays on
# the http backend). To enable: ensure the CDN host(s) shown by `playwright install --dry-run chromium`
# are reachable, then rebuild and set AER_FETCH_BACKEND=browser (or auto) in .env.
RUN if [ "$WITH_BROWSER" = "1" ]; then \
        pip install -e ".[browser]" \
        && (python -m playwright install --with-deps chromium \
            || echo "WARN: chromium not installed (CDN unreachable?); fetch_url stays on the http backend"); \
    fi

# Runtime assets
COPY config ./config
COPY scripts ./scripts

# Default: print the M0 probe usage. Override the command per run.
CMD ["python", "scripts/m0_toolcall_probe.py", "--help"]
