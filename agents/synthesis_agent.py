"""
Agent 5 — synthesis_agent.py
Calls OpenRouter free-tier LLM to synthesise all research into a PhD proposal.
Uses requests only — NO anthropic SDK.
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
    """Load and combine all research artefacts."""
    research_dir = Path("research")

    exa_path = research_dir / "exa_results.json"
    tavily_path = research_dir / "tavily_results.json"
    case_study_path = research_dir / "case_study_data.json"
    queries_path = research_dir / "queries.json"

    exa_results = []
    if exa_path.exists():
        exa_results = json.loads(exa_path.read_text())[:50]

    tavily_results = []
    if tavily_path.exists():
        tavily_results = json.loads(tavily_path.read_text())[:50]

    case_study_data = {}
    if case_study_path.exists():
        case_study_data = json.loads(case_study_path.read_text())

    queries_data = {}
    if queries_path.exists():
        queries_data = json.loads(queries_path.read_text())

    return {
        "exa_results": exa_results,
        "tavily_results": tavily_results,
        "case_study_data": case_study_data,
        "queries_data": queries_data,
    }


def build_context(research: dict) -> str:
    """Build a compact context string from research data."""
    parts: list[str] = []

    # Exa results
    for i, item in enumerate(research.get("exa_results", []), start=1):
        text_snippet = (item.get("text") or "")[:600]
        highlights = item.get("highlights") or []
        highlight_str = " | ".join(str(h) for h in highlights[:2])
        parts.append(
            f"[EXA-{i}] {item.get('title', '')} / {item.get('source', '')} / "
            f"{item.get('published_date', '')} / CLUSTER:{item.get('cluster', '')} / "
            f"{text_snippet} / HIGHLIGHTS: {highlight_str}"
        )

    # Tavily results
    for i, item in enumerate(research.get("tavily_results", []), start=1):
        content_snippet = (item.get("content") or item.get("raw_content") or "")[:600]
        parts.append(
            f"[TAV-{i}] {item.get('title', '')} / {item.get('source', '')} / "
            f"CLUSTER:{item.get('cluster', '')} / {content_snippet}"
        )

    # Case study data (full JSON)
    case_study_json = json.dumps(research.get("case_study_data", {}), indent=1)
    parts.append(f"\n--- UNION BANK CASE STUDY DATA ---\n{case_study_json}")

    context = "\n\n".join(parts)

    # Truncate from the end if too long, but always preserve the case study data
    if len(context) > MAX_CONTEXT_CHARS:
        # Preserve case study section at the end
        case_study_section = f"\n--- UNION BANK CASE STUDY DATA ---\n{case_study_json}"
        budget = MAX_CONTEXT_CHARS - len(case_study_section) - 200
        truncated_parts = []
        current_len = 0
        for part in parts[:-1]:  # exclude case study which is the last part
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

    if response.status_code == 503 and model == PRIMARY_MODEL:
        print(
            f"[synthesis_agent] HTTP 503 on primary model — switching to {FALLBACK_MODEL}"
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
    return data["choices"][0]["message"]["content"]


def main() -> None:
    prompts_path = Path("prompts/synthesis_system.txt")
    if not prompts_path.exists():
        raise FileNotFoundError(f"{prompts_path} not found")

    system_prompt = prompts_path.read_text()

    research = load_research()
    context_str = build_context(research)

    instruction = (
        "Using ALL sources above, write a complete PhD research proposal in valid JSON only. "
        "No markdown fences. No preamble. Output only the JSON object. "
        "Follow EVERY instruction in the system prompt exactly."
    )

    user_message = context_str + "\n\n---\n" + instruction

    print(
        f"[synthesis_agent] Context length: {len(user_message)} chars. "
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
