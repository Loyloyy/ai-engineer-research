#!/usr/bin/env python3
"""Egress probe — map which domains are reachable vs blocked from inside the container.

The server runs behind a hard egress allowlist (most sites TLS-reset). This maps reality across the
domains a code/AI researcher actually needs, so we can (a) appeal a precise short list and (b) steer
the agent toward reachable, high-value sources. All targets are public; this only does GETs.

    docker-compose run --rm app python scripts/egress_probe.py

Classifications:
  OK <code>   reachable (any HTTP status, incl. 403/404 — the TLS handshake completed)
  RESET       connection reset by peer  -> blocked by the egress firewall
  DNS_FAIL    name resolution failed    -> DNS blocked for that host
  TIMEOUT     no response in time       -> likely silently dropped
  TLS_ERR     TLS/cert problem ;  ERROR  other
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# (category, url). Real resources where possible, not just roots.
TARGETS: list[tuple[str, str]] = [
    # --- code forges + raw hosts ---
    ("forge", "https://github.com/langchain-ai/deepagents"),
    ("forge", "https://raw.githubusercontent.com/langchain-ai/deepagents/main/README.md"),
    ("forge", "https://api.github.com/repos/langchain-ai/deepagents"),
    ("forge", "https://codeload.github.com/langchain-ai/deepagents/zip/refs/heads/main"),
    ("forge", "https://objects.githubusercontent.com/"),
    ("forge", "https://gist.githubusercontent.com/"),
    ("forge", "https://user-images.githubusercontent.com/"),
    ("forge", "https://gitlab.com/gitlab-org/gitlab"),
    ("forge", "https://bitbucket.org/"),
    ("forge", "https://codeberg.org/"),
    ("forge", "https://sourceforge.net/"),
    ("forge", "https://git.kernel.org/"),
    ("forge", "https://hf.co/"),
    # --- github pages / readthedocs (where lots of OSS docs live) ---
    ("oss-docs", "https://langchain-ai.github.io/langgraph/"),
    ("oss-docs", "https://requests.readthedocs.io/en/latest/"),
    ("oss-docs", "https://pip.pypa.io/en/stable/"),
    ("oss-docs", "https://docs.pydantic.dev/latest/"),
    ("oss-docs", "https://readthedocs.org/"),
    ("oss-docs", "https://docs.vllm.ai/en/latest/"),
    ("oss-docs", "https://sgl-project.github.io/"),
    ("oss-docs", "https://www.gradio.app/"),
    ("oss-docs", "https://docs.streamlit.io/"),
    # --- package registries ---
    ("pkg", "https://pypi.org/pypi/langchain/json"),
    ("pkg", "https://files.pythonhosted.org/"),
    ("pkg", "https://registry.npmjs.org/react"),
    ("pkg", "https://www.npmjs.com/package/react"),
    ("pkg", "https://crates.io/api/v1/crates/serde"),
    ("pkg", "https://static.crates.io/"),
    ("pkg", "https://pkg.go.dev/"),
    ("pkg", "https://proxy.golang.org/"),
    ("pkg", "https://anaconda.org/"),
    ("pkg", "https://conda.anaconda.org/"),
    ("pkg", "https://rubygems.org/"),
    ("pkg", "https://repo1.maven.org/maven2/"),
    ("pkg", "https://www.nuget.org/"),
    # --- container registries ---
    ("container", "https://hub.docker.com/"),
    ("container", "https://registry-1.docker.io/"),
    ("container", "https://ghcr.io/"),
    ("container", "https://quay.io/"),
    ("container", "https://catalog.ngc.nvidia.com/"),
    # --- AI vendor docs / APIs ---
    ("ai-vendor", "https://huggingface.co/BAAI/bge-m3"),
    ("ai-vendor", "https://huggingface.co/api/models/BAAI/bge-m3"),
    ("ai-vendor", "https://huggingface.co/papers"),
    ("ai-vendor", "https://huggingface.co/docs/transformers/index"),
    ("ai-vendor", "https://platform.openai.com/docs/overview"),
    ("ai-vendor", "https://docs.anthropic.com/en/home"),
    ("ai-vendor", "https://ai.google.dev/"),
    ("ai-vendor", "https://docs.mistral.ai/"),
    ("ai-vendor", "https://docs.cohere.com/"),
    ("ai-vendor", "https://ollama.com/"),
    ("ai-vendor", "https://openrouter.ai/docs"),
    ("ai-vendor", "https://groq.com/"),
    ("ai-vendor", "https://www.together.ai/"),
    ("ai-vendor", "https://python.langchain.com/docs/introduction/"),
    ("ai-vendor", "https://docs.langchain.com/oss/python/deepagents/overview"),
    ("ai-vendor", "https://developer.nvidia.com/"),
    # --- vector DBs / infra ---
    ("infra", "https://milvus.io/docs"),
    ("infra", "https://qdrant.tech/documentation/"),
    ("infra", "https://weaviate.io/developers/weaviate"),
    ("infra", "https://docs.trychroma.com/"),
    ("infra", "https://docs.pinecone.io/"),
    ("infra", "https://redis.io/docs/latest/"),
    # --- general docs ---
    ("docs", "https://docs.python.org/3/"),
    ("docs", "https://developer.mozilla.org/en-US/"),
    ("docs", "https://pytorch.org/docs/stable/index.html"),
    ("docs", "https://download.pytorch.org/whl/torch/"),
    ("docs", "https://www.tensorflow.org/"),
    ("docs", "https://scikit-learn.org/stable/"),
    ("docs", "https://numpy.org/doc/stable/"),
    ("docs", "https://pandas.pydata.org/docs/"),
    ("docs", "https://fastapi.tiangolo.com/"),
    ("docs", "https://kubernetes.io/docs/home/"),
    ("docs", "https://docs.docker.com/"),
    # --- papers / research ---
    ("papers", "https://arxiv.org/abs/1706.03762"),
    ("papers", "https://export.arxiv.org/abs/1706.03762"),
    ("papers", "https://ar5iv.labs.arxiv.org/html/1706.03762"),
    ("papers", "https://www.semanticscholar.org/"),
    ("papers", "https://api.semanticscholar.org/graph/v1/paper/search?query=transformer"),
    ("papers", "https://aclanthology.org/"),
    ("papers", "https://openreview.net/"),
    ("papers", "https://paperswithcode.com/"),
    ("papers", "https://proceedings.mlr.press/"),
    ("papers", "https://openaccess.thecvf.com/"),
    ("papers", "https://dblp.org/"),
    ("papers", "https://www.biorxiv.org/"),
    # --- Q&A / community ---
    ("community", "https://stackoverflow.com/questions"),
    ("community", "https://api.stackexchange.com/2.3/info?site=stackoverflow"),
    ("community", "https://news.ycombinator.com/"),
    ("community", "https://www.reddit.com/r/LangChain/"),
    ("community", "https://discuss.huggingface.co/"),
    ("community", "https://discuss.pytorch.org/"),
    ("community", "https://lobste.rs/"),
    # --- knowledge ---
    ("knowledge", "https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)"),
    ("knowledge", "https://www.wikidata.org/"),
    # --- search ---
    ("search", "https://www.google.com/"),
    ("search", "https://www.bing.com/"),
    ("search", "https://duckduckgo.com/"),
    ("search", "https://html.duckduckgo.com/html/"),
    ("search", "https://search.brave.com/"),
    ("search", "https://scholar.google.com/"),
    # --- ML platforms ---
    ("ml-platform", "https://www.kaggle.com/"),
    ("ml-platform", "https://wandb.ai/"),
    ("ml-platform", "https://replicate.com/"),
    ("ml-platform", "https://modal.com/"),
    ("ml-platform", "https://lmarena.ai/"),
    # --- blogs / news (high-value) ---
    ("blogs", "https://github.blog/"),
    ("blogs", "https://openai.com/news/"),
    ("blogs", "https://www.anthropic.com/news"),
    ("blogs", "https://blog.langchain.dev/"),
    ("blogs", "https://huggingface.co/blog"),
    ("blogs", "https://pytorch.org/blog/"),
    ("blogs", "https://medium.com/"),
    ("blogs", "https://substack.com/"),
    ("blogs", "https://dev.to/"),
    # --- CDNs / assets ---
    ("cdn", "https://cdn.jsdelivr.net/"),
    ("cdn", "https://unpkg.com/"),
    ("cdn", "https://cdnjs.cloudflare.com/"),
    ("cdn", "https://raw.githack.com/"),
    ("cdn", "https://cdn.playwright.dev/"),
    # --- archives / reader proxies (potential escape hatches for blocked pages) ---
    ("escape-hatch", "https://web.archive.org/web/2id_/https://arxiv.org/abs/1706.03762"),
    ("escape-hatch", "https://archive.org/"),
    ("escape-hatch", "https://r.jina.ai/https://github.com/langchain-ai/deepagents"),
]

_UA = "Mozilla/5.0 (compatible; ai-engineer-research-egress-probe/0.1)"
_TIMEOUT = 6
_WORKERS = 16


def classify(url: str) -> tuple[str, str]:
    import httpx

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers={"User-Agent": _UA}) as c:
            r = c.get(url)
        return "OK", str(r.status_code)
    except Exception as e:  # noqa: BLE001 — we WANT to bucket every failure mode
        msg = f"{type(e).__name__}: {e}".lower()
        if any(s in msg for s in ("name resolution", "name or service not known", "nodename", "[errno -3]", "[errno -2]", "getaddrinfo")):
            return "DNS_FAIL", type(e).__name__
        if any(s in msg for s in ("reset by peer", "errno 104", "connection reset")):
            return "RESET", type(e).__name__
        if "timed out" in msg or "timeout" in msg:
            return "TIMEOUT", type(e).__name__
        if "ssl" in msg or "certificate" in msg or "tls" in msg:
            return "TLS_ERR", type(e).__name__
        return "ERROR", f"{type(e).__name__}: {str(e)[:50]}"


def main() -> int:
    print(f"Probing {len(TARGETS)} targets ({_WORKERS} concurrent, {_TIMEOUT}s timeout)...\n")
    results: dict[tuple[str, str], tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
        futs = {ex.submit(classify, url): (cat, url) for cat, url in TARGETS}
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()

    # Print grouped by category, in declaration order.
    last_cat = None
    for cat, url in TARGETS:
        if cat != last_cat:
            print(f"\n--- {cat} ---")
            last_cat = cat
        result, detail = results[(cat, url)]
        print(f"  {result:<9} {url}")

    by_result: dict[str, int] = {}
    for r, _ in results.values():
        by_result[r] = by_result.get(r, 0) + 1
    print("\n==== summary ====")
    for k in sorted(by_result):
        print(f"  {k:<9} {by_result[k]}")
    reachable = by_result.get("OK", 0)
    print(f"\n  reachable: {reachable}/{len(TARGETS)}")

    print("\n==== REACHABLE (rely on these) ====")
    for cat, url in TARGETS:
        if results[(cat, url)][0] == "OK":
            print(f"  [{cat}] {url}")
    print("\n==== BLOCKED (candidates to appeal, by value) ====")
    for cat, url in TARGETS:
        if results[(cat, url)][0] != "OK":
            print(f"  {results[(cat, url)][0]:<9} [{cat}] {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
