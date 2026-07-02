"""Run functional/performance tests and create equivalent JSON and PDF reports.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_pdf(report: dict, destination: Path) -> None:
    """Render a compact, paginated PDF from pytest's JSON report."""
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)

    def footer(canvas, doc) -> None:
        """Draw a stable report identifier and page number."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(18 * mm, 10 * mm, "HGPExamWorkFlowAndChat - automated test evidence")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    summary = report.get("summary", {})
    rows = [["Metric", "Value"]] + [[str(key).replace("_", " ").title(), str(value)] for key, value in summary.items()]
    table = Table(rows, colWidths=[70 * mm, 95 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [Paragraph("HGPExamWorkFlowAndChat Test Report", styles["Title"]),
             Paragraph(f"Generated {datetime.now(UTC).isoformat()}", styles["Normal"]), Spacer(1, 6 * mm), table,
             Spacer(1, 8 * mm), Paragraph("Test details", styles["Heading1"])]
    for test in report.get("tests", []):
        name = str(test.get("nodeid", "unnamed test")).replace("::", " - ").replace("_", " ")
        outcome = str(test.get("outcome", "unknown")).upper()
        duration = sum(float(test.get(stage, {}).get("duration", 0)) for stage in ("setup", "call", "teardown"))
        story.append(Paragraph(f"{outcome} - {name}", styles["Heading3"]))
        story.append(Paragraph(f"Duration: {duration:.6f} seconds", styles["Normal"]))
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    """Execute pytest once and convert its machine report to a PDF."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/test-reports")
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "test-report.json"
    command = [sys.executable, "-m", "pytest", "--json-report", f"--json-report-file={json_path}", *args.pytest_args]
    result = subprocess.run(command, check=False)
    if json_path.exists():
        report = json.loads(json_path.read_text(encoding="utf-8"))
        build_pdf(report, output / "test-report.pdf")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
