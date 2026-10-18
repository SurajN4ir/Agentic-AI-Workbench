#!/usr/bin/env python3
"""
generate_demo_assets.py — Generate Standardized Synthetic Industrial Demo Assets
================================================================================
Creates the reproducible dataset for AeroTurbine Dynamics Ltd. (SIH PS 26117):
1. turbine_maintenance_spec_v4.docx — Operating limits and overhaul specifications.
2. q3_inspection_report.docx — Field inspection report with measurements and notes.
3. production_defect_metrics_q3.xlsx — Tabular defect metrics across 12 assembly lines.
"""

from __future__ import annotations

from pathlib import Path

import docx
import openpyxl
from docx.shared import Pt, RGBColor
from openpyxl.styles import Alignment, Font, PatternFill

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_assets"
DEMO_DIR.mkdir(parents=True, exist_ok=True)


def generate_defect_metrics_xlsx() -> Path:
    """Generate production_defect_metrics_q3.xlsx."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Q3_Defect_Log"

    headers = [
        "machine_id",
        "assembly_line",
        "operating_hours",
        "measured_vibration_rms",
        "bearing_temp_c",
        "defect_count",
        "critical_flaw_flag",
    ]
    ws.append(headers)

    # Style header
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

    for _col_idx, cell in enumerate(ws[1], start=1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    rows = [
        ["M-101", "Turbine-Line-A", 1420, 3.2, 142.5, 4, "NO"],
        ["M-102", "Turbine-Line-A", 1850, 4.1, 168.0, 9, "NO"],
        ["M-103", "Turbine-Line-B", 2100, 3.8, 155.2, 7, "NO"],
        ["M-104", "Turbine-Line-B", 3450, 5.8, 192.4, 47, "YES"],  # Highest defect count + exceeds vibration limit (5.8 > 4.5)
        ["M-105", "Turbine-Line-C", 1120, 2.9, 138.1, 2, "NO"],
        ["M-106", "Turbine-Line-C", 2980, 4.4, 178.6, 18, "NO"],
        ["M-107", "Turbine-Line-A", 1640, 3.5, 149.0, 5, "NO"],
        ["M-108", "Turbine-Line-B", 2750, 4.2, 171.3, 12, "NO"],
        ["M-109", "Turbine-Line-C", 3100, 4.7, 186.5, 23, "YES"],
        ["M-110", "Turbine-Line-A", 980, 2.4, 130.2, 1, "NO"],
        ["M-111", "Turbine-Line-B", 1950, 3.9, 160.4, 8, "NO"],
        ["M-112", "Turbine-Line-C", 2400, 4.0, 165.8, 11, "NO"],
    ]

    for row in rows:
        ws.append(row)

    # Auto adjust column width
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    out_file = DEMO_DIR / "production_defect_metrics_q3.xlsx"
    wb.save(out_file)
    print(f"Generated: {out_file.name} ({out_file.stat().st_size} bytes)")
    return out_file


def generate_maintenance_spec_docx() -> Path:
    """Generate turbine_maintenance_spec_v4.docx."""
    doc = docx.Document()

    # Document Header
    p_title = doc.add_heading("AeroTurbine Dynamics Ltd. — Technical Specification", level=0)
    p_title.runs[0].font.name = "Segoe UI"
    p_title.runs[0].font.size = Pt(20)
    p_title.runs[0].font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

    doc.add_paragraph("Document ID: ATD-SPEC-2026-V4 | Classification: CONFIDENTIAL INDUSTRIAL")
    doc.add_paragraph("Scope: High-Pressure Industrial Gas Turbine Operations & Threshold Compliance\n")

    # Section 1
    doc.add_heading("1. Operating Tolerances & Vibration Limits", level=1)
    doc.add_paragraph(
        "Industrial gas turbines operating in continuous production must maintain root-mean-square "
        "(RMS) vibration velocities strictly below the critical engineering threshold:"
    )

    p_limit = doc.add_paragraph()
    run_limit = p_limit.add_run("• Maximum Permissible Vibration Velocity: 4.5 mm/s RMS (ISO 10816-3 Class III)")
    run_limit.bold = True
    run_limit.font.color.rgb = RGBColor(0xB9, 0x1C, 0x1C)

    doc.add_paragraph("• Maximum Continuous Bearing Temperature: 185.0 °C")
    doc.add_paragraph("• Mandatory Overhaul Interval: 3,000 Operating Hours")

    # Section 2
    doc.add_heading("2. Mandatory Action Protocol for Exceeded Limits", level=1)
    doc.add_paragraph(
        "If any turbine exhibits measured vibration exceeding 4.5 mm/s RMS or bearing temperatures above 185.0 °C:\n"
        "1. Immediate emergency shutdown and rotor de-coupling within 2 hours of telemetry alarm.\n"
        "2. Ultrasonic non-destructive testing (NDT) on high-pressure compressor stage blades.\n"
        "3. Complete bearing housing lubrication flush and replacement of dynamic seal assemblies.\n"
        "4. Any unit exceeding 30 defects per quarter must undergo full rotor re-balancing prior to re-commissioning."
    )

    out_file = DEMO_DIR / "turbine_maintenance_spec_v4.docx"
    doc.save(str(out_file))
    print(f"Generated: {out_file.name} ({out_file.stat().st_size} bytes)")
    return out_file


def generate_inspection_report_docx() -> Path:
    """Generate q3_inspection_report.docx."""
    doc = docx.Document()

    doc.add_heading("Field Engineering Q3 Inspection Report", level=0)
    doc.add_paragraph("Facility: North Industrial Plant — AeroTurbine Assembly Facility")
    doc.add_paragraph("Lead Field Inspector: Dr. H. Vance, Senior Reliability Engineer\n")

    doc.add_heading("Summary of Field Observations", level=1)
    doc.add_paragraph(
        "Quarterly diagnostic inspection across Turbine Lines A, B, and C was conducted between Sept 15 and Sept 30. "
        "Overall mechanical integrity remains nominal across Line A and Line C. "
        "However, significant acoustic anomalies and high-frequency harmonic hum were observed on Turbine Line B."
    )

    doc.add_heading("Key Line B Diagnostic Findings", level=1)
    doc.add_paragraph(
        "Machine M-104 currently records the highest cumulative operating runtime (3,450 hours), exceeding the recommended "
        "3,000-hour overhaul limit. Telemetry sensors indicate severe vibration peaking at 5.8 mm/s RMS, accompanied by bearing "
        "temperature spikes reaching 192.4 °C. "
        "Visual borescope inspection confirmed blade micro-pitting and seal degradation."
    )

    out_file = DEMO_DIR / "q3_inspection_report.docx"
    doc.save(str(out_file))
    print(f"Generated: {out_file.name} ({out_file.stat().st_size} bytes)")
    return out_file


def main() -> None:
    print("\nGenerating synthetic industrial demo assets for AeroTurbine Dynamics Ltd...")
    generate_defect_metrics_xlsx()
    generate_maintenance_spec_docx()
    generate_inspection_report_docx()
    print("All demo assets successfully generated in demo_assets/\n")


if __name__ == "__main__":
    main()
