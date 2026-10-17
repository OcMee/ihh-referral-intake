"""Print the FICTIONAL demo packets as fax-style PDFs so the public app can embed an "original".

Every page carries a FICTIONAL banner. Real packets are never touched: their originals are the
scans in challenges/1-referral-intake/packets/ (git ignored).

  python src/fake_pdf.py            -> app/pdf/D01.pdf ... app/pdf/F09.pdf
"""

import json
import sys
import textwrap
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "demo"))
sys.path.insert(0, str(REPO / "src"))
OUT = REPO / "app" / "pdf"


def packets():
    import make_demo
    for c, p in ((make_demo.c1, make_demo.p1), (make_demo.c2, make_demo.p2), (make_demo.c3, make_demo.p3)):
        yield c["packet_id"], p
    for f in sorted((REPO / "demo/fictional").glob("F[0-9][0-9]/F[0-9][0-9].pages.json")):
        yield f.stem.split(".")[0], json.loads(f.read_text())["pages"]


def render(pid: str, pages: list, dest: Path) -> None:
    W, H = letter
    c = canvas.Canvas(str(dest), pagesize=letter)
    c.setTitle(f"{pid} fictional referral packet")
    n = len(pages)
    for p in pages:
        # fax header strip
        c.setFillColor(HexColor("#e9e7e2"))
        c.rect(0, H - 34, W, 34, stroke=0, fill=1)
        c.setFillColor(HexColor("#333333"))
        c.setFont("Courier-Bold", 9)
        c.drawString(36, H - 21, f"FAX  {pid}  FICTIONAL DEMO RECORD - NOT A REAL PATIENT")
        c.drawRightString(W - 36, H - 21, f"PAGE {p['page']:02d}/{n:02d}")
        c.setFont("Helvetica-Bold", 13)
        c.drawString(54, H - 66, p["title"][:80])
        c.setStrokeColor(HexColor("#999999"))
        c.line(54, H - 74, W - 54, H - 74)
        y = H - 96
        for raw in p["text"].split("\n"):
            bold = raw.startswith("## ")
            line = raw[3:] if bold else raw
            for part in (textwrap.wrap(line, 88) or [""]):
                if y < 60:
                    break
                c.setFont("Courier-Bold" if bold else "Courier", 9.5)
                c.drawString(54, y, part)
                y -= 13.5
            if bold:
                y -= 2
        c.setFont("Courier", 8)
        c.setFillColor(HexColor("#777777"))
        c.drawString(54, 30, "Invented for the Claude Impact Lab demo. Names, facilities and numbers are fictional.")
        c.showPage()
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pid, pages in packets():
        render(pid, pages, OUT / f"{pid}.pdf")
        print(f"{pid}: {len(pages)} pages -> app/pdf/{pid}.pdf")
    readable()



def readable() -> None:
    """Readable copies of the fictional packets: each fake page beside its transcript (same layout as clean.py)."""
    import pymupdf
    import clean
    for pid, pages in packets():
        tmp = OUT / f".{pid}_pages"
        tmp.mkdir(exist_ok=True)
        imgs = []
        with pymupdf.open(OUT / f"{pid}.pdf") as doc:
            for i, pg in enumerate(doc, start=1):
                img = tmp / f"p-{i:02d}.png"
                pg.get_pixmap(dpi=90).save(img)
                imgs.append(img)
        clean.build({"packet_id": pid, "pages": pages}, imgs, OUT / f"{pid}.readable.pdf", f"{pid}.pdf (fictional)")
        for img in imgs:
            img.unlink()
        tmp.rmdir()
        print(f"{pid}: readable -> app/pdf/{pid}.readable.pdf")


if __name__ == "__main__":
    main()
