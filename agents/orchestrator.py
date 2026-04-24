"""
Agent 1 — orchestrator.py
Pure Python; no external API calls.
Decomposes the research topic into structured query clusters and writes
research/queries.json for downstream agents.
"""

import json
import os
import sys
from pathlib import Path

TOPIC = (
    "The Effect of International Financial Reporting Standards (IFRS) on Going Concern "
    "Assessment and Financial Stability in the Nigerian Banking Sector: "
    "A Case Study of Union Bank of Nigeria PLC (2012–2022)"
)

QUERY_PLAN = {
    "background_ifrs": [
        "IFRS adoption Nigeria banking sector regulatory timeline",
        "IFRS 9 Expected Credit Loss model Nigerian commercial banks implementation",
        "IFRS 7 financial instruments disclosures Nigerian banks transparency",
        "CBN Central Bank Nigeria IFRS adoption mandate timeline 2012 2014",
    ],
    "going_concern": [
        "going concern assessment IFRS Nigeria banking sector auditors",
        "ISA 570 revised going concern auditing standards banking institutions",
        "going concern disclosures modified audit opinions Nigerian banks",
        "IFRS 9 loan impairment provisioning bank solvency going concern",
    ],
    "banking_stability": [
        "IFRS adoption bank financial stability developing countries empirical evidence",
        "IFRS 9 procyclicality capital adequacy banking systemic risk",
        "Basel III IFRS capital adequacy requirements Nigeria banking regulation",
        "bank stability index Nigeria financial sector resilience metrics",
    ],
    "union_bank_case_study": [
        "Union Bank Nigeria IFRS financial statements 2015 2023 annual report",
        "going concern audit opinion Union Bank Nigeria UBN",
        "non-performing loan ratio capital adequacy ratio UBN 2018 2023",
        "IFRS 9 transition impact Union Bank Nigeria opening equity adjustment",
        "Titan Trust Bank acquisition Union Bank Nigeria 2022 change of control",
    ],
    "literature_gaps": [
        "research gaps IFRS going concern banking Nigeria empirical studies",
        "IFRS 9 small medium banks Nigeria financial stability empirical gap",
        "secondary panel data IFRS banking Africa longitudinal study",
    ],
    "theoretical_framework": [
        "agency theory IFRS financial reporting transparency principal agent",
        "stakeholder theory IFRS banking disclosure regulation",
        "positive accounting theory Nigeria financial reporting incentives",
    ],
}


def main() -> None:
    depth = os.environ.get("RESEARCH_DEPTH", "deep")

    # Count total queries
    total_queries = sum(len(v) for v in QUERY_PLAN.values())

    output = {
        "topic": TOPIC,
        "depth": depth,
        "query_clusters": QUERY_PLAN,
        "total_queries": total_queries,
    }

    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    output_path = research_dir / "queries.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(
        f"[orchestrator] Query plan written to {output_path} "
        f"({total_queries} queries across {len(QUERY_PLAN)} clusters, depth={depth})"
    )


if __name__ == "__main__":
    main()
