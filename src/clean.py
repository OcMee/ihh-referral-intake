"""Turn a scanned referral packet into an easy-to-read PDF.

Stages:
  1. fix         ocrmypdf: rotate pages upright, deskew, add a text layer   (free, local)
  2. transcribe  Claude reads each page image and returns a clean transcript (--transcribe, uses API)
  3. build       readable PDF: summary + page map, then each original page next to its transcript

Output goes to output/<packet>/ which git ignores. Never commit it: it is packet data.

  python src/clean.py challenges/1-referral-intake/packets/R05.pdf
  python src/clean.py challenges/1-referral-intake/packets/R05.pdf --transcribe
"""

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

import pymupdf as fitz
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, Image, KeepInFrame,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

REPO = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO / "output"
MODEL = "claude-opus-5-5"

DOC_TYPES = Literal[
    "fax_cover", "referral_form", "calaim_auth", "face_sheet", "h_and_p", "progress_note",
    "nursing_note", "pt_eval", "ot_eval", "labs", "imaging", "ecg", "med_list", "med_record",
    "social_work", "psych_consult", "wound_note", "vitals", "orders", "other", "blank",
]


class PageTranscript(BaseModel):
    page: int
    doc_type: DOC_TYPES
    title: str
    orientation: Literal["normal", "sideways", "upside_down"]
    legibility: Literal["good", "fair", "poor"]
    text: str
    notes: str


TRANSCRIBE_PROMPT = """This is page {page} of a faxed hospital referral packet. It has been \
de-identified: black boxes are redactions.

Transcribe the page so a referral coordinator can read it fast.
- Copy clinical text exactly. Do not fix, summarize or interpret it.
- Write [REDACTED] where a black box hides text. Never guess what is under it.
- Checkboxes: write the label then [X] or [ ]. If a mark is ambiguous, write [?] and say why in notes.
- Handwriting you cannot read: write [illegible].
- Blank template sections with nothing filled in: one line saying so, do not copy the boilerplate.
- Use short lines. Start a section heading with "## ". Start a bullet with "- ".
- title: a few words naming the document (e.g. "History and Physical, page 2 of 3").
- notes: anything a reviewer should check by hand on the original. Empty if nothing.
If you see a name, date, phone or ID number that is NOT redacted, say so in notes."""


def fix(src: Path, out: Path) -> Path:
    fixed = out / f"{src.stem}.fixed.pdf"
    subprocess.run(
        ["ocrmypdf", "--rotate-pages", "--deskew", "--optimize", "1", "--quiet",
         str(src), str(fixed)],
        check=True,
    )
    return fixed


def render(pdf: Path, out: Path, dpi: int = 110) -> list[Path]:
    img_dir = out / "pages"
    img_dir.mkdir(exist_ok=True)
    paths = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            p = img_dir / f"p-{i:02d}.png"
            page.get_pixmap(dpi=dpi).save(p)
            paths.append(p)
    return paths


def transcribe(images: list[Path], packet_id: str, pages_json: Path) -> None:
    import anthropic

    client = anthropic.Anthropic()
    results = []
    for i, img in enumerate(images, start=1):
        data = base64.standard_b64encode(img.read_bytes()).decode()
        resp = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png", "data": data}},
                    {"type": "text", "text": TRANSCRIBE_PROMPT.format(page=i)},
                ],
            }],
            output_format=PageTranscript,
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            print(f"  page {i}: no transcript ({resp.stop_reason}), marked for hand review")
            t = PageTranscript(page=i, doc_type="other", title="Not transcribed",
                               orientation="normal", legibility="poor", text="",
                               notes=f"Model returned {resp.stop_reason}. Read the original.")
        else:
            t = resp.parsed_output
            t.page = i
        results.append(t.model_dump())
        print(f"  page {i}: {t.doc_type} ({t.legibility})")
    pages_json.write_text(json.dumps({"packet_id": packet_id, "pages": results}, indent=2))


# ---------- build ----------

STYLES = {
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14,
                         spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#1f3b57")),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=13, leading=16,
                            spaceAfter=4),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8, leading=10,
                           textColor=colors.HexColor("#666666"), spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=12.5),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=12.5,
                             leftIndent=10, bulletIndent=0),
    "note": ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
                           textColor=colors.HexColor("#8a4b00"), spaceBefore=6),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5),
}


def esc(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (s.replace("[REDACTED]", '<font color="#999999">[REDACTED]</font>')
             .replace("[X]", "<b>[X]</b>")
             .replace("[?]", '<font color="#c0392b"><b>[?]</b></font>'))


def text_flowables(text: str) -> list:
    out = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            out.append(Spacer(1, 4))
        elif line.startswith("## "):
            out.append(Paragraph(esc(line[3:]), STYLES["h2"]))
        elif line.startswith("- "):
            out.append(Paragraph(esc(line[2:]), STYLES["bullet"], bulletText="•"))
        else:
            out.append(Paragraph(esc(line), STYLES["body"]))
    return out


def build(data: dict, images: list[Path], out_pdf: Path, source_name: str) -> None:
    W, H = landscape(letter)
    m = 0.4 * inch
    img_w = 4.9 * inch
    full = Frame(m, m, W - 2 * m, H - 2 * m, id="full")
    left = Frame(m, m, img_w, H - 2 * m, id="left", leftPadding=0, rightPadding=0)
    right = Frame(m + img_w + 0.25 * inch, m, W - img_w - 2 * m - 0.25 * inch, H - 2 * m,
                  id="right")

    def footer(c, doc):
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#888888"))
        c.drawString(m, 0.2 * inch, f"{data['packet_id']}  readable copy  |  de-identified "
                     "packet data, do not commit or share  |  transcripts are AI-made, "
                     "check against the original on the left")
        c.drawRightString(W - m, 0.2 * inch, f"sheet {doc.page}")

    doc = BaseDocTemplate(str(out_pdf), pagesize=(W, H),
                          title=f"{data['packet_id']} readable", author="ihh-referral-intake")
    doc.addPageTemplates([
        PageTemplate(id="summary", frames=[full], onPage=footer),
        PageTemplate(id="spread", frames=[left, right], onPage=footer),
    ])

    pages = data["pages"]
    story = [Paragraph(f"Referral packet {data['packet_id']}: readable copy", STYLES["h1"]),
             Paragraph(f"Source: {source_name}, {len(pages)} pages. Left side of each sheet is "
                       "the original page, right side is a typed transcript. Black boxes are "
                       "privacy redactions, not missing information.", STYLES["meta"])]

    if data.get("highlights"):
        story.append(Paragraph("What stands out (with page numbers)", STYLES["h2"]))
        for h in data["highlights"]:
            story.append(Paragraph(esc(h), STYLES["bullet"], bulletText="•"))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Page map", STYLES["h2"]))
    rows = [["Page", "Document", "Type", "Legibility", "Check by hand"]]
    for p in pages:
        rows.append([str(p["page"]), Paragraph(esc(p["title"]), STYLES["cell"]), p["doc_type"],
                     p["legibility"], Paragraph(esc(p["notes"]) or "", STYLES["cell"])])
    t = Table(rows, colWidths=[0.5 * inch, 3.0 * inch, 1.2 * inch, 0.8 * inch, 4.4 * inch],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef4")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d0d8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [t, NextPageTemplate("spread"), PageBreak()]

    for p, img in zip(pages, images):
        im = Image(str(img))
        scale = min(img_w / im.imageWidth, (H - 2 * m) / im.imageHeight)
        im.drawWidth, im.drawHeight = im.imageWidth * scale, im.imageHeight * scale
        right_side = [Paragraph(f"Page {p['page']}: {esc(p['title'])}", STYLES["title"]),
                      Paragraph(f"{p['doc_type']}  |  orientation {p['orientation']}  |  "
                                f"legibility {p['legibility']}", STYLES["meta"])]
        right_side += text_flowables(p["text"])
        if p["notes"]:
            right_side.append(Paragraph("Check by hand: " + esc(p["notes"]), STYLES["note"]))
        story += [im, FrameBreak(),
                  KeepInFrame(right.width, right.height, right_side, mode="shrink"),
                  PageBreak()]

    doc.build(story)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--transcribe", action="store_true", help="call Claude to transcribe pages")
    ap.add_argument("--pages-json", type=Path, help="use an existing transcript JSON")
    args = ap.parse_args()

    src = args.pdf.resolve()
    packet_id = src.stem.split("-")[-1]
    out = OUT_ROOT / packet_id
    out.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] fixing pages -> {out}")
    fixed = fix(src, out)
    images = render(fixed, out)

    pages_json = args.pages_json or out / f"{packet_id}.pages.json"
    if args.transcribe:
        print(f"[2/3] transcribing {len(images)} pages with {MODEL}")
        transcribe(images, packet_id, pages_json)
    if not pages_json.exists():
        print(f"[2/3] skipped. Fixed PDF: {fixed}\n      Run with --transcribe for the readable copy.")
        return

    print("[3/3] building readable PDF")
    data = json.loads(pages_json.read_text())
    if len(data["pages"]) != len(images):
        sys.exit(f"transcript has {len(data['pages'])} pages, packet has {len(images)}")
    readable = out / f"{packet_id}.readable.pdf"
    build(data, images, readable, src.name)
    print(f"done: {readable}")


if __name__ == "__main__":
    main()
