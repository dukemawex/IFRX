"""
Agent 2 — exa_agent.py (TinyFish full-feature backend)

Uses the TinyFish automation SSE API to perform goal-directed, PhD-grade
research extraction for every query cluster in the IFRS / Union Bank pipeline.

Features used
─────────────
• Cluster-specific extraction goals  — each cluster receives a bespoke,
  PhD-quality natural-language goal that references the exact topic,
  variables (NPL, CAR, ROA, IFRS 9, ISA 570 …) and output schema needed.
• Multiple authoritative seed URLs per cluster — TinyFish is pointed at the
  most relevant academic / regulatory domains for each research area.
• Proper SSE streaming  — the response is consumed with iter_lines() so the
  agent can handle long-running extractions without buffering the whole body.
• JSON-fragment accumulation  — partial JSON emitted across multiple SSE
  data-lines is concatenated and repaired before parsing.
• Result-type routing  — SSE events carrying {"type": "result"/"done"} are
  detected first; raw JSON arrays fall back as secondary.
• Rich metadata extraction  — goals request: title, url, authors, year,
  journal_or_publisher, doi, abstract (≤400 words), key_findings, citations.
• URL-based deduplication  — duplicate source URLs are removed across the
  full run so the synthesis agent receives unique references.
• Depth-aware query budget  — RESEARCH_DEPTH (quick/standard/deep) adjusts
  how many seed URLs are tried per cluster.
• Graceful degradation  — per-query exceptions are caught and logged without
  crashing the pipeline; every cluster always completes.

Output: research/tinyfish_results.json
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from pathlib import Path
from threading import Lock

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

TINYFISH_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"

# ── Depth budget: how many seed URLs to try per query ────────────────────────
DEPTH_SEED_LIMIT = {"quick": 1, "standard": 2, "deep": 3}

# ── Per-cluster authoritative seed URLs (ordered by relevance) ───────────────
CLUSTER_SEEDS: dict[str, list[str]] = {
    "background_ifrs": [
        "https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/",
        "https://www.cbn.gov.ng/supervision/circulars.asp",
        "https://www.frc.gov.ng/",
    ],
    "going_concern": [
        "https://www.iaasb.org/publications/isa-570-revised-going-concern",
        "https://www.ifac.org/knowledge-gateway/audit-assurance",
        "https://ssrn.com/en/",
    ],
    "banking_stability": [
        "https://www.bis.org/publ/work.htm",
        "https://www.imf.org/en/Publications/WP",
        "https://www.cbn.gov.ng/OUT/2023/RSD/2022%20ANNUAL%20REPORT.pdf",
    ],
    "union_bank_case_study": [
        "https://www.unionbankng.com/investor-relations/",
        "https://ngxgroup.com/exchange/",
        "https://www.cbn.gov.ng/supervision/otherfin.asp",
    ],
    "literature_gaps": [
        "https://ssrn.com/en/",
        "https://www.researchgate.net/search?q=IFRS+going+concern+Nigeria",
        "https://www.emerald.com/insight/search?q=IFRS+Nigeria+banking",
    ],
    "theoretical_framework": [
        "https://ssrn.com/en/",
        "https://www.jstor.org/action/doBasicSearch?Query=agency+theory+IFRS+banking",
        "https://www.tandfonline.com/search?query=stakeholder+theory+IFRS",
    ],
}

# ── Per-cluster PhD-grade extraction goals ────────────────────────────────────
# Each goal is tailored to the exact research questions, variables, and output
# schema needed for the corresponding section of the proposal.
CLUSTER_GOALS: dict[str, str] = {
    "background_ifrs": (
        "You are assisting a PhD researcher studying the effect of IFRS adoption on "
        "going concern assessment and financial stability in Nigerian banks (2012–2022), "
        "with Union Bank of Nigeria PLC as the case study.\n\n"
        "TASK: Extract the most relevant academic papers, regulatory documents, and "
        "authoritative reports on the following specific topics:\n"
        "1. The CBN/FRC Nigeria mandate for IFRS adoption in Nigerian banks (2010–2014)\n"
        "2. IFRS 9 Expected Credit Loss (ECL) model implementation in Nigerian commercial banks\n"
        "3. IFRS 7 financial instruments disclosure requirements and their application in "
        "   Nigerian bank annual reports\n"
        "4. Comparative analysis of Nigerian GAAP vs IFRS transition outcomes for banks\n\n"
        "For EACH source found, extract ALL of the following fields:\n"
        "  title, url, authors (array of full names), year (integer), "
        "  journal_or_publisher, doi_or_isbn, abstract (max 400 words), "
        "  key_findings (array of 3–5 concise bullet strings), "
        "  relevant_citations (array of APA 7th edition strings cited within the source), "
        "  cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
    "going_concern": (
        "You are assisting a PhD researcher studying going concern assessment under IFRS "
        "in the Nigerian banking sector (2012–2022).\n\n"
        "TASK: Extract the most relevant academic papers and standards on:\n"
        "1. ISA 570 (Revised) Going Concern — requirements, triggers, and auditor obligations\n"
        "2. Empirical studies on going concern opinions issued to Nigerian commercial banks\n"
        "3. The relationship between IFRS 9 loan impairment (ECL provisioning) and bank "
        "   solvency / going concern risk\n"
        "4. Modified audit opinions (Emphasis of Matter / qualified opinions) linked to "
        "   capital inadequacy in Nigerian banks\n\n"
        "For EACH source, extract ALL fields:\n"
        "  title, url, authors (array), year, journal_or_publisher, doi_or_isbn, "
        "  abstract (max 400 words), key_findings (3–5 bullets), "
        "  relevant_citations (APA 7th), cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
    "banking_stability": (
        "You are assisting a PhD researcher studying the relationship between IFRS adoption "
        "and bank financial stability in developing countries, with focus on Nigeria.\n\n"
        "TASK: Extract empirical research on:\n"
        "1. The effect of IFRS adoption on financial stability metrics (NPL ratio, CAR, ROA, "
        "   Z-score) in banks in Africa and other developing economies\n"
        "2. IFRS 9 procyclicality risk: does ECL provisioning amplify credit contraction "
        "   during economic downturns?\n"
        "3. Basel III capital adequacy framework interaction with IFRS 9 in Nigerian banks\n"
        "4. Empirical bank stability indices for Nigeria (2012–2022) — CBN annual reports, "
        "   IMF Article IV consultations, BIS working papers\n\n"
        "For EACH source, extract ALL fields:\n"
        "  title, url, authors (array), year, journal_or_publisher, doi_or_isbn, "
        "  abstract (max 400 words), key_findings (3–5 bullets), "
        "  relevant_citations (APA 7th), stability_metrics_covered (array), cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
    "union_bank_case_study": (
        "You are assisting a PhD researcher conducting a case study of Union Bank of "
        "Nigeria PLC (UBN, ticker UBN:NL) covering 2012–2022.\n\n"
        "TASK: Extract the following specific information:\n"
        "1. UBN annual report financial highlights 2015–2022: NPL ratio, Capital Adequacy "
        "   Ratio (CAR), Return on Assets (ROA), total assets, loan loss provisions\n"
        "2. External audit opinions for each year — especially any Emphasis of Matter or "
        "   going concern paragraphs (PwC Nigeria, KPMG Nigeria)\n"
        "3. UBN's IFRS 9 transition disclosure (2018): modified retrospective approach, "
        "   opening equity adjustment (NGN billions)\n"
        "4. Titan Trust Bank acquisition of ~89.4% UBN stake (2022): timeline, regulatory "
        "   approvals, NGX delisting implications\n"
        "5. CBN Supervisory Reports on UBN: recapitalisation notices (2015–2016), "
        "   COVID-19 forbearance (2020)\n\n"
        "For EACH source, extract ALL fields:\n"
        "  title, url, authors_or_organization, year, document_type "
        "  (annual_report / regulatory_filing / news / academic), "
        "  financial_data_extracted (dict of metric→value where applicable), "
        "  audit_opinion (string), key_findings (3–5 bullets), cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
    "literature_gaps": (
        "You are assisting a PhD researcher who needs to identify and articulate gaps in "
        "existing literature on IFRS, going concern assessment, and banking stability in "
        "Nigeria and sub-Saharan Africa.\n\n"
        "TASK: Find recent peer-reviewed papers (2015–2024) that:\n"
        "1. Study IFRS adoption effects on Nigerian/African bank performance but do NOT "
        "   examine going concern opinions as an outcome variable\n"
        "2. Examine going concern in Nigerian banks without linking it to IFRS 9 ECL\n"
        "3. Use panel data for African banking sectors but exclude Union Bank or Nigerian "
        "   listed banks from their sample\n"
        "4. Acknowledge limitations about single-country, small-sample, or pre-IFRS 9 data\n\n"
        "For EACH paper found, extract ALL fields:\n"
        "  title, url, authors (array), year, journal, doi, abstract (max 300 words), "
        "  gap_identified (2–3 sentences as stated by the authors), "
        "  future_research_suggested (string), cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
    "theoretical_framework": (
        "You are assisting a PhD researcher who needs to build a theoretical framework "
        "applying Agency Theory, Signalling Theory, and Stakeholder Theory to the "
        "IFRS–going concern–banking stability nexus in Nigeria.\n\n"
        "TASK: Find seminal and recent papers (2000–2024) that:\n"
        "1. Apply Agency Theory to IFRS financial reporting transparency and information "
        "   asymmetry between bank management and regulators/investors\n"
        "2. Apply Signalling Theory to explain why IFRS adoption signals financial health "
        "   to external stakeholders in developing economies\n"
        "3. Apply Stakeholder Theory to IFRS banking disclosures and going concern "
        "   obligations to depositors, regulators, and the public\n"
        "4. Combine two or more of these theories in an accounting/banking context, "
        "   ideally in African or Nigerian settings\n\n"
        "For EACH paper found, extract ALL fields:\n"
        "  title, url, authors (array), year, journal, doi, abstract (max 300 words), "
        "  theory_applied (array: 'agency'/'signalling'/'stakeholder'), "
        "  core_argument (2–3 sentences), key_propositions (array of strings), "
        "  how_to_cite_apa7 (full APA 7th citation string), cluster\n\n"
        "Return ONLY a valid JSON array. No preamble."
    ),
}


# ── SSE stream parser ─────────────────────────────────────────────────────────

def _stream_sse(response: requests.Response) -> list[dict]:
    """
    Consume a TinyFish SSE response and return the extracted result items.

    Strategy (in priority order):
    1. Look for {"type": "result"|"done"|"complete", "data"|"result": [...]} events.
    2. Look for any top-level JSON array in a data line.
    3. Accumulate all data payloads, concatenate, and attempt a final JSON parse.
    4. Collect non-JSON text lines as raw entries to preserve any partial info.
    """
    type_result_items: list[dict] = []
    raw_array_items: list[dict] = []
    accumulated_payloads: list[str] = []
    raw_text_lines: list[str] = []

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        line = line.rstrip()

        # SSE comment / event-type / id lines — skip
        if line.startswith(":") or line.startswith("event:") or line.startswith("id:"):
            continue
        if not line.startswith("data:"):
            continue

        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue

        accumulated_payloads.append(payload)

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            raw_text_lines.append(payload)
            continue

        # ── Priority 1: typed result envelope ───────────────────────────────
        if isinstance(parsed, dict):
            event_type = parsed.get("type", "")
            if event_type in ("result", "done", "complete", "final"):
                inner = parsed.get("data") or parsed.get("result") or parsed.get("items")
                if isinstance(inner, list):
                    type_result_items.extend(inner)
                    continue
                if isinstance(inner, dict):
                    type_result_items.append(inner)
                    continue
            # skip pure progress / status events
            if event_type in ("thinking", "browsing", "loading", "progress", "status"):
                continue
            # any other dict that looks like a result item
            if any(k in parsed for k in ("title", "url", "source", "abstract")):
                raw_array_items.append(parsed)
                continue

        # ── Priority 2: raw JSON array ───────────────────────────────────────
        if isinstance(parsed, list):
            raw_array_items.extend(parsed)

    # ── Priority 1 wins if we got typed results ──────────────────────────────
    if type_result_items:
        return type_result_items

    if raw_array_items:
        return raw_array_items

    # ── Priority 3: concatenated fragment repair ──────────────────────────────
    combined = "".join(accumulated_payloads)
    # Find the outermost JSON array
    start = combined.find("[")
    end = combined.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(combined[start : end + 1])
        except json.JSONDecodeError:
            pass

    # ── Priority 4: raw text fallback (preserve info for LLM context) ────────
    if raw_text_lines:
        return [{"raw": "\n".join(raw_text_lines)}]

    return []


def _normalise(item: dict, query: str, cluster: str, seed_url: str) -> dict:
    """
    Map any TinyFish result shape to the pipeline's canonical schema.
    Preserves ALL rich metadata fields so the synthesis agent has maximum context.
    """
    return {
        # Core fields (used by synthesis_agent context builder)
        "source": item.get("url", item.get("link", item.get("source", ""))),
        "title": item.get("title", item.get("name", "")),
        "published_date": str(
            item.get("year",
                item.get("published_date", item.get("date", item.get("posted", ""))))
        ),
        "text": item.get("abstract", item.get("text", item.get("content", item.get("raw", "")))),
        "highlights": item.get("key_findings", item.get("highlights", [])),
        # Rich metadata — preserved for synthesis agent
        "authors": item.get("authors", item.get("authors_or_organization", [])),
        "journal_or_publisher": item.get("journal_or_publisher", item.get("journal", "")),
        "doi": item.get("doi_or_isbn", item.get("doi", "")),
        "key_findings": item.get("key_findings", []),
        "relevant_citations": item.get("relevant_citations", []),
        "stability_metrics_covered": item.get("stability_metrics_covered", []),
        "gap_identified": item.get("gap_identified", ""),
        "future_research_suggested": item.get("future_research_suggested", ""),
        "theory_applied": item.get("theory_applied", []),
        "core_argument": item.get("core_argument", ""),
        "key_propositions": item.get("key_propositions", []),
        "how_to_cite_apa7": item.get("how_to_cite_apa7", ""),
        "financial_data_extracted": item.get("financial_data_extracted", {}),
        "audit_opinion": item.get("audit_opinion", ""),
        "document_type": item.get("document_type", ""),
        # Provenance
        "query": query,
        "cluster": cluster,
        "seed_url": seed_url,
        "agent": "tinyfish",
    }


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
def search_tinyfish(query: str, seed_url: str, cluster: str) -> list[dict]:
    """
    Run a single TinyFish automation goal against one seed URL.
    Uses the cluster-specific goal template, injecting the current query as
    the focused sub-topic within the broader extraction instructions.
    """
    api_key = os.environ["TINYFISH_API_KEY"]
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    # Inject the specific query as the focused sub-topic in the cluster goal
    cluster_goal = CLUSTER_GOALS[cluster]
    goal = (
        f"FOCUSED SUB-TOPIC FOR THIS REQUEST: {query}\n\n"
        f"{cluster_goal}"
    )

    body = {"url": seed_url, "goal": goal}

    response = requests.post(
        TINYFISH_URL, headers=headers, json=body, stream=True, timeout=(15, 45)
    )
    response.raise_for_status()

    items = _stream_sse(response)
    return [_normalise(item, query, cluster, seed_url) for item in items if isinstance(item, dict)]


def main() -> None:
    queries_path = Path("research/queries.json")
    if not queries_path.exists():
        raise FileNotFoundError(f"{queries_path} not found — run orchestrator first")

    data = json.loads(queries_path.read_text())
    clusters: dict[str, list[str]] = data["query_clusters"]
    depth = data.get("depth", os.environ.get("RESEARCH_DEPTH", "deep"))
    seed_limit = DEPTH_SEED_LIMIT.get(depth, 3)

    # Build the full list of (cluster, query, seed_url) tasks
    tasks: list[tuple[str, str, str]] = []
    for cluster_key, queries in clusters.items():
        seeds = CLUSTER_SEEDS.get(cluster_key, ["https://ssrn.com/en/"])[:seed_limit]
        print(
            f"[tinyfish_agent] Cluster: {cluster_key} | "
            f"{len(queries)} queries × {len(seeds)} seed(s) | depth={depth}"
        )
        for query in queries:
            for seed_url in seeds:
                tasks.append((cluster_key, query, seed_url))

    all_results: list[dict] = []
    seen_urls: set[str] = set()
    results_lock = Lock()

    def run_task(task: tuple[str, str, str]) -> None:
        cluster_key, query, seed_url = task
        try:
            results = search_tinyfish(query, seed_url, cluster_key)
            with results_lock:
                new_results = []
                for r in results:
                    url = r.get("source", "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    new_results.append(r)
                all_results.extend(new_results)
            print(
                f"  ✓ '{query[:55]}' @ {seed_url.split('/')[2]} "
                f"→ {len(new_results)} results ({len(results) - len(new_results)} dupes dropped)"
            )
        except Exception as exc:
            print(f"  ✗ '{query[:55]}' @ {seed_url.split('/')[2]} → ERROR: {exc}")

    if tasks:
        max_workers = min(6, len(tasks))
        # Hard wall-clock deadline derived from an env variable so it can be
        # tuned without touching this file.  Default: 45 minutes, which fits
        # comfortably inside the workflow's timeout-minutes: 60 budget.
        AGENT_TIMEOUT_SECONDS = int(os.environ.get("TINYFISH_TIMEOUT_SECONDS", str(45 * 60)))
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_task, task) for task in tasks]
            try:
                for future in as_completed(futures, timeout=AGENT_TIMEOUT_SECONDS):
                    future.result()  # propagate unexpected exceptions
                    completed_count += 1
            except FuturesTimeoutError:
                pending = len(tasks) - completed_count
                print(
                    f"[tinyfish_agent] Wall-clock deadline reached "
                    f"({AGENT_TIMEOUT_SECONDS}s) — "
                    f"{completed_count}/{len(tasks)} tasks completed, "
                    f"{pending} still pending. Saving partial results."
                )

    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    output_path = research_dir / "tinyfish_results.json"
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))

    cluster_counts = {}
    for r in all_results:
        k = r.get("cluster", "unknown")
        cluster_counts[k] = cluster_counts.get(k, 0) + 1

    print(
        f"\n[tinyfish_agent] Done. {len(all_results)} unique results written to {output_path}"
    )
    for k, v in cluster_counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

