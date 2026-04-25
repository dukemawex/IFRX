"""
Agent 5 — synthesis_agent.py
Calls OpenRouter free-tier LLM to synthesise all research into a PhD proposal.
Uses requests only — NO anthropic SDK.
Research sources: Tavily search/extract/deep-research results and Union Bank case study data.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
PRIMARY_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
FALLBACK_MODEL = "mistralai/mistral-7b-instruct:free"

MAX_CONTEXT_CHARS = 28_000  # ~8k tokens safety threshold


def load_research() -> dict:
    """Load and combine all research artefacts from Tavily and the case study."""
    research_dir = Path("research")

    tavily_path = research_dir / "tavily_results.json"
    tavily_research_path = research_dir / "tavily_research.json"
    case_study_path = research_dir / "case_study_data.json"
    queries_path = research_dir / "queries.json"

    tavily_results = []
    if tavily_path.exists():
        tavily_results = json.loads(tavily_path.read_text())[:60]

    tavily_research = []
    if tavily_research_path.exists():
        tavily_research = json.loads(tavily_research_path.read_text())

    case_study_data = {}
    if case_study_path.exists():
        case_study_data = json.loads(case_study_path.read_text())

    queries_data = {}
    if queries_path.exists():
        queries_data = json.loads(queries_path.read_text())

    return {
        "tavily_results": tavily_results,
        "tavily_research": tavily_research,
        "case_study_data": case_study_data,
        "queries_data": queries_data,
    }


def build_context(research: dict) -> str:
    """
    Build a combined context string from all three sources, prioritised by
    information density. The case study data is always placed last (highest
    priority anchor) and never truncated.
    """
    parts: list[str] = []

    # ── Source A: Tavily standard search + extract results ────────────────────
    for i, item in enumerate(research.get("tavily_results", []), start=1):
        tier = item.get("tier", "search")
        content_snippet = (
            item.get("raw_content") or item.get("content") or ""
        )[:500]
        answer = item.get("answer_snippet", "")
        parts.append(
            f"[TAV-{i}:{tier.upper()}] {item.get('title', '')} / "
            f"{item.get('source', '')} / "
            f"CLUSTER:{item.get('cluster', '')} / "
            f"{content_snippet}"
            + (f" / ANSWER: {answer[:200]}" if answer else "")
        )

    # ── Source B: Tavily deep research reports ────────────────────────────────
    for i, report in enumerate(research.get("tavily_research", []), start=1):
        cluster = report.get("cluster", "")
        # The report may come back as "report" string or nested "data"
        report_text = (
            report.get("report")
            or report.get("answer")
            or report.get("summary")
            or ""
        )
        sources = report.get("sources") or report.get("results") or []
        source_urls = " | ".join(
            s.get("url", s) if isinstance(s, dict) else str(s)
            for s in sources[:5]
        )
        parts.append(
            f"[DEEP-{i}] CLUSTER:{cluster} / "
            f"{report_text[:1500]}"
            + (f" / SOURCES: {source_urls}" if source_urls else "")
        )

    # ── Source C: Live-enriched case study (always last, never truncated) ─────
    case_study = research.get("case_study_data", {})
    # Exclude bulk live_web_snippets from the main JSON dump to save tokens;
    # they are already summarised in TAV results above.
    case_study_for_context = {
        k: v for k, v in case_study.items() if k != "live_web_snippets"
    }
    case_study_json = json.dumps(case_study_for_context, indent=1)

    # Live snippets summary (answer lines only, capped)
    live_snippets = case_study.get("live_web_snippets", [])
    live_summary_parts = []
    for s in live_snippets[:8]:
        ans = s.get("answer", "")
        url = s.get("url", "")
        content = (s.get("content", "") or "")[:300]
        if ans:
            live_summary_parts.append(f"LIVE[{url}]: {ans[:250]}")
        elif content:
            live_summary_parts.append(f"LIVE[{url}]: {content}")
    live_summary = "\n".join(live_summary_parts)

    case_study_section = (
        "\n--- UNION BANK LIVE + BASELINE CASE STUDY DATA ---\n"
        + (f"LIVE WEB EVIDENCE:\n{live_summary}\n\n" if live_summary else "")
        + f"STRUCTURED DATA:\n{case_study_json}"
    )
    parts.append(case_study_section)

    context = "\n\n".join(parts)

    # Truncate A/B/C from the END while always preserving case study section
    if len(context) > MAX_CONTEXT_CHARS:
        budget = MAX_CONTEXT_CHARS - len(case_study_section) - 200
        truncated_parts = []
        current_len = 0
        for part in parts[:-1]:
            if current_len + len(part) + 2 > budget:
                truncated_parts.append("[... context truncated to fit token limit ...]")
                break
            truncated_parts.append(part)
            current_len += len(part) + 2
        truncated_parts.append(case_study_section)
        context = "\n\n".join(truncated_parts)

    return context


def call_openrouter(
    system_prompt: str,
    user_message: str,
    model: str,
    max_tokens: int = 8000,
) -> str:
    """POST to OpenRouter and return the assistant message content."""
    api_key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dukemawex/IFRX",
        "X-Title": "IFRS-PhD-Proposal-Generator",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }

    # Rate-limit pause before every call
    time.sleep(2)

    response = requests.post(OPENROUTER_BASE, headers=headers, json=payload, timeout=120)

    if response.status_code == 429:
        print("[synthesis_agent] HTTP 429 — waiting 60 seconds before retry...")
        time.sleep(60)
        response = requests.post(
            OPENROUTER_BASE, headers=headers, json=payload, timeout=120
        )

    if response.status_code in (404, 503) and model == PRIMARY_MODEL:
        print(
            f"[synthesis_agent] HTTP {response.status_code} on primary model — switching to {FALLBACK_MODEL}"
        )
        payload["model"] = FALLBACK_MODEL
        response = requests.post(
            OPENROUTER_BASE, headers=headers, json=payload, timeout=120
        )

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter API error {response.status_code}: {response.text[:500]}"
        )

    data = response.json()

    # OpenRouter may return a 200 with an error body (e.g. context-length exceeded,
    # quota exhausted, or an upstream provider error).
    if "error" in data:
        err = data["error"]
        raise RuntimeError(
            f"OpenRouter returned an error in the response body "
            f"(HTTP {response.status_code}, model={payload['model']}): {err}"
        )

    choices = data.get("choices")
    if not choices:
        raise RuntimeError(
            f"OpenRouter response contained no choices "
            f"(HTTP {response.status_code}, model={payload['model']}). "
            f"Full response: {data}"
        )

    message = choices[0].get("message", {})
    content = message.get("content")
    if not content:
        raise RuntimeError(
            f"OpenRouter choice[0] has no 'content' field "
            f"(HTTP {response.status_code}, model={payload['model']}). "
            f"Choice: {choices[0]}"
        )

    return content


def main() -> None:
    prompts_path = Path("prompts/synthesis_system.txt")
    if not prompts_path.exists():
        raise FileNotFoundError(f"{prompts_path} not found")

    system_prompt = prompts_path.read_text()

    research = load_research()
    context_str = build_context(research)

    instruction = (
        "Using ALL sources above — [TAV-N:SEARCH] Tavily standard search results, "
        "[TAV-N:EXTRACT] Tavily full-page extractions from authoritative URLs, "
        "[DEEP-N] Tavily deep research synthesis reports, and "
        "the UNION BANK LIVE + BASELINE CASE STUDY DATA — "
        "write a complete PhD research proposal in valid JSON only. "
        "No markdown fences. No preamble. Output only the JSON object. "
        "Follow EVERY instruction in the system prompt exactly. "
        "Use only real, verifiable sources present in the context above for all citations."
    )

    user_message = context_str + "\n\n---\n" + instruction

    tav_count = len(research.get("tavily_results", []))
    deep_count = len(research.get("tavily_research", []))
    print(
        f"[synthesis_agent] Sources loaded: "
        f"Tavily={tav_count}, DeepResearch={deep_count}. "
        f"Context: {len(user_message)} chars. "
        f"Calling OpenRouter ({PRIMARY_MODEL})..."
    )

    raw = call_openrouter(system_prompt, user_message, PRIMARY_MODEL)

    # Strip accidental markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    research_dir = Path("research")
    research_dir.mkdir(exist_ok=True)

    try:
        proposal = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raw_path = research_dir / "proposal_raw.txt"
        raw_path.write_text(raw)
        print(
            f"[synthesis_agent] ERROR: Failed to parse JSON response. "
            f"Raw output saved to {raw_path}. JSONDecodeError: {exc}"
        )
        sys.exit(1)

    output_path = research_dir / "proposal_draft.json"
    output_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False))

    section_keys = list(proposal.keys())
    print(
        f"[synthesis_agent] Proposal written to {output_path}. "
        f"Sections found: {section_keys}"
    )


if __name__ == "__main__":
    main()
