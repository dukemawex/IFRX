"""
Agent 3 — tavily_agent.py
Three-tier Tavily research pipeline for the IFRS / Union Bank PhD proposal.

Tier 1 — search()        : Scoped academic/financial search for every query in
                            every cluster. Uses search_depth="advanced",
                            include_answer=True, and include_domains to restrict
                            results to authoritative academic and regulatory sources.

Tier 2 — extract()       : Full content extraction from specific, pre-selected
                            authoritative URLs (IFRS.org, IAASB, BIS, CBN,
                            UBN investor relations, NGX, IMF) for each cluster.
                            Provides raw page text the LLM can mine for citations.

Tier 3 — research()      : Deep multi-step research call (Tavily Research API)
                            for each cluster's primary research question. Returns
                            a comprehensive synthesis report with ranked sources.
                            SDK method is tried first; raw HTTP fallback if the
                            installed SDK version is older.

All tiers are merged, deduplicated by URL, tagged with cluster and tier, and
written to:
  research/tavily_results.json   — Tier 1 + Tier 2 results (individual items)
  research/tavily_research.json  — Tier 3 deep-research reports (one per cluster)
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests
from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

TAVILY_RESEARCH_URL = "https://api.tavily.com/research"

# ── Clusters that should use topic="finance" ─────────────────────────────────
FINANCE_CLUSTERS = {"background_ifrs", "banking_stability", "union_bank_case_study"}

# ── Academic and regulatory domains to scope standard searches ────────────────
ACADEMIC_DOMAINS = [
    "scholar.google.com", "ssrn.com", "researchgate.net", "jstor.org",
    "emerald.com", "tandfonline.com", "wiley.com", "springer.com",
    "sciencedirect.com", "cbn.gov.ng", "frc.gov.ng", "unionbankng.com",
    "ngxgroup.com", "sec.gov.ng", "ifrs.org", "iasb.org", "iaasb.org",
    "bis.org", "imf.org", "worldbank.org", "afdb.org",
]

# ── Tier 2: authoritative URLs to extract per cluster ────────────────────────
CLUSTER_EXTRACT_URLS: dict[str, list[str]] = {
    "background_ifrs": [
        "https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/",
        "https://www.ifrs.org/issued-standards/list-of-standards/ifrs-7-financial-instruments-disclosures/",
        "https://www.cbn.gov.ng/supervision/circulars.asp",
    ],
    "going_concern": [
        "https://www.iaasb.org/publications/isa-570-revised-going-concern",
        "https://www.ifac.org/knowledge-gateway/audit-assurance/publications/isa-570-revised-going-concern",
    ],
    "banking_stability": [
        "https://www.bis.org/publ/work.htm",
        "https://www.imf.org/en/Publications/WP",
        "https://www.cbn.gov.ng/documents/annualreports.asp",
    ],
    "union_bank_case_study": [
        "https://www.unionbankng.com/investor-relations/",
        "https://ngxgroup.com/exchange/trade/equities/ubn/",
        "https://www.cbn.gov.ng/supervision/finStats.asp",
    ],
    "literature_gaps": [
        "https://ssrn.com/en/",
        "https://www.emerald.com/insight/search?q=IFRS+Nigeria+banking+going+concern",
    ],
    "theoretical_framework": [
        "https://ssrn.com/en/",
        "https://www.jstor.org/action/doBasicSearch?Query=agency+theory+IFRS+banking",
    ],
}

# ── Tier 3: deep-research question and instructions per cluster ───────────────
CLUSTER_RESEARCH: dict[str, dict[str, str]] = {
    "background_ifrs": {
        "query": (
            "IFRS adoption in Nigerian banking sector 2012–2022: "
            "CBN mandate, FRC guidelines, IFRS 9 ECL implementation, "
            "IFRS 7 disclosures, transition from Nigerian GAAP"
        ),
        "instructions": (
            "Produce a comprehensive academic research summary covering: "
            "(1) the CBN circular FPR/DIR/CIR/GEN/01/010 mandating IFRS for Nigerian banks, "
            "(2) the FRC Nigeria guidelines for public interest entities, "
            "(3) IFRS 9 Expected Credit Loss model implementation challenges for Nigerian banks, "
            "(4) IFRS 7 disclosure quality improvements post-adoption. "
            "Cite all sources with author, year, and URL. "
            "Focus on peer-reviewed journals and official regulatory publications."
        ),
    },
    "going_concern": {
        "query": (
            "Going concern assessment under IFRS in Nigerian banks: "
            "ISA 570, modified audit opinions, IFRS 9 loan impairment and bank solvency 2012–2022"
        ),
        "instructions": (
            "Provide an in-depth academic review covering: "
            "(1) ISA 570 (Revised) 2015 requirements and triggers for going concern modifications, "
            "(2) empirical evidence on going concern opinions in Nigerian commercial banks, "
            "(3) the link between IFRS 9 Expected Credit Loss provisioning and bank solvency risk, "
            "(4) Emphasis of Matter paragraphs in Nigerian bank audit reports 2015–2018. "
            "Prioritise Nigerian and African journals. Cite all sources."
        ),
    },
    "banking_stability": {
        "query": (
            "IFRS adoption, IFRS 9 procyclicality, and bank financial stability "
            "in Nigeria and developing countries: NPL, CAR, ROA, Z-score evidence"
        ),
        "instructions": (
            "Synthesise empirical research on: "
            "(1) the causal effect of IFRS adoption on NPL ratio, CAR, and ROA in African banks, "
            "(2) IFRS 9 procyclicality risk during economic downturns (including COVID-19), "
            "(3) Basel III and IFRS 9 interaction on capital adequacy in Nigerian banks, "
            "(4) CBN Banking Supervision Annual Report data on sector-level stability 2012–2022. "
            "Include IMF and BIS working papers. Cite all sources with DOI where available."
        ),
    },
    "union_bank_case_study": {
        "query": (
            "Union Bank of Nigeria PLC (UBN) financial performance 2015–2022: "
            "NPL ratio, CAR, ROA, IFRS 9 transition 2018, audit opinions, "
            "Titan Trust Bank acquisition 2022"
        ),
        "instructions": (
            "Compile a detailed case study data summary for Union Bank of Nigeria PLC covering: "
            "(1) annual NPL ratio, Capital Adequacy Ratio (CAR), and Return on Assets (ROA) "
            "    for each year 2015–2022 with source citations, "
            "(2) audit opinions (particularly 2015–2016 Emphasis of Matter paragraphs), "
            "(3) IFRS 9 modified retrospective transition in 2018 and the equity impact, "
            "(4) Titan Trust Bank acquisition timeline and NGX delisting 2022–2023. "
            "Use only verifiable public sources: annual reports, NGX filings, CBN reports. "
            "Report exact figures where available."
        ),
    },
    "literature_gaps": {
        "query": (
            "Research gaps in IFRS going concern banking stability Nigeria Africa: "
            "missing empirical studies, panel data limitations, IFRS 9 single-country gaps"
        ),
        "instructions": (
            "Identify and articulate specific research gaps in the literature on "
            "IFRS, going concern assessment, and banking stability in Nigeria and sub-Saharan Africa: "
            "(1) studies that examine IFRS adoption but not going concern as an outcome variable, "
            "(2) going concern studies that predate IFRS 9, "
            "(3) panel data studies that exclude Nigerian-listed banks, "
            "(4) single-country studies acknowledging generalisability limitations. "
            "Quote the exact gap statements from the original authors. Cite all sources."
        ),
    },
    "theoretical_framework": {
        "query": (
            "Agency theory, signalling theory, stakeholder theory applied to "
            "IFRS financial reporting, going concern, and banking regulation in Africa"
        ),
        "instructions": (
            "Review the theoretical foundations for studying IFRS and going concern in banking: "
            "(1) Agency Theory — how IFRS reduces information asymmetry between bank management "
            "    and shareholders/regulators (cite Jensen & Meckling 1976 and African extensions), "
            "(2) Signalling Theory — how IFRS adoption signals financial health to foreign investors "
            "    in developing economies, "
            "(3) Stakeholder Theory — how IFRS going concern disclosures serve depositors, "
            "    regulators, and the public, "
            "(4) applications of these theories specifically in Nigerian/African banking contexts. "
            "Provide full APA 7th edition citations."
        ),
    },
}


# ── Tier 1: scoped search ─────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def search_tavily(query: str, topic: str = "general") -> list[dict]:
    """Scoped academic/financial Tavily search for a single query."""
    response = client.search(
        query,
        search_depth="advanced",
        max_results=10,
        include_answer=True,
        include_raw_content=True,
        topic=topic,
        include_domains=ACADEMIC_DOMAINS,
    )

    answer_snippet = response.get("answer", "") or ""
    results = []
    for item in response.get("results", []):
        raw_content = item.get("raw_content") or ""
        results.append({
            "source": item.get("url", ""),
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "raw_content": raw_content[:4000],
            "score": item.get("score", 0.0),
            "query": query,
            "answer_snippet": answer_snippet,
            "tier": "search",
            "agent": "tavily",
        })
    return results


# ── Tier 2: URL extraction ────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=3, max=15))
def _extract_single_url(url: str) -> dict | None:
    """Extract full content from a single URL. Returns None on failure."""
    response = client.extract(urls=[url])
    for item in response.get("results", []):
        raw = item.get("raw_content") or ""
        return {
            "source": item.get("url", url),
            "title": item.get("url", url).split("/")[-1] or item.get("url", url),
            "content": raw[:800],
            "raw_content": raw[:6000],
            "score": 1.0,
            "query": "authoritative_extract",
            "answer_snippet": "",
            "tier": "extract",
            "agent": "tavily",
        }
    for failed in response.get("failed_results", []):
        print(f"  [extract] Failed: {failed.get('url', '')} — {failed.get('error', '')}")
    return None


def extract_urls(urls: list[str]) -> list[dict]:
    """Extract full content from specific authoritative URLs, one at a time."""
    results = []
    for url in urls:
        try:
            item = _extract_single_url(url)
            if item:
                results.append(item)
        except Exception as exc:
            print(f"  [extract] Failed: {url} — {exc}")
    return results


# ── Tier 3: deep research ─────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=5, max=30))
def deep_research(query: str, instructions: str, cluster: str) -> dict | None:
    """
    Call Tavily Research API for a deep multi-step research report.
    Tries the SDK method first, falls back to direct HTTP.
    """
    api_key = os.environ["TAVILY_API_KEY"]

    # ── Try SDK method (available in tavily-python >= 0.5.x) ─────────────────
    if hasattr(client, "research"):
        try:
            result = client.research(query, instructions=instructions)
            if result:
                result["cluster"] = cluster
                result["tier"] = "research"
                result["agent"] = "tavily"
                return result
        except Exception as exc:
            print(f"  [research] SDK method failed ({exc}), trying HTTP...")

    # ── Direct HTTP fallback ──────────────────────────────────────────────────
    try:
        resp = requests.post(
            TAVILY_RESEARCH_URL,
            json={
                "api_key": api_key,
                "input": query,
                "instructions": instructions,
                "max_tokens": 12000,
            },
            timeout=90,
        )
        if resp.ok:
            result = resp.json()
            result["cluster"] = cluster
            result["tier"] = "research"
            result["agent"] = "tavily"
            return result
        print(f"  [research] HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"  [research] HTTP fallback failed: {exc}")

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    queries_path = Path("research/queries.json")
    if not queries_path.exists():
        raise FileNotFoundError(f"{queries_path} not found — run orchestrator first")

    data = json.loads(queries_path.read_text())
    clusters: dict[str, list[str]] = data["query_clusters"]

    all_items: list[dict] = []
    seen_urls: set[str] = set()
    items_lock = Lock()
    research_reports: list[dict] = []
    reports_lock = Lock()

    # ── Tier 1: parallelise all searches across every cluster ─────────────────
    # Build a flat list of (cluster_key, query, topic) tasks
    search_tasks: list[tuple[str, str, str]] = []
    for cluster_key, queries in clusters.items():
        topic = "finance" if cluster_key in FINANCE_CLUSTERS else "general"
        for query in queries:
            search_tasks.append((cluster_key, query, topic))

    print(f"\n[tavily_agent] Tier 1 — search ({len(search_tasks)} queries across all clusters)")

    def run_search(task: tuple[str, str, str]) -> None:
        cluster_key, query, topic = task
        try:
            results = search_tavily(query, topic=topic)
            with items_lock:
                new = 0
                for r in results:
                    r["cluster"] = cluster_key
                    url = r.get("source", "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    all_items.append(r)
                    new += 1
            print(f"  ✓ [{cluster_key}] '{query[:55]}' → {new} new")
        except Exception as exc:
            print(f"  ✗ [{cluster_key}] '{query[:55]}' → ERROR: {exc}")

    max_search_workers = min(6, len(search_tasks)) if search_tasks else 1
    with ThreadPoolExecutor(max_workers=max_search_workers) as executor:
        futures = [executor.submit(run_search, task) for task in search_tasks]
        for future in as_completed(futures):
            future.result()

    # ── Tier 2: extract authoritative URLs per cluster (sequential — small set) ─
    for cluster_key in clusters:
        extract_targets = CLUSTER_EXTRACT_URLS.get(cluster_key, [])
        if extract_targets:
            print(f"\n[tavily_agent] ── Cluster: {cluster_key} ── Tier 2 — extract ({len(extract_targets)} URLs)")
            try:
                extracted = extract_urls(extract_targets)
                new = 0
                for r in extracted:
                    r["cluster"] = cluster_key
                    url = r.get("source", "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    all_items.append(r)
                    new += 1
                print(f"  ✓ Extracted {new} pages")
            except Exception as exc:
                print(f"  ✗ Extract failed: {exc}")
            time.sleep(0.5)

    # ── Tier 3: parallelise deep research across all clusters ─────────────────
    print(f"\n[tavily_agent] Tier 3 — deep research ({len(clusters)} clusters in parallel)")

    def run_deep_research(cluster_key: str) -> None:
        rc = CLUSTER_RESEARCH.get(cluster_key)
        if not rc:
            return
        try:
            report = deep_research(rc["query"], rc["instructions"], cluster_key)
            if report:
                with reports_lock:
                    research_reports.append(report)
                sources = report.get("sources") or report.get("results") or []
                print(f"  ✓ [{cluster_key}] Report received ({len(str(report))} chars, {len(sources)} sources)")
            else:
                print(f"  ✗ [{cluster_key}] Research returned empty result")
        except Exception as exc:
            print(f"  ✗ [{cluster_key}] Deep research failed: {exc}")

    max_research_workers = min(3, len(clusters)) if clusters else 1
    with ThreadPoolExecutor(max_workers=max_research_workers) as executor:
        futures = [executor.submit(run_deep_research, ck) for ck in clusters]
        for future in as_completed(futures):
            future.result()

    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    # Write Tier 1+2 results
    results_path = research_dir / "tavily_results.json"
    results_path.write_text(json.dumps(all_items, indent=2, ensure_ascii=False))

    # Write Tier 3 reports
    research_path = research_dir / "tavily_research.json"
    research_path.write_text(json.dumps(research_reports, indent=2, ensure_ascii=False))

    tier_counts = {}
    for r in all_items:
        t = r.get("tier", "unknown")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    print(f"\n[tavily_agent] Done.")
    print(f"  Standard results: {len(all_items)} items → {results_path}")
    for t, c in tier_counts.items():
        print(f"    tier={t}: {c}")
    print(f"  Deep research:    {len(research_reports)} reports → {research_path}")


if __name__ == "__main__":
    main()

