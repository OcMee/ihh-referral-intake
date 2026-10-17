"""Play the outside world for a demo: send a FICTIONAL packet in by fax or email.

Nothing real is contacted. "fax" posts the PDF to the local server the way a cloud fax service's
webhook would; "email" writes a .eml file into intake/ the way a mailbox connector would.
Senders use the reserved .test domain and a 555 number, so they cannot belong to anyone.

  python src/simulate_intake.py fax   app/pdf/F02.pdf
  python src/simulate_intake.py email app/pdf/F03.pdf
"""

import os
import sys
import urllib.request
from email.message import EmailMessage
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def fax(pdf: Path, port: int) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/intake/fax", data=pdf.read_bytes(), method="POST",
                                 headers={"Content-Type": "application/pdf", "X-Fax-From": "714-555-0100 (fictional)"})
    try:
        with urllib.request.urlopen(req) as r:
            print("fax received:", r.read().decode())
    except urllib.error.HTTPError as e:
        print("fax refused:", e.read().decode())


def mail(pdf: Path) -> None:
    m = EmailMessage()
    m["From"] = "Case Manager (fictional) <case.manager@hospital.test>"
    m["To"] = os.environ.get("DESK_INTAKE_EMAIL", "office@ocmeed.com")
    m["Subject"] = f"Recuperative care referral (fictional demo packet {pdf.stem})"
    m.set_content("Please see the attached referral packet. Fictional demo email.")
    sub = "vnd.openxmlformats-officedocument.wordprocessingml.document" if pdf.suffix.lower() == ".docx" else "pdf"
    m.add_attachment(pdf.read_bytes(), maintype="application", subtype=sub, filename=pdf.name)
    dest = REPO / "intake" / f"email-{pdf.stem}.eml"
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(bytes(m))
    print(f"email saved to {dest}; the server picks it up within a few seconds")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("fax", "email"):
        sys.exit(__doc__)
    pdf = Path(sys.argv[2])
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
    fax(pdf, port) if sys.argv[1] == "fax" else mail(pdf)
