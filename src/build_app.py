"""Build the Referral Desk web app into a single self-contained HTML file.

  python src/build_app.py            public build: fictional cases only  -> app/index.html (committed)
  python src/build_app.py --real     the 11 IHH packets with their scans -> output/app/index.html (git ignored)

The real build holds de-identified packet text. Never commit, upload or publish it.
"""

import json
import sys
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
         fitlist=None, criteria=None) -> dict:
    keep = ("patient", "fit", "claude_fit", "verification", "key_facts", "rules", "conflicts", "questions_for_hospital")
    out = {k: d.get(k) for k in keep}
    out["questions"] = out.pop("questions_for_hospital") or []
    out.update(id=d["packet_id"], pages=len(pages["pages"]), received_min=ARRIVED[i % len(ARRIVED)], img=img, ihh=ihh, pdf=pdf, readable=readable, docx=docx, fitlist=fitlist, criteria=criteria,
               documents=[{**x, "name": checklist.get(x["doc_id"], x["doc_id"])} for x in d.get("documents", [])],
               page_list=[{"page": p["page"], "title": p["title"], "doc_type": p["doc_type"], "text": p["text"]} for p in pages["pages"]])
    return out


def html(data: dict, artifact: bool) -> str:
    shell = (SRC / "shell.html").read_text()
    data = {**data, "meta": {**data["meta"], "artifact": artifact}}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = (shell.replace("<!--STYLE-->", f"<style>{(SRC / 'app.css').read_text()}</style>")
                 .replace("<!--DATA-->", f"<script>window.APP={blob};</script>")
                 .replace("<!--SCRIPT-->", f"<script>{(SRC / 'app.js').read_text()}</script>"))
    if artifact:
        return page
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + page + "</html>")


def public(checklist: dict) -> list:
    import make_demo
    import shutil
    rules = score.load_rules()
    out_dir = REPO / "app/pdf"
    shutil.copy(REPO / CRIT_SRC, out_dir / "ihh-admission-criteria.pdf")
    items = [(c, {"pages": p}) for c, p in ((make_demo.c1, make_demo.p1), (make_demo.c2, make_demo.p2), (make_demo.c3, make_demo.p3))]
    items += [(json.loads(f.read_text()), json.loads(f.with_name(f"{f.stem}.pages.json").read_text()))
              for f in sorted((REPO / "demo/fictional").glob("F0?/F0?.json"))]
    packets = []
    for i, (check, pages) in enumerate(items):
        d = score.score_packet(check, pages, rules)
        pid = d["packet_id"]
        checklist_pdf.make(d, checklist, out_dir / f"{pid}.checklist.pdf", fictional=True)
        packets.append(pack(d, pages, checklist, i, pdf=f"pdf/{pid}.pdf", readable=f"pdf/{pid}.readable.pdf",
                            docx=f"pdf/{pid}.docx", fitlist=f"pdf/{pid}.checklist.pdf", criteria="pdf/ihh-admission-criteria.pdf"))
    return packets


def real(checklist: dict) -> list:
    truth = {p["packet_id"]: p["decision"] for p in json.loads(DECISIONS.read_text())["packets"]}
    packets = []
    for i, f in enumerate(sorted((REPO / "output").glob("R??/R??.scored.json"))):
        pid = f.parent.name
        pages = json.loads((f.parent / f"{pid}.pages.json").read_text())
        d = json.loads(f.read_text())
        checklist_pdf.make(d, checklist, f.parent / f"{pid}.checklist.pdf", fictional=False)
        packets.append(pack(d, pages, checklist, i, img=f"../{pid}/pages/p-{{nn}}.png", ihh=truth.get(pid),
                            fitlist=f"../{pid}/{pid}.checklist.pdf", criteria=f"../../{CRIT_SRC}",
                            pdf=f"../../challenges/1-referral-intake/packets/{pid}.pdf",
                            readable=f"../{pid}/{pid}.readable.pdf", docx=f"../{pid}/{pid}.docx"))
    return packets


def main(argv: list) -> None:
    checklist = {x["id"]: x["text"] for x in json.loads(CRITERIA.read_text())["referral_checklist"]["items"]}
    if "--real" in argv:
        data = {"meta": {"real": True, "banner": "De-identified IHH packets. Local only: do not share, upload or publish this page.",
                         "note": "IHH decisions are hidden unless you tick the box."}, "packets": real(checklist)}
        dest = REPO / "output/app/index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html(data, artifact=False), encoding="utf-8")
    else:
        data = {"meta": {"real": False, "banner": "Fictional demo cases. Every patient here is invented; no real patient data is on this page.",
                         "note": "Fictional packets have transcripts but no scans."}, "packets": public(checklist)}
        (REPO / "app/index.html").write_text(html(data, artifact=False), encoding="utf-8")
        (REPO / "app/artifact.html").write_text(html(data, artifact=True), encoding="utf-8")
        dest = REPO / "app/index.html"
    print(f"{len(data['packets'])} packets -> {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
