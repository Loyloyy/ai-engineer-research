"""Hugging Face structured-API tools (huggingface.co is reachable). Model/dataset evidence.

Public HF Hub API via httpx — model/dataset metadata (downloads, likes, license, linked arxiv papers)
and model-card text. No auth needed for public repos. Graceful-degrade like the other tools.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_API = "https://huggingface.co/api"
_TIMEOUT = 20
_MAX_CARD_CHARS = 9000
_UA = "ai-engineer-research/0.1"


def _get(url: str, params: dict | None = None):
    import httpx

    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}) as c:
            r = c.get(url, params=params or {})
            r.raise_for_status()
            return r.json(), ""
    except Exception as e:  # noqa: BLE001
        logger.warning("hf API %s failed: %s", url, e)
        return None, f"{type(e).__name__}: {e}"


def _license(tags: list[str], card: dict | None) -> str:
    for t in tags or []:
        if t.startswith("license:"):
            return t.split(":", 1)[1]
    return (card or {}).get("license") or "?"


def _arxiv_ids(tags: list[str]) -> list[str]:
    return [t.split(":", 1)[1] for t in (tags or []) if t.startswith("arxiv:")]


@tool(parse_docstring=True)
def hf_search_models(query: str, max_results: int = 5) -> str:
    """Search Hugging Face models (ranked by downloads). Use to find models/implementations for a topic.

    Args:
        query: search terms, e.g. "bge embedding" or "llama guard".
        max_results: how many models to return (1-10).
    """
    max_results = max(1, min(int(max_results), 10))
    data, err = _get(f"{_API}/models", {"search": query, "sort": "downloads", "direction": "-1", "limit": max_results})
    if data is None:
        return f"[hf_search_models error: {err}]"
    if not data:
        return f"[hf_search_models: no models for {query!r}]"
    lines = [f"HF models for {query!r} (by downloads):"]
    for m in data[:max_results]:
        lines.append(
            f"- {m.get('id')}  ↓{m.get('downloads')}  ♥{m.get('likes')}  "
            f"{m.get('pipeline_tag') or '?'}  license={_license(m.get('tags', []), None)}\n"
            f"  https://huggingface.co/{m.get('id')}"
        )
    return "\n".join(lines)


@tool(parse_docstring=True)
def hf_model_card(model_id: str) -> str:
    """Fetch a model's metadata (downloads, likes, license, linked arxiv papers) + its model-card text.

    Args:
        model_id: e.g. "BAAI/bge-m3".
    """
    model_id = model_id.strip().strip("/")
    data, err = _get(f"{_API}/models/{model_id}")
    if data is None:
        return f"[hf_model_card error for {model_id}: {err}]"
    tags = data.get("tags", [])
    arxiv = _arxiv_ids(tags)
    meta = (
        f"{model_id}\n"
        f"downloads={data.get('downloads')} likes={data.get('likes')} "
        f"pipeline={data.get('pipeline_tag')} library={data.get('library_name')} "
        f"license={_license(tags, data.get('cardData'))} gated={data.get('gated')}\n"
        f"created={(data.get('createdAt') or '')[:10]} last_modified={(data.get('lastModified') or '')[:10]}\n"
        f"linked_papers(arxiv)={', '.join(arxiv) if arxiv else 'none'}\n"
        f"https://huggingface.co/{model_id}\n"
    )
    # The model card README is text/markdown (not JSON) → fetch as raw text.
    import httpx

    card_text = ""
    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True) as c:
            rr = c.get(f"https://huggingface.co/{model_id}/raw/main/README.md")
            if rr.status_code == 200:
                card_text = rr.text
    except Exception:  # noqa: BLE001
        pass
    if card_text:
        truncated = len(card_text) > _MAX_CARD_CHARS
        meta += "\n--- model card ---\n" + card_text[:_MAX_CARD_CHARS] + ("\n[...truncated...]" if truncated else "")
    return meta


@tool(parse_docstring=True)
def hf_search_datasets(query: str, max_results: int = 5) -> str:
    """Search Hugging Face datasets (ranked by downloads). Use to find eval/training data for a topic.

    Args:
        query: search terms, e.g. "mteb retrieval" or "instruction tuning".
        max_results: how many datasets to return (1-10).
    """
    max_results = max(1, min(int(max_results), 10))
    data, err = _get(f"{_API}/datasets", {"search": query, "sort": "downloads", "direction": "-1", "limit": max_results})
    if data is None:
        return f"[hf_search_datasets error: {err}]"
    if not data:
        return f"[hf_search_datasets: no datasets for {query!r}]"
    lines = [f"HF datasets for {query!r} (by downloads):"]
    for d in data[:max_results]:
        lines.append(f"- {d.get('id')}  ↓{d.get('downloads')}  ♥{d.get('likes')}\n  https://huggingface.co/datasets/{d.get('id')}")
    return "\n".join(lines)


HF_TOOLS = [hf_search_models, hf_model_card, hf_search_datasets]
