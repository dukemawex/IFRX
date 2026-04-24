"""
Agent 2 — exa_agent.py
Exa / TinyFish neural academic search.
Reads research/queries.json, searches each query, writes research/exa_results.json.
"""

import json
import os
import time
from pathlib import Path

from exa_py import Exa
from tenacity import retry, stop_after_attempt, wait_exponential

INCLUDE_DOMAINS = [
    "scholar.google.com",
    "ssrn.com",
    "researchgate.net",
    "jstor.org",
    "emerald.com",
    "tandfonline.com",
    "cbn.gov.ng",
    "unionbankng.com",
    "sec.gov.ng",
    "ifrs.org",
    "iasb.org",
    "bis.org",
]

client = Exa(api_key=os.environ["EXA_API_KEY"])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def search_exa(query: str, num_results: int = 8) -> list[dict]:
    """Search Exa and return a normalised list of result dicts."""
    response = client.search_and_contents(
        query,
        num_results=num_results,
        use_autoprompt=True,
        text={"max_characters": 3000},
        highlights={"num_sentences": 4, "highlights_per_url": 2},
        include_domains=INCLUDE_DOMAINS,
        category="research paper",
    )

    results = []
    for item in response.results:
        text_content = ""
        if hasattr(item, "text") and item.text:
            text_content = item.text

        highlights = []
        if hasattr(item, "highlights") and item.highlights:
            highlights = item.highlights

        results.append(
            {
                "source": getattr(item, "url", ""),
                "title": getattr(item, "title", ""),
                "published_date": getattr(item, "published_date", ""),
                "text": text_content,
                "highlights": highlights,
                "query": query,
                "agent": "exa",
            }
        )
    return results


def main() -> None:
    queries_path = Path("research/queries.json")
    if not queries_path.exists():
        raise FileNotFoundError(f"{queries_path} not found — run orchestrator first")

    data = json.loads(queries_path.read_text())
    clusters: dict[str, list[str]] = data["query_clusters"]

    all_results: list[dict] = []

    for cluster_key, queries in clusters.items():
        print(f"[exa_agent] Searching cluster: {cluster_key} ({len(queries)} queries)")
        for query in queries:
            try:
                results = search_exa(query)
                for r in results:
                    r["cluster"] = cluster_key
                all_results.extend(results)
                print(f"  ✓ '{query[:60]}' → {len(results)} results")
            except Exception as exc:
                print(f"  ✗ '{query[:60]}' → ERROR: {exc}")
            time.sleep(0.5)

    output_path = Path("research/exa_results.json")
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"[exa_agent] Done. {len(all_results)} results written to {output_path}")


if __name__ == "__main__":
    main()
