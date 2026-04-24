"""
Agent 6 — docx_writer.py
Builds a PhD-format Word document from research/proposal_draft.json and
research/case_study_data.json, saving to output/proposal_ifrs_union_bank.docx.
"""

import json
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# ── Style constants ────────────────────────────────────────────────────────────
HEADING_COLOR = RGBColor(0x1A, 0x37, 0x6C)  # navy blue
FONT_NAME = "Times New Roman"
BODY_SIZE = Pt(12)
REF_SIZE = Pt(11)
TITLE_SIZE = Pt(16)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _set_font(run, size=None, bold=False, italic=False, color=None):
    run.font.name = FONT_NAME
    if size:
        run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color


def _heading(doc: Document, text: str, level: int = 1) -> None:
    """Add a styled heading paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    _set_font(run, size=Pt(13) if level == 1 else Pt(12), bold=True, color=HEADING_COLOR)


def _body(doc: Document, text: str) -> None:
    """Add a body paragraph."""
    p = doc.add_paragraph(style="Normal")
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(str(text))
    _set_font(run)


def _numbered_list(doc: Document, items: list) -> None:
    for i, item in enumerate(items, start=1):
        p = doc.add_paragraph(style="Normal")
        p.paragraph_format.left_indent = Inches(0.25)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(f"{i}. {item}")
        _set_font(run)


def _set_margins(doc: Document) -> None:
    for section in doc.sections:
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)


def _table_header_row(table, headers: list[str]) -> None:
    row = table.rows[0]
    for i, hdr in enumerate(headers):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(hdr)
        _set_font(run, bold=True)


def _add_table_row(table, values: list[str]) -> None:
    row = table.add_row()
    for i, val in enumerate(values):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(val))
        _set_font(run, size=Pt(10))


def _shade_row(row, hex_color: str = "D9E1F2") -> None:
    """Apply background shading to a table row."""
    for cell in row.cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)


# ── Main builder ───────────────────────────────────────────────────────────────

def build_document(proposal: dict, case_study: dict) -> Document:
    doc = Document()
    _set_margins(doc)

    # Default paragraph style
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = BODY_SIZE

    # ── 1. Cover page ──────────────────────────────────────────────────────────
    cover = proposal.get("cover_page", {})
    if isinstance(cover, dict):
        title_text = cover.get("title", "")
        author_text = cover.get("author", "")
        institution_text = cover.get("institution", "")
        date_text = cover.get("date", datetime.now().strftime("%B %Y"))
    else:
        title_text = str(cover)
        author_text = ""
        institution_text = ""
        date_text = datetime.now().strftime("%B %Y")

    for _ in range(4):
        doc.add_paragraph()  # vertical spacing

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(
        title_text or (
            "The Effect of International Financial Reporting Standards (IFRS) on "
            "Going Concern Assessment and Financial Stability in the Nigerian Banking "
            "Sector: A Case Study of Union Bank of Nigeria PLC (2012–2022)"
        )
    )
    _set_font(title_run, size=TITLE_SIZE, bold=True, color=HEADING_COLOR)

    for line in [author_text, institution_text, date_text]:
        if line:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line)
            _set_font(run)

    doc.add_page_break()

    # ── 2. Abstract ────────────────────────────────────────────────────────────
    _heading(doc, "ABSTRACT")
    _body(doc, proposal.get("abstract", ""))
    doc.add_page_break()

    # ── 3. Table of Contents placeholder ──────────────────────────────────────
    _heading(doc, "TABLE OF CONTENTS")
    p = doc.add_paragraph()
    run = p.add_run(
        "[Please update the Table of Contents in Microsoft Word: "
        "References → Update Table → Update entire table]"
    )
    run.font.italic = True
    run.font.name = FONT_NAME
    doc.add_page_break()

    # ── 4. Introduction ────────────────────────────────────────────────────────
    _heading(doc, "1. INTRODUCTION")
    _body(doc, proposal.get("introduction", ""))

    # ── 5. Statement of the Problem ────────────────────────────────────────────
    _heading(doc, "2. STATEMENT OF THE PROBLEM")
    _body(doc, proposal.get("statement_of_problem", ""))

    # ── 6. Research Objectives ─────────────────────────────────────────────────
    _heading(doc, "3. RESEARCH OBJECTIVES")
    objectives = proposal.get("research_objectives", [])
    if isinstance(objectives, list):
        _numbered_list(doc, objectives)
    else:
        _body(doc, str(objectives))

    # ── 7. Research Questions ──────────────────────────────────────────────────
    _heading(doc, "4. RESEARCH QUESTIONS")
    questions = proposal.get("research_questions", [])
    if isinstance(questions, list):
        _numbered_list(doc, questions)
    else:
        _body(doc, str(questions))

    # ── 8. Research Hypotheses ─────────────────────────────────────────────────
    _heading(doc, "5. RESEARCH HYPOTHESES")
    hypotheses = proposal.get("research_hypotheses", [])
    if isinstance(hypotheses, list):
        for i, hyp in enumerate(hypotheses, start=1):
            if isinstance(hyp, dict):
                p = doc.add_paragraph(style="Normal")
                p.paragraph_format.space_after = Pt(2)
                run_h = p.add_run(f"H{i}: ")
                _set_font(run_h, bold=True)
                null_run = p.add_run(f"H₀: {hyp.get('null', '')}  ")
                _set_font(null_run)
                alt_run = p.add_run(f"Hₐ: {hyp.get('alternate', '')}")
                _set_font(alt_run)
            else:
                _body(doc, str(hyp))
    else:
        _body(doc, str(hypotheses))

    # ── 9. Significance of the Study ──────────────────────────────────────────
    _heading(doc, "6. SIGNIFICANCE OF THE STUDY")
    _body(doc, proposal.get("significance_of_study", ""))

    # ── 10. Scope and Delimitation ─────────────────────────────────────────────
    _heading(doc, "7. SCOPE AND DELIMITATION")
    _body(doc, proposal.get("scope_and_delimitation", ""))

    doc.add_page_break()

    # ── 11. Literature Review ──────────────────────────────────────────────────
    _heading(doc, "8. LITERATURE REVIEW")
    lit_review = proposal.get("literature_review", {})
    if isinstance(lit_review, dict):
        for sub_key, sub_text in lit_review.items():
            sub_heading = sub_key.replace("_", " ").title()
            _heading(doc, f"8.{list(lit_review.keys()).index(sub_key) + 1} {sub_heading}", level=2)
            _body(doc, str(sub_text))
    else:
        _body(doc, str(lit_review))

    # ── 12. Theoretical Framework ──────────────────────────────────────────────
    _heading(doc, "9. THEORETICAL FRAMEWORK")
    _body(doc, proposal.get("theoretical_framework", ""))

    # ── 13. Research Gaps ─────────────────────────────────────────────────────
    _heading(doc, "10. IDENTIFICATION OF RESEARCH GAPS")
    gaps = proposal.get("research_gaps", [])
    if isinstance(gaps, list):
        for gap in gaps:
            p = doc.add_paragraph(style="Normal")
            p.paragraph_format.space_after = Pt(6)
            gap_str = str(gap)
            # Bold the "GAP N:" prefix
            if gap_str.upper().startswith("GAP"):
                colon_idx = gap_str.find(":")
                if colon_idx != -1:
                    label = gap_str[: colon_idx + 1]
                    rest = gap_str[colon_idx + 1 :]
                    bold_run = p.add_run(label)
                    _set_font(bold_run, bold=True)
                    rest_run = p.add_run(rest)
                    _set_font(rest_run)
                else:
                    run = p.add_run(gap_str)
                    _set_font(run)
            else:
                run = p.add_run(gap_str)
                _set_font(run)
    else:
        _body(doc, str(gaps))

    doc.add_page_break()

    # ── 14. Research Methodology ───────────────────────────────────────────────
    _heading(doc, "11. RESEARCH METHODOLOGY")
    methodology = proposal.get("methodology", {})
    if isinstance(methodology, dict):
        sub_labels = {
            "research_philosophy": "Research Philosophy",
            "research_design": "Research Design",
            "population_and_sampling": "Population and Sampling",
            "data_collection": "Data Collection",
            "model_specification": "Model Specification",
            "analytical_techniques": "Analytical Techniques",
        }
        for idx, (sub_key, sub_label) in enumerate(sub_labels.items(), start=1):
            if sub_key in methodology:
                _heading(doc, f"11.{idx} {sub_label}", level=2)
                _body(doc, str(methodology[sub_key]))
        # Any extra keys not in the labels dict
        for sub_key, sub_val in methodology.items():
            if sub_key not in sub_labels:
                _heading(doc, sub_key.replace("_", " ").title(), level=2)
                _body(doc, str(sub_val))
    else:
        _body(doc, str(methodology))

    # ── 15. Data Sources and Variable Operationalisation ──────────────────────
    _heading(doc, "12. DATA SOURCES AND VARIABLE OPERATIONALISATION")
    variables = proposal.get("data_sources_and_variables", [])
    if isinstance(variables, list) and variables:
        headers = ["Variable", "Proxy Measure", "Data Source", "Time Period"]
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        _table_header_row(table, headers)
        _shade_row(table.rows[0])
        for var in variables:
            if isinstance(var, dict):
                _add_table_row(
                    table,
                    [
                        var.get("variable", ""),
                        var.get("proxy", ""),
                        var.get("source", ""),
                        var.get("period", ""),
                    ],
                )
            else:
                _add_table_row(table, [str(var), "", "", ""])
        doc.add_paragraph()
    else:
        _body(doc, str(variables))

    # ── 16. Expected Findings ──────────────────────────────────────────────────
    _heading(doc, "13. EXPECTED FINDINGS AND CONTRIBUTION")
    _body(doc, proposal.get("expected_findings", ""))

    # ── 17. Ethical Considerations ─────────────────────────────────────────────
    _heading(doc, "14. ETHICAL CONSIDERATIONS")
    _body(doc, proposal.get("ethical_considerations", ""))

    doc.add_page_break()

    # ── 18. References ─────────────────────────────────────────────────────────
    _heading(doc, "REFERENCES")
    references = proposal.get("references", [])
    if isinstance(references, list):
        for ref in references:
            p = doc.add_paragraph(style="Normal")
            p.paragraph_format.first_line_indent = Inches(-0.5)
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(str(ref))
            run.font.name = FONT_NAME
            run.font.size = REF_SIZE
    else:
        _body(doc, str(references))

    doc.add_page_break()

    # ── 19. Appendices ─────────────────────────────────────────────────────────
    _heading(doc, "APPENDICES")
    _heading(doc, "Appendix A: Union Bank of Nigeria PLC — Financial Indicators 2015–2022", level=2)

    financial_data = case_study.get("financial_data_by_year", {})
    if financial_data:
        app_headers = ["Year", "NPL (%)", "CAR (%)", "ROA (%)", "GC Modified", "Audit Opinion"]
        app_table = doc.add_table(rows=1, cols=len(app_headers))
        app_table.style = "Table Grid"
        _table_header_row(app_table, app_headers)
        _shade_row(app_table.rows[0])
        for year, metrics in sorted(financial_data.items()):
            _add_table_row(
                app_table,
                [
                    year,
                    str(metrics.get("NPL_pct", "")),
                    str(metrics.get("CAR_pct", "")),
                    str(metrics.get("ROA_pct", "")),
                    "Yes" if metrics.get("going_concern_modified") else "No",
                    metrics.get("audit_opinion", ""),
                ],
            )
        doc.add_paragraph()

    source_note = doc.add_paragraph()
    note_run = source_note.add_run(
        "Sources: Union Bank of Nigeria PLC Annual Reports (2015–2022); "
        "CBN Banking Supervision Reports; NGX regulatory filings. "
        "GC Modified = Going Concern paragraph or Emphasis of Matter issued by auditors."
    )
    note_run.font.italic = True
    note_run.font.name = FONT_NAME
    note_run.font.size = Pt(10)

    return doc


def main() -> None:
    proposal_path = Path("research/proposal_draft.json")
    case_study_path = Path("research/case_study_data.json")

    if not proposal_path.exists():
        raise FileNotFoundError(f"{proposal_path} not found — run synthesis_agent first")
    if not case_study_path.exists():
        raise FileNotFoundError(f"{case_study_path} not found — run case_study_agent first")

    proposal = json.loads(proposal_path.read_text())
    case_study = json.loads(case_study_path.read_text())

    doc = build_document(proposal, case_study)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "proposal_ifrs_union_bank.docx"
    doc.save(str(output_path))
    print(f"[docx_writer] Document saved to {output_path}")


if __name__ == "__main__":
    main()
