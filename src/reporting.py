"""Report generation helpers for ARGUS."""
from __future__ import annotations
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def build_pdf_report(run: dict) -> bytes:
    """Build a PDF from an actual completed workflow result."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=17*mm, leftMargin=17*mm,
                            topMargin=16*mm, bottomMargin=16*mm, title="ARGUS Risk Assessment")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ArgusTitle", parent=styles["Title"], textColor=colors.HexColor("#17243A"), alignment=TA_LEFT, spaceAfter=5))
    styles.add(ParagraphStyle(name="ArgusSub", parent=styles["Normal"], textColor=colors.HexColor("#667085"), fontSize=9, leading=13))
    styles.add(ParagraphStyle(name="ArgusH", parent=styles["Heading2"], textColor=colors.HexColor("#234B86"), spaceBefore=10, spaceAfter=5))
    styles.add(ParagraphStyle(name="ArgusBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=4))
    story = [Paragraph("ARGUS | Corporate Risk Intelligence", styles["ArgusTitle"]),
             Paragraph("Financial risk assessment and decision-support brief", styles["ArgusSub"]), Spacer(1, 7*mm)]
    esc = lambda x: str(x if x is not None else "Not available").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    metadata = [["Company", esc(run.get("company")), "Period", esc(run.get("period"))],
                ["Data origin", esc(run.get("data_origin")), "Review", esc(run.get("review", {}).get("disposition"))],
                ["Run ID", esc(run.get("run_id")), "Generated", datetime.now().strftime("%Y-%m-%d %H:%M")]]
    t = Table(metadata, colWidths=[23*mm, 58*mm, 22*mm, 58*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F2F5FA")),
                           ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#F2F5FA")),
                           ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#17243A")),
                           ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#D9E0EA")),
                           ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 8),
                           ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story += [t, Spacer(1, 5*mm), Paragraph("Executive summary", styles["ArgusH"]),
              Paragraph(esc(run.get("synthesis_note", "No synthesis note available.")), styles["ArgusBody"])]
    review = run.get("review", {})
    story += [Paragraph("Independent review", styles["ArgusH"]),
              Paragraph(f"Disposition: <b>{esc(review.get('disposition'))}</b>. Human approval is required before acting on recommendations.", styles["ArgusBody"])]
    issues = review.get("issues", [])
    if issues:
        data = [["Severity", "Component", "Issue"]] + [[esc(i.get("severity")), esc(i.get("agent")), esc(i.get("issue"))] for i in issues]
        tbl = Table(data, colWidths=[23*mm, 47*mm, 91*mm], repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EAF0F8")), ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#D9E0EA")), ("FONTSIZE", (0,0), (-1,-1), 7.5), ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
        story += [tbl]
    story.append(Paragraph("Agent findings", styles["ArgusH"]))
    for agent in run.get("results", []):
        block = [Paragraph(f"<b>{esc(agent.get('agent_name'))}</b> | {esc(agent.get('status'))} | Risk: {esc(agent.get('risk_level'))}", styles["ArgusBody"]),
                 Paragraph(esc(agent.get("summary")), styles["ArgusBody"])]
        for finding in agent.get("findings", []):
            block.append(Paragraph("• " + esc(finding.get("text")) + (f" <font color='#667085'>[{esc(finding.get('type'))}]</font>"), styles["ArgusBody"]))
        if agent.get("limitations"):
            block.append(Paragraph("Limitations: " + esc("; ".join(agent["limitations"])), styles["ArgusSub"]))
        story.append(KeepTogether(block)); story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Recommendations", styles["ArgusH"]))
    recs = run.get("recommendations", [])
    if not recs:
        story.append(Paragraph("No recommendations were issued. This may occur when review rejects the run or the available data does not support a rule-based recommendation.", styles["ArgusBody"]))
    for rec in recs:
        story += [Paragraph(f"<b>[{esc(str(rec.get('urgency','')).upper())}] {esc(rec.get('action'))}</b>", styles["ArgusBody"]),
                  Paragraph(esc(rec.get("rationale")) + " | Horizon: " + esc(rec.get("horizon")) + " | Impact: " + esc(rec.get("quantified_impact")), styles["ArgusBody"]),
                  Paragraph("Limitations: " + esc(rec.get("limitations")), styles["ArgusSub"]), Spacer(1, 2*mm)]
    story += [Spacer(1, 5*mm), Paragraph("Important limitations", styles["ArgusH"]),
              Paragraph("This report is decision-support output, not investment advice, a credit rating, or an audit opinion. Synthetic data, assumptions, incomplete disclosures, and model uncertainty can materially affect results. Review source documents and obtain qualified human approval before making decisions.", styles["ArgusBody"])]
    doc.build(story)
    return buf.getvalue()
