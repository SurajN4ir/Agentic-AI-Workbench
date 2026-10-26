"""
scripts/generate_synthetic_eval_fixtures.py
===========================================
Deterministic generator for synthetic industrial evaluation fixtures.
Creates:
  - Clean specification nameplate (PNG)
  - Ambiguous character tag with lookalikes (0/O, 1/I/l, 8/B, 5/S, 2/Z) (PNG)
  - Structured 2D telemetry table with cell borders (PNG)
  - Multi-page scanned document with zero native digital text (PDF)

All fixtures are stored inside eval/fixtures/ocr/.
Never accesses external network or personal host directories.
"""

from pathlib import Path

from PIL import Image, ImageDraw

FIXTURE_DIR = Path("eval/fixtures/ocr")


def generate_clean_plate(output_path: Path) -> None:
    width, height = 600, 240
    img = Image.new("RGB", (width, height), color=(245, 245, 247))
    draw = ImageDraw.Draw(img)

    # Plate border
    draw.rectangle([(10, 10), (width - 10, height - 10)], outline=(30, 30, 35), width=3)
    draw.rectangle([(14, 14), (width - 14, height - 14)], outline=(120, 120, 130), width=1)

    lines = [
        "TURBINE GENERATOR TG-8500",
        "SERIAL: SN-TG8500-2026-X",
        "RATED CAPACITY: 1250 KW",
        "OPERATING SPEED: 3600 RPM",
        "MAX OIL TEMP: 85 C",
    ]

    y = 30
    for line in lines:
        draw.text((30, y), line, fill=(10, 10, 15))
        y += 38

    img.save(output_path, "PNG")


def generate_ambiguous_tag(output_path: Path) -> None:
    width, height = 550, 180
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(8, 8), (width - 8, height - 8)], outline=(40, 40, 40), width=2)

    lines = [
        "TAG-0O1Il8B5S2Z",
        "VALVE-O01-B8-S5-Z2",
        "SER-1I0O8B",
    ]

    y = 30
    for line in lines:
        draw.text((25, y), line, fill=(0, 0, 0))
        y += 42

    img.save(output_path, "PNG")


def generate_table_image(output_path: Path) -> None:
    width, height = 650, 260
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Table Grid
    headers = ["PUMP_ID", "PRESSURE_PSI", "FLOW_GPM", "TEMP_C", "STATUS"]
    rows = [
        ["P-101", "145.2", "320", "62.4", "NOMINAL"],
        ["P-102", "188.7", "410", "78.1", "ELEVATED"],
        ["P-103", "92.0", "150", "45.0", "STANDBY"],
    ]

    col_widths = [100, 140, 110, 110, 130]
    row_height = 45
    start_x, start_y = 30, 30

    total_w = sum(col_widths)
    total_h = (len(rows) + 1) * row_height

    # Outer border
    draw.rectangle([(start_x, start_y), (start_x + total_w, start_y + total_h)], outline=(0, 0, 0), width=2)

    # Horizontal lines
    for i in range(1, len(rows) + 1):
        line_y = start_y + i * row_height
        draw.line([(start_x, line_y), (start_x + total_w, line_y)], fill=(50, 50, 50), width=1)

    # Vertical lines
    curr_x = start_x
    for w in col_widths[:-1]:
        curr_x += w
        draw.line([(curr_x, start_y), (curr_x, start_y + total_h)], fill=(50, 50, 50), width=1)

    # Header text
    curr_x = start_x
    for header, w in zip(headers, col_widths, strict=True):
        draw.text((curr_x + 8, start_y + 14), header, fill=(0, 0, 0))
        curr_x += w

    # Row text
    for r_idx, row in enumerate(rows):
        curr_y = start_y + (r_idx + 1) * row_height + 14
        curr_x = start_x
        for val, w in zip(row, col_widths, strict=True):
            draw.text((curr_x + 8, curr_y), val, fill=(20, 20, 20))
            curr_x += w

    img.save(output_path, "PNG")


def generate_scanned_pdf(output_path: Path) -> None:
    width, height = 650, 400

    # Page 1
    p1 = Image.new("RGB", (width, height), color=(250, 250, 250))
    d1 = ImageDraw.Draw(p1)
    d1.rectangle([(15, 15), (width - 15, height - 15)], outline=(80, 80, 80), width=2)
    p1_lines = [
        "SOVEREIGN POWER SYSTEMS - FIELD INSPECTION LOG",
        "ASSET: STEAM TURBINE UNIT 4",
        "DATE: 2026-10-15",
        "INSPECTOR: ID-7742",
        "BEARING VIBRATION: 2.4 MM/S",
        "EXHAUST PRESSURE: 0.08 BAR",
    ]
    y = 40
    for line in p1_lines:
        d1.text((35, y), line, fill=(0, 0, 0))
        y += 45

    # Page 2
    p2 = Image.new("RGB", (width, height), color=(250, 250, 250))
    d2 = ImageDraw.Draw(p2)
    d2.rectangle([(15, 15), (width - 15, height - 15)], outline=(80, 80, 80), width=2)
    p2_lines = [
        "MAINTENANCE ACTION ITEMS:",
        "1. REPLACE HYDRAULIC FILTER HF-402 AT 12000 HOURS",
        "2. CALIBRATE GOVERNOR SENSOR GS-12",
        "3. RE-TORQUE CASING BOLTS TO 450 NM",
        "OVERALL STATUS: ACCEPTABLE",
    ]
    y = 40
    for line in p2_lines:
        d2.text((35, y), line, fill=(0, 0, 0))
        y += 45

    # Save as multi-page PDF (native image scan with no digital text)
    p1.save(output_path, "PDF", save_all=True, append_images=[p2])


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    generate_clean_plate(FIXTURE_DIR / "clean_specification_plate.png")
    generate_ambiguous_tag(FIXTURE_DIR / "ambiguous_serial_tag.png")
    generate_table_image(FIXTURE_DIR / "table_pump_telemetry.png")
    generate_scanned_pdf(FIXTURE_DIR / "scanned_turbine_inspection.pdf")
    print("All synthetic OCR evaluation fixtures generated successfully.")


if __name__ == "__main__":
    main()
