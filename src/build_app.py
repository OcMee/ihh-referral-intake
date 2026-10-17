"""Build the Referral Desk web app into a single self-contained HTML file.

  python src/build_app.py            public build: fictional cases only  -> app/index.html (committed)
  python src/build_app.py --real     the 11 IHH packets with their scans -> output/app/index.html (git ignored)

The real build holds de-identified packet text. Never commit, upload or publish it.
"""

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "demo"))
import score  # noqa: E402
import checklist_pdf  # noqa: E402

SRC = REPO / "app" / "src"
CRITERIA = REPO / "challenges/1-referral-intake/criteria/admission-criteria.json"
DECISIONS = REPO / "challenges/1-referral-intake/eval/decisions.json"
# simulated arrival: minutes ago, so the inbox shows a realistic mix of fresh, close and overdue referrals
ARRIVED = [96, 12, 131, 44, 23, 71, 58, 7, 109, 35, 84, 18, 63, 102, 29, 50, 3, 77, 40, 125]


CRIT_SRC = "challenges/1-referral-intake/criteria/source/ihh-recuperative-care-admission-criteria.pdf"


def pack(d: dict, pages: dict, checklist: dict, i: int, img=None, ihh=None, pdf=None, readable=None, docx=None,
         fitlist=None, criteria=None, seed=None) -> dict:
    keep = ("patient", "fit", "claude_fit", "verification", "key_facts", "rules", "conflicts", "questions_for_hospital")
    out = {k: d.get(k) for k in keep}
    out["questions"] = out.pop("questions_for_hospital") or []
    out.update(id=d["packet_id"], uploaded=None, seed=seed, pages=len(pages["pages"]), received_min=ARRIVED[i % len(ARRIVED)], img=img, ihh=ihh, pdf=pdf, readable=readable, docx=docx, fitlist=fitlist, criteria=criteria,
               documents=[{**x, "name": checklist.get(x["doc_id"], x["doc_id"])} for x in d.get("documents", [])],
               page_list=[{"page": p["page"], "title": p["title"], "doc_type": p["doc_type"], "text": p["text"]} for p in pages["pages"]])
    return out


def small(path: Path) -> bytes:
    """Smaller page image for the artifact, which has a 16 MB limit; the website keeps the full-size originals."""
    import io
    from PIL import Image
    im = Image.open(path).convert("L")
    im.thumbnail((560, 760))
    b = io.BytesIO(); im.save(b, "JPEG", quality=55, optimize=True)
    return b.getvalue()


def html(data: dict, artifact: bool) -> str:
    shell = (SRC / "shell.html").read_text()
    # demo history is anchored to the build time, so seeded entries never move or land after real decisions
    data = {**data, "meta": {**data["meta"], "artifact": artifact, "built": int(time.time() * 1000)}}
    if artifact and not data["meta"].get("real"):  # the artifact cannot load files: inline the fictional page images
        import base64
        pk = []
        for p in data["packets"]:
            imgs = [f"data:image/jpeg;base64,{base64.b64encode(small(REPO / 'app' / p['img'].replace('{nn}', f'{n:02d}'))).decode()}"
                    for n in range(1, p["pages"] + 1)] if p.get("img") else None
            pk.append({**p, "imgs": imgs})
        data = {**data, "packets": pk}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = (shell.replace("<!--STYLE-->", f"<style>{(SRC / 'app.css').read_text()}</style>")
                 .replace("<!--DATA-->", f"<script>window.APP={blob};</script>")
                 .replace("<!--SCRIPT-->", f"<script>{(SRC / 'app.js').read_text()}</script>"))
    if artifact:
        return page
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + page + "</html>")


def page_images(pdf: Path, dest: Path) -> int:
    """Fictional originals as page images, so the original shows inside the app (PDF frames are blocked in some viewers)."""
    import pymupdf
    dest.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc:
        for i, pg in enumerate(doc, start=1):
            pg.get_pixmap(dpi=80).save(dest / f"p-{i:02d}.jpg", jpg_quality=70)
        return len(doc)


def public(checklist: dict, pre: str = "") -> list:
    """pre: path prefix to app/ (the local build lives in output/app/, so it uses ../../app/)."""
    import make_demo
    import shutil
    rules = score.load_rules()
    out_dir = REPO / "app/pdf"
    shutil.copy(REPO / CRIT_SRC, out_dir / "ihh-admission-criteria.pdf")
    items = [(c, {"pages": p}) for c, p in ((make_demo.c1, make_demo.p1), (make_demo.c2, make_demo.p2), (make_demo.c3, make_demo.p3))]
    items += [(json.loads(f.read_text()), json.loads(f.with_name(f"{f.stem}.pages.json").read_text()))
              for f in sorted((REPO / "demo/fictional").glob("F[0-9][0-9]/F[0-9][0-9].json")) if not 10 <= int(f.stem[1:]) <= 27]  # to review
    # already reviewed earlier today: F10-F20 with a seeded decision record (labeled as demo history in the app)
    hist = [(json.loads(f.read_text()), json.loads(f.with_name(f"{f.stem}.pages.json").read_text()))
            for f in sorted((REPO / "demo/fictional").glob("F[12][0-9]/F[12][0-9].json")) if int(f.stem[1:]) <= 27]
    intended = {a["packet_id"]: a["intended"] for a in json.loads((REPO / "demo/fictional/answers.json").read_text())}
    KIND = {"fit": "approve", "needs_info": "info", "not_fit": "deny"}
    BY = "Dr Cornel Manole (Referral coordinator)"
    packets = []
    for j, (check, pages) in enumerate(hist):
        d = score.score_packet(check, pages, rules)
        pid = d["packet_id"]
        received = 900 - j * 38                      # minutes before the build; always in the past
        took = [38, 72, 55, 104, 47, 131, 66, 29, 88, 59, 93][j % 11]   # minutes to first decision
        seed = [{"decision": KIND[intended[pid]], "min": received - took, "by": BY}]
        if pid in ("F10", "F16", "F19", "F24"):  # accepted earlier and already arrived at IHH
            seed.append({"decision": "arrived", "min": received - took - 150, "by": BY})
        if pid == "F14":  # example revision: the hospital sent the missing swab results
            seed.append({"decision": "approve", "min": received - took - 95, "by": BY,
                         "reason": "Demo: hospital faxed negative MRSA and COVID swab results (INF-1, INF-2)."})
        checklist_pdf.make(d, checklist, out_dir / f"{pid}.checklist.pdf", fictional=True)
        page_images(out_dir / f"{pid}.pdf", out_dir / "pages" / pid)
        p = pack(d, pages, checklist, j, pdf=f"{pre}pdf/{pid}.pdf", img=f"{pre}pdf/pages/{pid}/p-{{nn}}.jpg", readable=f"{pre}pdf/{pid}.readable.pdf",
                 docx=f"{pre}pdf/{pid}.docx", fitlist=f"{pre}pdf/{pid}.checklist.pdf", criteria=f"{pre}pdf/ihh-admission-criteria.pdf", seed=seed)
        p["received_min"] = received
        packets.append(p)
    for i, (check, pages) in enumerate(items):
        d = score.score_packet(check, pages, rules)
        pid = d["packet_id"]
        checklist_pdf.make(d, checklist, out_dir / f"{pid}.checklist.pdf", fictional=True)
        page_images(out_dir / f"{pid}.pdf", out_dir / "pages" / pid)
        packets.append(pack(d, pages, checklist, i, pdf=f"{pre}pdf/{pid}.pdf", img=f"{pre}pdf/pages/{pid}/p-{{nn}}.jpg", readable=f"{pre}pdf/{pid}.readable.pdf",
                            docx=f"{pre}pdf/{pid}.docx", fitlist=f"{pre}pdf/{pid}.checklist.pdf", criteria=f"{pre}pdf/ihh-admission-criteria.pdf"))
    return packets


def real(checklist: dict) -> list:
    truth = {p["packet_id"]: p["decision"] for p in json.loads(DECISIONS.read_text())["packets"]}
    packets = []
    # R01-R11 are IHH's packets; U01.. are PDFs dropped into the local server (src/desk_server.py)
    found = [f for f in sorted((REPO / "output").glob("*/*.scored.json"))
             if re.fullmatch(r"[A-Z]\d\d", f.parent.name) and f.stem == f"{f.parent.name}.scored"]
    for i, f in enumerate(found):
        pid, here = f.parent.name, f.parent
        pages = json.loads((here / f"{pid}.pages.json").read_text())
        d = json.loads(f.read_text())
        checklist_pdf.make(d, checklist, here / f"{pid}.checklist.pdf", fictional=False)
        uploaded = (here / f"{pid}.pdf").exists()
        p = pack(d, pages, checklist, i, img=f"../{pid}/pages/p-{{nn}}.png", ihh=truth.get(pid),
                 fitlist=f"../{pid}/{pid}.checklist.pdf", criteria=f"../../{CRIT_SRC}",
                 pdf=f"../{pid}/{pid}.pdf" if uploaded else f"../../challenges/1-referral-intake/packets/{pid}.pdf",
                 readable=f"../{pid}/{pid}.readable.pdf",
                 docx=f"../{pid}/{pid}.docx" if (here / f"{pid}.docx").exists() else None)
        if (here / "received.json").exists():  # real arrival time for uploads
            r = json.loads((here / "received.json").read_text())
            p["received_min"] = round((time.time() - r["at"]) / 60)
            p["uploaded"] = {k: v for k, v in r.items() if k not in ("at", "sha256")}  # source, from, subject, hospital...
        packets.append(p)
    return packets


def main(argv: list) -> None:
    checklist = {x["id"]: x["text"] for x in json.loads(CRITERIA.read_text())["referral_checklist"]["items"]}
    if "--real" in argv:
        local = real(checklist)
        if any(x["id"].startswith("R") for x in local):  # the 11 IHH packets are on this computer
            data = {"meta": {"real": True, "local": True, "banner": "De-identified IHH packets. Local only: do not share, upload or publish this page.",
                             "note": "IHH decisions are hidden unless you tick the box."}, "packets": local}
        else:  # a coordinator's laptop without the IHH packets: the fictional desk plus anything dropped in
            data = {"meta": {"real": False, "local": True, "banner": "", "note": "All patients in this demo are invented."},
                    "packets": public(checklist, pre="../../app/") + local}
        dest = REPO / "output/app/index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html(data, artifact=False), encoding="utf-8")
    else:
        data = {"meta": {"real": False, "banner": "",
                         "note": "All patients in this demo are invented."}, "packets": public(checklist)}
        # website drag-and-check: recognize the demo files by content (sha256 of each PDF and Word copy)
        import hashlib
        data["meta"]["known"] = {hashlib.sha256(f.read_bytes()).hexdigest(): f.stem for f in sorted((REPO / "app/pdf").glob("*.*"))
                                 if re.fullmatch(r"[DF]\d\d", f.stem) and f.suffix in (".pdf", ".docx")}
        (REPO / "app/index.html").write_text(html(data, artifact=False), encoding="utf-8")
        (REPO / "app/artifact.html").write_text(html(data, artifact=True), encoding="utf-8")
        dest = REPO / "app/index.html"
    print(f"{len(data['packets'])} packets -> {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
