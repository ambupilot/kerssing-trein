"""Printable archival summary of a completed European Instruction.

This is an administrative record, NOT a replacement for the official railway form.
"""
import io
import json
from xml.sax.saxutils import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

SCHEMA_PATH = Path(__file__).resolve().parent / "static" / "ei-schema.json"
COLORS = {"1":"#F5B3B4","2":"#D2D4D4","3":"#EDD0E0","4":"#FFF0BD","5":"#AFD2EB","6":"#F5F09B","7":"#D2D4D4","8":"#F8C4A7","90":"#B8DDB4","95":"#E1E1E1"}
TITLES = {
 "1": "Toestemming een EOA/stoptonend sein te passeren",
 "2": "Toestemming tot doorrijden na TRIP",
 "3": "Verplichting om stil te blijven staan",
 "4": "Intrekking van een instructie",
 "5": "Verplichting om de snelheid te beperken",
 "6": "Verplichting om te rijden op zicht",
 "7": "Toestemming om te vertrekken",
 "8": "Toestemming om een defecte overweg te passeren",
 "90": "Controleren van de infrastructuur",
 "95": "Aanvullende opdracht",
}
FIXED = {"7": ("7.23",), "8": ("8.60", "8.80")}

def build_ei_pdf(payload):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=17*mm,
                            rightMargin=17*mm, topMargin=16*mm, bottomMargin=16*mm,
                            title="European Instruction - administratief archief")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("EI-body", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=4)
    small = ParagraphStyle("EI-small", parent=body, fontSize=8, leading=11)
    note = ParagraphStyle("EI-note", parent=body, textColor=colors.HexColor("#9b1c1c"))
    story = [Paragraph("European Instruction - archiefkopie", styles["Title"]),
             Paragraph("Ontwikkelversie: niet voor operationeel gebruik. Dit is een administratieve weergave, geen officieel EI-formulier.", note),
             Spacer(1, 5*mm)]
    meta = [
        ["Identificatie", str(payload.get("identification", ""))],
        ["Datum", str(payload.get("date", ""))],
        ["Tijd", str(payload.get("time", ""))],
        ["Afgehandeld", str(payload.get("completedAt", ""))],
        ["Registratie-ID", str(payload.get("recordId", ""))],
        ["Revisie", str(payload.get("revision", ""))],
    ]
    table = Table([[Paragraph(escape(str(k)), body), Paragraph(escape(str(v)), body)] for k,v in meta],
                  colWidths=[38*mm, 135*mm], hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                               ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.whitesmoke, colors.white]),
                               ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.extend([table, Spacer(1, 5*mm)])
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for num in payload["selected"]:
        num = str(num)
        if num not in schema:
            raise ValueError("Onbekende EI")
        definition = schema[num]
        header = Table([[Paragraph("<b>EI " + escape(num) + " - " + escape(definition["title"]) + "</b>", body)]],
                       colWidths=[173*mm])
        header.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor(COLORS[num])),
            ("BOX", (0,0), (-1,-1), .8, colors.HexColor("#444444")),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ]))
        story.extend([Spacer(1, 3*mm), header, Spacer(1, 3*mm)])
        checks = payload.get("checks", {}).get(num, {})
        if not isinstance(checks, dict):
            checks = {}
        for code, description in definition.get("checks", []):
            fixed = code in FIXED.get(num, ())
            symbol = '<font color="#e1252a">[X]</font>' if fixed else (
                '<font color="#228b39">[X]</font>' if checks.get(code) else '[ ]')
            indent = 12*mm if (num == "1" and code in ("1.20","x.25")) or (
                num == "7" and code in ("7.20","7.23")) else 0
            row = Table([[Paragraph(symbol, body),
                          Paragraph('<font color="#0879c7">' + escape(code) + '</font> ' + escape(description), body)]],
                        colWidths=[15*mm, 158*mm-indent], hAlign="LEFT")
            row.setStyle(TableStyle([
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 3),
                ("RIGHTPADDING", (0,0), (-1,-1), 4),
                ("TOPPADDING", (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ]))
            if indent:
                row.hAlign="RIGHT"
            story.append(row)
        details = payload.get("details", {}).get(num, {})
        if not isinstance(details, dict):
            details = {}
        for key, description, kind in definition.get("fields", []):
            value = str(details.get(key, ""))
            field = Table([[Paragraph(escape(description), small)],
                           [Paragraph(escape(value).replace("\\n", "<br/>") or "&nbsp;", body)]],
                          colWidths=[165*mm], hAlign="LEFT")
            field.setStyle(TableStyle([
                ("BOX", (0,1), (-1,1), 1, colors.HexColor("#e1252a")),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
                ("RIGHTPADDING", (0,0), (-1,-1), 8),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ]))
            story.extend([Spacer(1, 2*mm), field])
        story.append(Spacer(1, 5*mm))
    doc.build(story)
    return buffer.getvalue()
