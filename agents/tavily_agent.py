"""
Agent 3 — tavily_agent.py
Tavily live web + finance search.
Reads research/queries.json, searches each query, writes research/tavily_results.json.
"""

import json
import os
import time
from pathlib import Path

from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

# Clusters that should use topic="finance" in Tavily search
FINANCE_CLUSTERS = {"background_ifrs", "banking_stability", "union_bank_case_study"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def search_tavily(query: str, topic: str = "general") -> list[dict]:
    """Search Tavily and return a normalised list of result dicts."""
    response = client.search(
        query,
        search_depth="advanced",
        max_results=8,
        include_answer=True,
        include_raw_content=True,
        topic=topic,
    )

    results = []
    answer_snippet = response.get("answer", "") or ""

    for item in response.get("results", []):
        raw_content = item.get("raw_content") or ""
        results.append(
            {
                "source": item.get("url", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "raw_content": raw_content[:3000],
                "score": item.get("score", 0.0),
                "query": query,
                "answer_snippet": answer_snippet,
                "agent": "tavily",
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
        topic = "finance" if cluster_key in FINANCE_CLUSTERS else "general"
        print(
            f"[tavily_agent] Searching cluster: {cluster_key} "
            f"({len(queries)} queries, topic={topic})"
        )
        for query in queries:
            try:
                results = search_tavily(query, topic=topic)
                for r in results:
                    r["cluster"] = cluster_key
                all_results.extend(results)
                print(f"  ✓ '{query[:60]}' → {len(results)} results")
            except Exception as exc:
                print(f"  ✗ '{query[:60]}' → ERROR: {exc}")
            time.sleep(0.4)

    output_path = Path("research/tavily_results.json")
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"[tavily_agent] Done. {len(all_results)} results written to {output_path}")


if __name__ == "__main__":
    main()
