# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for reports."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_exam_report(data: dict) -> bytes:
    """Perform the generate exam report operation."""
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#17233B"), spaceAfter=8))
    styles.add(ParagraphStyle(name="Banner", parent=styles["BodyText"], alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=colors.white, backColor=colors.HexColor("#2C716D"), borderPadding=8, spaceAfter=12))
    styles.add(ParagraphStyle(name="Question", parent=styles["Heading2"], textColor=colors.HexColor("#17233B"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#4C5568")))

    def footer(canvas, document):
        """Perform the footer operation."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 12 * mm, f"HGPExamWorkFlowAndChat - Evidence report {data['submission_id']}")
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Examination report - {data['exam_title']}",
        author="HGPExamWorkFlowAndChat",
    )
    story = [
        Paragraph("EXAMINATION REPORT", styles["Small"]),
        Paragraph(escape(data["exam_title"]), styles["ReportTitle"]),
        Paragraph(
            "PRACTICE EXAM - AI-ONLY, NOT INSTRUCTOR REVIEWED"
            if data["exam_kind"] == "practice"
            else "REAL EXAM - INSTRUCTOR REVIEWED AND SIGNED",
            styles["Banner"],
        ),
    ]
    summary = [
        ["Student", escape(data["student_name"])],
        ["Course", escape(data["course_title"])],
        ["Submitted", escape(data["submitted_at"])],
        ["Returned", escape(data.get("returned_at") or "Immediate practice feedback")],
        ["Score", f"{data['total_score']:.2f} / {data['maximum_score']:.2f}"],
        ["Status", escape(data["status"])],
    ]
    if data.get("exam_group"):
        summary.insert(1, ["Exam group", escape(data["exam_group"])])
    conversions = data.get("grade_conversions", {})
    if conversions:
        summary.extend([
            ["Percentage", f"{conversions.get('percentage', 0):.2f}%"],
            ["ECTS", escape(str(conversions.get("ects", "")))],
            ["German scale", escape(str(conversions.get("germany", "")))],
            ["British scale", escape(str(conversions.get("united_kingdom", "")))],
            ["US scale", escape(f"{conversions.get('united_states', {}).get('letter', '')} / GPA {conversions.get('united_states', {}).get('gpa_4', '')}")],
        ])
    table = Table(summary, colWidths=[38 * mm, 120 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBE6DA")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8D1C2")),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([table, Spacer(1, 8 * mm), Paragraph("Question scoring", styles["Heading1"])])

    for index, item in enumerate(data["questions"], start=1):
        metrics = item.get("signals", {})
        metric_text = ", ".join(f"{name}: {value:.3f}" for name, value in metrics.items() if value is not None)
        block = [
            Paragraph(f"{index}. {escape(item['prompt'])}", styles["Question"]),
            Paragraph(f"<b>Student answer:</b> {escape(item['answer'])}", styles["BodyText"]),
            Spacer(1, 2 * mm),
            Paragraph(f"<b>Score:</b> {item['score']:.2f} / {item['max_score']:.2f}", styles["BodyText"]),
            Paragraph(f"<b>Metrics:</b> {escape(metric_text or 'No metric details available')}", styles["Small"]),
        ]
        if item.get("feedback"):
            block.append(Paragraph(f"<b>Feedback:</b> {escape(item['feedback'])}", styles["BodyText"]))
        story.append(KeepTogether(block))

    story.extend([
        Spacer(1, 8 * mm),
        Paragraph("Academic integrity and writing review", styles["Heading1"]),
    ])
    integrity = data.get("academic_integrity_review")
    if integrity:
        similarity = integrity.get("internet_similarity", {})
        apa = integrity.get("apa", {})
        grammar = integrity.get("grammar", {})
        story.extend([
            Paragraph(f"Internet similarity status: {escape(str(similarity.get('status', 'unknown')))}; maximum lexical similarity: {float(similarity.get('maximum_similarity', 0)):.3f}", styles["Small"]),
            Paragraph(f"APA-style citations detected: {int(apa.get('citation_count', 0))}; reference section: {bool(apa.get('has_reference_section', False))}", styles["Small"]),
            Paragraph(f"Grammar review status: {escape(str(grammar.get('status', 'unknown')))}; issues: {int(grammar.get('issue_count', len(grammar.get('issues', []))))}", styles["Small"]),
            Paragraph("Similarity is evidence for instructor review and is not an automatic plagiarism decision.", styles["Small"]),
        ])
    else:
        story.append(Paragraph("No academic-integrity review was stored for this submission.", styles["Small"]))
    if conversions:
        story.append(Paragraph(escape(str(conversions.get("disclaimer", ""))), styles["Small"]))
    story.extend([
        Spacer(1, 8 * mm),
        Paragraph("Evidence and signatures", styles["Heading1"]),
        Paragraph(f"Exam SHA-256: {escape(data['exam_sha256'])}", styles["Small"]),
        Paragraph(f"Student certificate SHA-256: {escape(data['student_certificate_sha256'])}", styles["Small"]),
        Paragraph(f"Student signature SHA-256: {escape(data['student_signature_sha256'])}", styles["Small"]),
        Paragraph(f"Grading SHA-256: {escape(data['grading_sha256'])}", styles["Small"]),
    ])
    if data.get("instructor_certificate_sha256"):
        story.extend([
            Paragraph(f"Instructor certificate SHA-256: {escape(data['instructor_certificate_sha256'])}", styles["Small"]),
            Paragraph(f"Instructor signature SHA-256: {escape(data['instructor_signature_sha256'])}", styles["Small"]),
            Paragraph(f"Instructor signed at: {escape(data['instructor_signed_at'])}", styles["Small"]),
        ])
    else:
        story.append(Paragraph("No instructor signature: this is an automated practice report.", styles["Small"]))
    story.extend([
        Spacer(1, 5 * mm),
        Paragraph("This report is generated from the immutable examination and grading records stored by the application. Verify the listed digests and signatures against the retained evidence package.", styles["Small"]),
    ])
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
