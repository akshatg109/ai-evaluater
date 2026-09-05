"""Reusable PDF report generation."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _safe_paragraph(value):
    """Escape model text before handing it to ReportLab's markup parser."""
    return escape(str(value or "")).replace("\n", "<br/>")


def generate_evaluation_report(data, include_date=False):
    """Return an in-memory PDF report for a current or historical evaluation."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], fontSize=24,
        textColor=colors.HexColor("#8b5cf6"), spaceAfter=12,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "ReportHeading", parent=styles["Heading2"], fontSize=14,
        textColor=colors.HexColor("#3b82f6"), spaceAfter=10, spaceBefore=12,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "ReportBody", parent=styles["Normal"], fontSize=11,
        spaceAfter=10, alignment=TA_JUSTIFY,
    )
    metadata_style = ParagraphStyle(
        "ReportMetadata", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#666666"), spaceAfter=4,
    )

    story = [
        Paragraph("AI Answer Sheet Evaluation Report", title_style),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#8b5cf6")),
        Spacer(1, 12),
    ]
    if include_date:
        story.extend([
            Paragraph(f"<b>Evaluation Date:</b> {_safe_paragraph(data.get('created_at'))}", metadata_style),
            Spacer(1, 12),
        ])

    score_table = Table([["Suggested Marks", str(data.get("score", 0))]], colWidths=[2 * inch, 2 * inch])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#8b5cf6")),
        ("TEXTCOLOR", (0, 0), (1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (1, 0), "CENTER"),
        ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (1, 0), 12),
        ("TOPPADDING", (0, 0), (1, 0), 12),
        ("BOTTOMPADDING", (0, 0), (1, 0), 12),
        ("GRID", (0, 0), (1, 0), 1, colors.HexColor("#e0e0e0")),
    ]))
    story.extend([
        score_table,
        Spacer(1, 20),
        Paragraph("Examiner Feedback", heading_style),
        Paragraph(_safe_paragraph(data.get("feedback")), body_style),
        Spacer(1, 18),
        PageBreak(),
        Paragraph("Question Paper", heading_style),
        Paragraph(_safe_paragraph(data.get("question")), body_style),
        Spacer(1, 20),
        PageBreak(),
        Paragraph("Student Answer", heading_style),
        Paragraph(_safe_paragraph(data.get("answer")), body_style),
    ])
    if data.get("answer_key"):
        story.extend([
            Spacer(1, 20),
            PageBreak(),
            Paragraph("Answer Key", heading_style),
            Paragraph(_safe_paragraph(data.get("answer_key")), body_style),
        ])

    document.build(story)
    buffer.seek(0)
    return buffer
