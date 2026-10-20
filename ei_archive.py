"""Printable archival summary of a completed European Instruction.

This is an administrative record, NOT a replacement for the official railway form.
"""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

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
    for num in payload["selected"]:
        num = str(num)
        story.append(Paragraph("EI " + escape(num) + " - " + escape(TITLES[num]), styles["Heading2"]))
        checks = payload.get("checks", {}).get(num, {})
        if not isinstance(checks, dict): checks = {}
        for code, checked in sorted(checks.items()):
            story.append(Paragraph(escape(str(code)) + ": " + ("aangekruist" if checked else "niet aangekruist"), body))
        for code in FIXED.get(num, ()):
            story.append(Paragraph(escape(code) + ": voorgedrukt verplicht rood kruis", body))
        details = payload.get("details", {}).get(num, {})
        if isinstance(details, dict):
            for key, value in details.items():
                story.append(Paragraph("<b>" + escape(str(key)) + "</b>: " + escape(str(value)).replace("\n", "<br/>"), body))
        story.append(Spacer(1, 3*mm))
    doc.build(story)
    return buffer.getvalue()
