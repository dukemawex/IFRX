# IFRS PhD Proposal Generator

## Overview

This repository contains a GitHub Actions multi-agent pipeline that automatically
researches and writes a PhD-level research proposal on the topic:
**"The Effect of International Financial Reporting Standards (IFRS) on Going Concern
Assessment and Financial Stability in the Nigerian Banking Sector: A Case Study of
Union Bank of Nigeria PLC (2012–2022)"**. The pipeline orchestrates six Python agents
that decompose research queries, retrieve academic and financial data via the
**TinyFish** goal-directed automation API and Tavily, apply hardcoded Union Bank
secondary data, synthesise a complete proposal via an OpenRouter free-tier LLM, and
render the output as a formatted `.docx` Word document uploaded as a GitHub Actions
artifact.

---

## Repository Structure

```
.github/
  workflows/
    generate_proposal.yml   ← GitHub Actions orchestrator workflow
agents/
  orchestrator.py           ← Query decomposition (no API calls)
  exa_agent.py              ← Exa neural academic search
  tavily_agent.py           ← Tavily live web + finance search
  case_study_agent.py       ← Union Bank PLC hardcoded secondary data
  synthesis_agent.py        ← OpenRouter free-tier LLM synthesis
  docx_writer.py            ← PhD-format Word document builder
prompts/
  synthesis_system.txt      ← System prompt for synthesis agent
requirements.txt
.env.example                ← Example env vars (no real secrets)
README.md
```

---

## Setup

### GitHub Secrets Required

Add the following secrets to your repository under **Settings → Secrets and variables → Actions**:

| Secret Name          | Description                                                                             |
|----------------------|-----------------------------------------------------------------------------------------|
| `TINYFISH_API_KEY`   | TinyFish automation API key — [agent.tinyfish.ai](https://agent.tinyfish.ai)           |
| `TAVILY_API_KEY`     | Tavily API key — [tavily.com](https://tavily.com) (Research tier used)                 |
| `OPENROUTER_API_KEY` | OpenRouter API key — [openrouter.ai](https://openrouter.ai) (free tier sufficient)     |

### Local Development

1. Clone the repository and install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env and set real values for TINYFISH_API_KEY, TAVILY_API_KEY, OPENROUTER_API_KEY
```

3. Export the environment variables and run each agent in order:

```bash
export $(grep -v '^#' .env | xargs)

python agents/orchestrator.py
python agents/exa_agent.py
python agents/tavily_agent.py
python agents/case_study_agent.py
python agents/synthesis_agent.py
python agents/docx_writer.py
```

---

## Running the Pipeline

### Via GitHub Actions (recommended)

**Option A — Push trigger:**
Push any change to `agents/` or `prompts/` on the `main` branch. The workflow
triggers automatically.

**Option B — Manual trigger:**
1. Go to **Actions → Generate PhD Proposal — IFRS Union Bank**.
2. Click **Run workflow**.
3. Select the desired `depth` (quick | standard | deep; default: deep).
4. Click **Run workflow** to start.

Once the run completes, download the artifacts from the workflow summary page.

---

## Output

| Artifact Name                | Contents                                         | Retention |
|------------------------------|--------------------------------------------------|-----------|
| `phd-proposal-ifrs-union-bank` | `output/proposal_ifrs_union_bank.docx` — fully formatted PhD proposal with cover page, abstract, TOC placeholder, 14 numbered sections, references, and appendices | 30 days |
| `research-data-raw`           | `research/` directory — `queries.json`, `exa_results.json`, `tavily_results.json`, `case_study_data.json`, `proposal_draft.json` — full audit trail of all sources | 14 days |

### Document Structure

The `.docx` file contains the following sections in order:

1. Cover Page
2. Abstract
3. Table of Contents (placeholder — update in Word)
4. Introduction
5. Statement of the Problem
6. Research Objectives
7. Research Questions
8. Research Hypotheses
9. Significance of the Study
10. Scope and Delimitation
11. Literature Review (Conceptual / Theoretical / Empirical sub-sections)
12. Theoretical Framework
13. Identification of Research Gaps
14. Research Methodology
15. Data Sources and Variable Operationalisation (formatted table)
16. Expected Findings and Contribution
17. Ethical Considerations
18. References (APA 7th edition, hanging indent)
19. Appendix A: Union Bank Financial Indicators 2015–2022 (formatted table)
