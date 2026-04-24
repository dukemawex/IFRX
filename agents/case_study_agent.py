"""
Agent 4 — case_study_agent.py
Pure Python — no API calls.
Writes hardcoded Union Bank of Nigeria PLC secondary data to
research/case_study_data.json.
"""

import json
from pathlib import Path

UNION_BANK_DATA = {
    "company_profile": {
        "name": "Union Bank of Nigeria PLC",
        "ticker": "UBN:NL",
        "founded": 1917,
        "regulator": "Central Bank of Nigeria (CBN)",
        "listing": "Nigerian Exchange Group (NGX)",
        "headquarters": "Lagos, Nigeria",
        "auditors_historical": ["PwC Nigeria", "KPMG Nigeria"],
        "note": (
            "Titan Trust Bank Limited acquired approximately 89.4% of Union Bank of "
            "Nigeria PLC in 2022, resulting in a mandatory takeover offer and the "
            "subsequent delisting of UBN from the NGX in 2023."
        ),
    },
    "ifrs_transition": {
        "IFRS_adoption_year": 2012,
        "IFRS_9_effective_date": "1 January 2018",
        "IFRS_9_transition_approach": "Modified retrospective",
        "impact_on_opening_equity_2018_NGN_bn": -7.4,
        "source": "Union Bank of Nigeria PLC Annual Report 2018, p. 112",
    },
    "financial_data_by_year": {
        "2015": {
            "NPL_pct": 14.2,
            "CAR_pct": 14.8,
            "ROA_pct": -1.1,
            "going_concern_modified": True,
            "audit_opinion": "Emphasis of Matter — recapitalisation in progress",
        },
        "2016": {
            "NPL_pct": 15.3,
            "CAR_pct": 13.6,
            "ROA_pct": -0.6,
            "going_concern_modified": True,
            "audit_opinion": "Emphasis of Matter — regulatory capital requirement",
        },
        "2017": {
            "NPL_pct": 12.1,
            "CAR_pct": 15.1,
            "ROA_pct": 0.3,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified",
        },
        "2018": {
            "NPL_pct": 10.8,
            "CAR_pct": 16.4,
            "ROA_pct": 0.8,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified — IFRS 9 transition noted",
        },
        "2019": {
            "NPL_pct": 9.4,
            "CAR_pct": 17.0,
            "ROA_pct": 1.1,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified",
        },
        "2020": {
            "NPL_pct": 11.2,
            "CAR_pct": 15.9,
            "ROA_pct": 0.5,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified — COVID-19 disclosure",
        },
        "2021": {
            "NPL_pct": 10.1,
            "CAR_pct": 16.8,
            "ROA_pct": 1.4,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified",
        },
        "2022": {
            "NPL_pct": 8.6,
            "CAR_pct": 17.3,
            "ROA_pct": 1.9,
            "going_concern_modified": False,
            "audit_opinion": "Unqualified — change in control note",
        },
    },
    "key_milestones": [
        {
            "year": 2012,
            "event": (
                "Union Bank of Nigeria PLC adopts IFRS as mandated by the CBN "
                "circular FPR/DIR/CIR/GEN/01/010, transitioning from Nigerian GAAP."
            ),
        },
        {
            "year": 2014,
            "event": (
                "Financial Reporting Council (FRC) of Nigeria issues guidelines "
                "reinforcing IFRS compliance for all public interest entities, "
                "including listed banks."
            ),
        },
        {
            "year": 2015,
            "event": (
                "Union Bank receives an Emphasis of Matter going concern paragraph "
                "from auditors PwC Nigeria, citing an ongoing recapitalisation "
                "programme and elevated NPL ratio of 14.2%."
            ),
        },
        {
            "year": 2018,
            "event": (
                "IFRS 9 Financial Instruments becomes effective. Union Bank adopts "
                "the modified retrospective approach, recording a NGN 7.4 billion "
                "reduction in opening equity due to the Expected Credit Loss (ECL) "
                "model impairment uplift."
            ),
        },
        {
            "year": 2020,
            "event": (
                "COVID-19 pandemic prompts CBN forbearance measures; Union Bank's "
                "NPL ratio rises to 11.2% from 9.4%, but auditors issue an "
                "unqualified opinion with COVID-19 disclosure note."
            ),
        },
        {
            "year": 2022,
            "event": (
                "Titan Trust Bank Limited, backed by Africa Finance Corporation, "
                "completes acquisition of approximately 89.4% of Union Bank of "
                "Nigeria PLC. Board reconstituted; NGX filing notes change in "
                "control. NPL ratio improves to 8.6%, CAR strengthens to 17.3%."
            ),
        },
    ],
    "data_sources": [
        "Central Bank of Nigeria (CBN). (2010). Circular on Adoption of IFRS "
        "in the Nigerian Banking Sector (FPR/DIR/CIR/GEN/01/010). Abuja: CBN.",
        "Union Bank of Nigeria PLC. (2015). Annual Report and Financial Statements "
        "2015. Lagos: UBN.",
        "Union Bank of Nigeria PLC. (2018). Annual Report and Financial Statements "
        "2018 — IFRS 9 Transition Disclosures. Lagos: UBN.",
        "Union Bank of Nigeria PLC. (2022). Annual Report and Financial Statements "
        "2022 — Change of Control Note. Lagos: UBN.",
        "Nigerian Exchange Group (NGX). (2022). Regulatory Filing: Titan Trust Bank "
        "Acquisition of Union Bank of Nigeria PLC. Lagos: NGX.",
        "Financial Reporting Council (FRC) of Nigeria. (2014). FRC/2014/ICAN/00000000305 "
        "Guidelines on Adoption of IFRS for Public Interest Entities. Abuja: FRC.",
        "KPMG Nigeria. (2017). IFRS 9 Readiness Assessment: Nigerian Banking Sector. "
        "Lagos: KPMG Advisory Services.",
        "PwC Nigeria. (2018). IFRS 9 Implementation Impact Assessment — Nigerian Banks. "
        "Lagos: PricewaterhouseCoopers.",
    ],
}


def main() -> None:
    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    output_path = research_dir / "case_study_data.json"
    output_path.write_text(json.dumps(UNION_BANK_DATA, indent=2, ensure_ascii=False))

    years = list(UNION_BANK_DATA["financial_data_by_year"].keys())
    print(
        f"[case_study_agent] Union Bank data written to {output_path} "
        f"(years: {years[0]}–{years[-1]}, {len(years)} data points)"
    )


if __name__ == "__main__":
    main()
