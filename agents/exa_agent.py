"""
Agent 2 — exa_agent.py (TinyFish backend)
Uses the TinyFish automation API (https://agent.tinyfish.ai) to run goal-directed
web research for each query cluster, writing results to research/exa_results.json.

API call format (SSE endpoint, consumed synchronously):
  POST https://agent.tinyfish.ai/v1/automation/run-sse
  X-API-Key: <TINYFISH_API_KEY>
  Content-Type: application/json
  Body: {"url": "<seed_url>", "goal": "<extraction_goal>"}

The SSE stream emits lines of the form "data: <json>".  The agent collects all
data lines, merges any partial JSON arrays/objects, and normalises them into the
same result schema used by the rest of the pipeline.
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

TINYFISH_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"

# Academic / financial seed URLs paired with IFRS research topics.
# Each query is sent as a "goal" against the most relevant seed URL.
CLUSTER_SEED_URLS: dict[str, str] = {
    "background_ifrs": "https://www.ifrs.org/issued-standards/list-of-standards/",
    "going_concern": "https://www.iaasb.org/publications/isa-570-revised-going-concern",
    "banking_stability": "https://www.bis.org/publ/work.htm",
    "union_bank_case_study": "https://www.unionbankng.com/investor-relations/",
    "literature_gaps": "https://ssrn.com/en/",
    "theoretical_framework": "https://ssrn.com/en/",
}

DEFAULT_SEED_URL = "https://ssrn.com/en/"


def _parse_sse_response(raw_text: str) -> list[dict]:
    """
    Parse SSE stream text into a list of result dicts.

    Each non-empty "data:" line is attempted as JSON.  Arrays are flattened;
    plain objects are wrapped.  Non-JSON data lines are stored as plain text
    entries so no information is lost.
    """
    results: list[dict] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, list):
                results.extend(parsed)
            elif isinstance(parsed, dict):
                results.append(parsed)
            else:
                results.append({"raw": str(parsed)})
        except json.JSONDecodeError:
            results.append({"raw": payload})
    return results


def _normalise(item: dict, query: str) -> dict:
    """Map a TinyFish result dict to the pipeline's canonical schema."""
    return {
        "source": item.get("url", item.get("link", item.get("source", ""))),
        "title": item.get("title", item.get("name", "")),
        "published_date": item.get(
            "published_date", item.get("date", item.get("posted", ""))
        ),
        "text": item.get("text", item.get("content", item.get("raw", ""))),
        "highlights": item.get("highlights", []),
        "query": query,
        "agent": "tinyfish",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def search_tinyfish(query: str, seed_url: str) -> list[dict]:
    """
    Run a TinyFish automation goal and return normalised result dicts.

    The endpoint streams SSE; we request it with stream=True and consume all
    chunks before parsing so the retry decorator can handle transient failures.
    """
    api_key = os.environ["TINYFISH_API_KEY"]
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body = {
        "url": seed_url,
        "goal": (
            f"Search for academic and financial information about: {query}. "
            "Extract the most relevant results. For each result return: "
            "title, url, published_date, and a text summary of up to 600 words. "
            "Return as a JSON array."
        ),
    }

    response = requests.post(
        TINYFISH_URL, headers=headers, json=body, stream=True, timeout=120
    )
    response.raise_for_status()

    raw_text = response.text
    items = _parse_sse_response(raw_text)
    return [_normalise(item, query) for item in items]


def main() -> None:
    queries_path = Path("research/queries.json")
    if not queries_path.exists():
        raise FileNotFoundError(f"{queries_path} not found — run orchestrator first")

    data = json.loads(queries_path.read_text())
    clusters: dict[str, list[str]] = data["query_clusters"]

    all_results: list[dict] = []

    for cluster_key, queries in clusters.items():
        seed_url = CLUSTER_SEED_URLS.get(cluster_key, DEFAULT_SEED_URL)
        print(
            f"[tinyfish_agent] Searching cluster: {cluster_key} "
            f"({len(queries)} queries, seed={seed_url})"
        )
        for query in queries:
            try:
                results = search_tinyfish(query, seed_url)
                for r in results:
                    r["cluster"] = cluster_key
                all_results.extend(results)
                print(f"  ✓ '{query[:60]}' → {len(results)} results")
            except Exception as exc:
                print(f"  ✗ '{query[:60]}' → ERROR: {exc}")
            time.sleep(0.5)

    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    output_path = research_dir / "exa_results.json"
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"[tinyfish_agent] Done. {len(all_results)} results written to {output_path}")


if __name__ == "__main__":
    main()
