"""Fill the original VVRV European Instruction paper template.

All EI sections remain printed, including unused sections. Only driver-side fields
are overlaid. This is an unvalidated administrative copy, not an operational EI.
"""
import io
import os
from pathlib import Path
from urllib.request import urlopen

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

TEMPLATE_URL = "https://vvrv.nl/uploads/files/page/forrmulier-european-instructions-trdl.pdf"
TEMPLATE_FILE = Path(os.getenv("EI_TEMPLATE_PATH", "/app/data/ei-original-vvrv.pdf"))
# Positions measured from the original paper sheet, normalized to its rendered
# 1024 x 1448 page. Origin for these coordinates is the TOP LEFT.
PAGE_W, PAGE_H = 1024, 1448

# Main EI-selection boxes: printed boxes are retained, tick is added only if used.
SELECTIONS = {
    "1": (48, 114), "2": (48, 202), "3": (48, 275),
    "4": (48, 345), "5": (48, 407), "6": (48, 559),
    "7": (48, 708), "8": (48, 824), "90": (48, 1117),
    "95": (48, 1290),
}
CHECKS = {
    "1": {"1.10": (94, 131), "1.20": (134, 151), "x.25": (134, 169)},
    "2": {"2.10": (94, 223), "2.11": (94, 240)},
    "3": {"3.10": (94, 296), "3.20": (94, 313)},
    "4": {"4.10": (94, 365)},
    "5": {"x.41": (94, 428)},
    "6": {"x.41": (94, 580)},
    "7": {"7.10": (94, 731), "7.11": (94, 750), "7.20": (134, 773)},
    "8": {"8.40": (94, 849), "8.50": (94, 914)},
}
# Field locations (x-left, y-top, x-right, y-bottom) on the original.
FIELDS = {
    "1": {"location": (443, 143, 638, 173)},
    "4": {"instruction_id": (333, 353, 496, 380)},
    "5": {"speed": (447, 413, 638, 443), "between": (190, 455, 382, 484),
          "and": (447, 455, 638, 484), "from": (190, 499, 382, 527),
          "to": (447, 499, 638, 527)},
    "6": {"speed": (447, 564, 638, 594), "between": (190, 605, 382, 634),
          "and": (447, 605, 638, 634), "from": (190, 649, 382, 677),
          "to": (447, 649, 638, 677)},
    "7": {"signal": (374, 759, 537, 786)},
    "8": {"between": (190, 866, 382, 894), "and": (447, 866, 638, 894),
          "km1": (110, 930, 273, 959), "km2": (293, 930, 457, 959),
          "km3": (477, 930, 640, 959), "km4": (110, 971, 273, 999),
          "km5": (293, 971, 457, 999), "km6": (477, 971, 640, 999),
          "km7": (110, 1011, 273, 1040), "km8": (293, 1011, 457, 1040),
          "km9": (477, 1011, 640, 1040)},
    "90": {"reason": (68, 1131, 638, 1204), "report": (68, 1231, 638, 1261)},
    "95": {"instruction": (68, 1307, 638, 1379)},
}


def get_template():
    if not TEMPLATE_FILE.is_file():
        TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Fetch the official original once and keep a stable local copy.
        with urlopen(TEMPLATE_URL, timeout=15) as response:
            data = response.read(3_000_001)
        if len(data) > 3_000_000 or not data.startswith(b"%PDF-"):
            raise ValueError("Het originele EI-PDF-bestand is ongeldig")
        PdfReader(io.BytesIO(data))  # verify PDF before caching
        temp = TEMPLATE_FILE.with_suffix(".tmp")
        temp.write_bytes(data)
        temp.replace(TEMPLATE_FILE)
    reader = PdfReader(str(TEMPLATE_FILE))
    if len(reader.pages) != 1:
        raise ValueError("Onverwacht aantal pagina's in EI-bronformulier")
    return reader


def build_ei_pdf(payload):
    original = get_template()
    page = original.pages[0]
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    sx, sy = width / PAGE_W, height / PAGE_H
    overlay = io.BytesIO()
    c = canvas.Canvas(overlay, pagesize=(width, height))
    selected = {str(n) for n in payload.get("selected", [])}
    checks = payload.get("checks") or {}
    details = payload.get("details") or {}

    def position(x, y):
        return x*sx, height-y*sy

    def tick(x, y):
        px, py = position(x, y)
        c.setStrokeColorRGB(0.06, 0.52, 0.20)
        c.setLineWidth(1.7*sx)
        c.line(px-3*sx, py, px, py-4*sy)
        c.line(px, py-4*sy, px+6*sx, py+6*sy)

    def fill(box, value, multiline=False):
        if value is None or str(value).strip() == "":
            return
        x1, y1, x2, y2 = box
        text = str(value).replace("\r", "")
        c.saveState()
        c.setFillColorRGB(0.04, 0.04, 0.04)
        font_size = (10 if not multiline else 9)*sx
        c.setFont("Helvetica", font_size)
        left, top = position(x1+6, y1+8)
        bottom = height-(y2-3)*sy
        lines = text.split("\n") if multiline else [text.replace("\n", " ")]
        # Clip to the actual field: never print over adjacent official labels.
        clip = c.beginPath()
        clip.rect(x1*sx, height-y2*sy, (x2-x1)*sx, (y2-y1)*sy)
        c.clipPath(clip, stroke=0, fill=0)
        y = top - 9*sy
        for line in lines:
            if y < bottom:
                break
            c.drawString(left, y, line)
            y -= 13*sy
        c.restoreState()

    for number in selected:
        if number not in SELECTIONS:
            raise ValueError("Onbekende EI-selectie")
        tick(*SELECTIONS[number])
        values = checks.get(number) or {}
        if isinstance(values, dict):
            for code, enabled in values.items():
                if enabled and code in CHECKS.get(number, {}):
                    tick(*CHECKS[number][code])
        inputs = details.get(number) or {}
        if isinstance(inputs, dict):
            for key, box in FIELDS.get(number, {}).items():
                fill(box, inputs.get(key), multiline=number in ("90", "95"))

    # Identification goes in the official identification box; no right-hand
    # train-dispatcher fields or signatures are fabricated.
    fill((690, 69, 905, 90), payload.get("identification", ""))
    # Date and time are printed in the administrative footer, outside EI fields.
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 7*sx)
    c.drawString(*position(20, 1438),
                 ("Archief: " + str(payload.get("date", "")) + " " +
                  str(payload.get("time", "")))[:65])
    c.save()
    overlay.seek(0)
    writer = PdfWriter()
    page.merge_page(PdfReader(overlay).pages[0])
    writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
