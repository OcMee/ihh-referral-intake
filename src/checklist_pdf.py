"""One printable fit checklist per referral: every applicable IHH rule with status, finding and page.

Called by build_app.py for each scored packet. Real packets' checklists go to output/ (git ignored);
fictional ones to app/pdf/.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK, MUTE, ORANGE = colors.HexColor("#1a1a1a"), colors.HexColor("#5c5f66"), colors.HexColor("#ff8710")
STATUS = {"met": ("Met", "#17734a", "#e4f2ea"), "not_met": ("Not met", "#b3261e", "#fbe8e6"),
          "unknown": ("Unknown", "#9a5b00", "#fcefd9"), "cant_tell": ("Can't tell", "#5f6670", "#ebecee")}
ORDER = ["General", "ADLs", "Mobility", "Mental Health", "Cognition", "Other Factors", "End of life care",
         "Infection Control", "Infection", "Diabetes", "Respiratory Illness", "Cardiac"]

S = {
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTE),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceBefore=8, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=INK),
    "id": ParagraphStyle("id", fontName="Courier-Bold", fontSize=7.5, leading=10, textColor=INK),
    "foot": ParagraphStyle("foot", fontName="Helvetica-Oblique", fontSize=7.5, leading=9.5, textColor=MUTE),
}


def e(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make(d: dict, checklist: dict, dest: Path, fictional: bool) -> None:
    fit, cf = d["fit"], d.get("claude_fit", {})
    doc = SimpleDocTemplate(str(dest), pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title=f"{d['packet_id']} fit checklist", author="OCMEE Referral Solution", invariant=True)

    def frame(c, _doc):
        c.setFillColor(INK); c.rect(0, letter[1] - 22, letter[0], 22, stroke=0, fill=1)
        c.setFillColor(ORANGE); c.rect(0, letter[1] - 25, letter[0], 3, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 9); c.setFillColor(ORANGE); c.drawString(36, letter[1] - 15, "OCMEE REFERRAL SOLUTION")
        c.setFillColor(colors.white); c.setFont("Helvetica", 8)
        c.drawString(178, letter[1] - 15, f"fit checklist  ·  {d['packet_id']}")
        c.drawRightString(letter[0] - 36, letter[1] - 15,
                          "FICTIONAL DEMO CASE" if fictional else "De-identified packet data: do not share")
        c.setFillColor(MUTE); c.setFont("Helvetica", 7)
        c.drawRightString(letter[0] - 36, 20, f"page {_doc.page}")

    story = [Spacer(1, 6), Paragraph(f"{e(d['packet_id'])} · {e(d.get('patient', {}).get('summary'))}", S["h1"]),
             Paragraph(f"Fit score <b>{fit['score']}/100</b> · {e(fit['label'])}"
                       f"{' · blockers: ' + e(', '.join(fit['blockers'])) if fit['blockers'] else ' · no verified blockers'}"
                       f" · Claude's read {e(cf.get('score'))}/100 ({e(str(cf.get('recommendation', '')).replace('_', ' '))})"
                       f" · {d['verification']['verified']}/{d['verification']['quotes']} quotes verified on their pages", S["meta"])]

    rules = [r for r in d["rules"] if r["status"] != "not_applicable" and not r.get("superseded_by")]
    secs = {}
    for r in rules:
        secs.setdefault(r["section"], []).append(r)
    rank = {"not_met": 0, "unknown": 1, "cant_tell": 2, "met": 3}
    rows = [[Paragraph("<b>Rule</b>", S["cell"]), Paragraph("<b>Requirement</b>", S["cell"]),
             Paragraph("<b>Status</b>", S["cell"]), Paragraph("<b>Finding</b>", S["cell"]), Paragraph("<b>Pages</b>", S["cell"])]]
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6d3cc")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efede8"))]
    for sec in [s for s in ORDER if s in secs] + sorted(s for s in secs if s not in ORDER):
        rows.append([Paragraph(f"<b>{e(sec)}</b>", S["cell"]), "", "", "", ""])
        style += [("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1)), ("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor("#f7f6f2"))]
        for r in sorted(secs[sec], key=lambda r: rank.get(r["status"], 9)):
            label, fg, bg = STATUS.get(r["status"], (r["status"], "#333333", "#ffffff"))
            pages = ", ".join(f"p{x['page']}{'✓' if x.get('verified') else ' (check)'}" for x in r.get("evidence", []))
            rows.append([Paragraph(e(r["rule_id"]), S["id"]), Paragraph(e(r["short"]), S["cell"]),
                         Paragraph(f'<font color="{fg}"><b>{label}</b></font>', S["cell"]),
                         Paragraph(e(r.get("finding")), S["cell"]), Paragraph(e(pages) or "–", S["cell"])])
            style.append(("BACKGROUND", (2, len(rows) - 1), (2, len(rows) - 1), colors.HexColor(bg)))
    t = Table(rows, colWidths=[0.75 * inch, 1.6 * inch, 0.7 * inch, 3.65 * inch, 0.8 * inch], repeatRows=1)
    t.setStyle(TableStyle(style))
    story += [Paragraph(f"IHH admission criteria ({len(rules)} applicable, "
                        f"{len(d['rules']) - len(rules)} not applicable or superseded)", S["h2"]), t]

    docs = [[Paragraph("<b>Required document</b>", S["cell"]), Paragraph("<b>In packet</b>", S["cell"]), Paragraph("<b>Pages</b>", S["cell"])]]
    for x in d.get("documents", []):
        docs.append([Paragraph(e(f"{x['doc_id']} {checklist.get(x['doc_id'], '')}"), S["cell"]),
                     Paragraph({"yes": "Yes", "no": '<font color="#b3261e"><b>Missing</b></font>'}.get(x["present"], "Unknown"), S["cell"]),
                     Paragraph(", ".join(f"p{p}" for p in x.get("pages", [])) or "–", S["cell"])])
    dt = Table(docs, colWidths=[4.6 * inch, 1.1 * inch, 1.8 * inch], repeatRows=1)
    dt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6d3cc")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efede8")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Paragraph("IHH document checklist", S["h2"]), dt]

    qs = d.get("questions_for_hospital") or d.get("questions") or []
    if qs:
        story.append(Paragraph("Questions for the hospital", S["h2"]))
        story += [Paragraph(f"{i + 1}. {e(q)}", S["cell"]) for i, q in enumerate(qs)]
    story += [Spacer(1, 8), Paragraph(
        "AI-prepared checklist. The coordinator decides. ✓ = the quoted text was found on that page of the transcript; "
        "(check) = not found, read the page. Fit score weights were hand-tuned on IHH's 11 past decisions (in-sample).", S["foot"])]
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
