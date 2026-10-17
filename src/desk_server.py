"""Run Referral Desk on this computer, with five ways for a referral to arrive.

  export ANTHROPIC_API_KEY=...        (never put it in the repo)
  python src/desk_server.py           then open http://127.0.0.1:8000

A dropped PDF is saved to output/U01/U01.pdf (git ignored) and goes through the same pipeline as the
11 IHH packets: straighten pages, transcribe with Claude, criteria check with Claude (src/check.py),
verify every quote and score (src/score.py), then the inbox rebuilds and shows it.

The server listens on 127.0.0.1 only, so nothing is reachable from other machines. Uploaded packets
are patient data: do not run this on a shared or public host.

Intake channels (all feed the same pipeline and inbox; every card shows its source):
  Upload   drag and drop one or more PDFs on the inbox            POST /api/upload
  Fax      a cloud fax service would POST each fax PDF here      POST /api/intake/fax
           (prototype: src/simulate_intake.py fax plays that service; nothing real is connected)
  Folder   any PDF saved in intake/ is picked up within seconds  (point fax software's save folder here)
  Email    any .eml saved in intake/ is read: sender, subject, PDF attachments
           (a mailbox connector would save mail here; src/simulate_intake.py email makes a fictional one)
  Portal   /portal: a hospital sends files and ticks IHH's DOC-1..10 checklist first
The same file arriving twice (same bytes) is refused and named as a duplicate.

  python src/desk_server.py --dry-run   test the plumbing without the API: accepts only the
                                        fictional app/pdf/F0X.pdf files (recognized by content) and
                                        reuses their prepared transcript and check.
"""

import argparse
import base64
import contextlib
import email
import email.policy
import hashlib
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "demo"))
OUT = REPO / "output"
INTAKE = REPO / "intake"  # watched folder (git ignored): PDFs and .eml emails
# address hospitals send referrals to; a mailbox connector would save its mail into intake/ (not connected here)
INTAKE_EMAIL = os.environ.get("DESK_INTAKE_EMAIL", "office@ocmeed.com")
MAX_BYTES = 60 * 1024 * 1024
STEPS = ["fix", "transcribe", "check", "score", "build"]

JOBS: dict = {}
LOCK = threading.Lock()  # one packet at a time: the API calls are the slow part
DRY = False
SOURCES = {"upload": "Upload", "fax": "Fax", "folder": "Folder", "email": "Email", "portal": "Portal"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fictional(body: bytes):
    """Dry run: which fictional packet is this, by content (works whatever the channel renamed it to)."""
    h = sha(body)
    return next((f.stem for f in sorted((REPO / "app/pdf").glob("F[0-9][0-9].pdf")) if sha(f.read_bytes()) == h), None)


def merge(pdfs: list) -> bytes:
    import pymupdf
    if len(pdfs) == 1:
        return pdfs[0]
    out = pymupdf.open()
    for b in pdfs:
        with pymupdf.open(stream=b, filetype="pdf") as d:
            out.insert_pdf(d)
    return out.tobytes()


def docx_to_pdf(b: bytes) -> bytes:
    """Word referral -> PDF pages, so it goes through the same pipeline as a fax.
    Our Word copies mark page breaks with "Scan page N"; other files flow onto letter pages."""
    if DRY:  # dry run: our fictional Word copy stands for its fictional PDF (same pages as the prepared transcript)
        h = sha(b)
        for f in sorted((REPO / "app/pdf").glob("F[0-9][0-9].docx")):
            if sha(f.read_bytes()) == h:
                return f.with_suffix(".pdf").read_bytes()
        raise ValueError("Dry run accepts only the fictional F01 to F20 Word files")
    import docx
    import textwrap
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    d = docx.Document(io.BytesIO(b))
    lines = []
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            lines.append("".join(t.text or "" for t in el.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            for row in el.iter():
                if row.tag.endswith("}tr"):
                    cells = ["".join(t.text or "" for t in c.iter() if t.tag.endswith("}t")) for c in row if c.tag.endswith("}tc")]
                    lines.append(" | ".join(x.strip() for x in cells))
    pages, cur = [], []
    for ln in lines:
        if re.fullmatch(r"Scan page \d+", ln.strip()) and cur:
            pages.append(cur); cur = []
        cur.append(ln)
    pages.append(cur)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    W, H = letter
    for page in pages:
        y = H - 54
        for ln in page:
            for part in textwrap.wrap(ln, 92) or [""]:
                if y < 50:
                    c.showPage(); y = H - 54
                c.setFont("Courier", 9.5); c.drawString(48, y, part); y -= 13
        c.showPage()
    c.save()
    return buf.getvalue()


IMG = (".jpg", ".jpeg", ".png")


def is_image(b: bytes, name: str = "") -> bool:
    return b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or name.lower().endswith(IMG)


def images_to_pdf(imgs: list) -> bytes:
    """Phone photos of a paper fax: each picture becomes one page, in the order given."""
    if DRY:
        raise ValueError("Dry run cannot use photos: it only knows the prepared fictional packets. Use the live mode.")
    import pymupdf
    out = pymupdf.open()
    for b in imgs:
        with pymupdf.open(stream=b) as im:
            out.insert_pdf(pymupdf.open("pdf", im.convert_to_pdf()))
    return out.tobytes()


def to_pdf(b: bytes, name: str) -> bytes:
    if is_image(b, name):
        return images_to_pdf([b])
    return docx_to_pdf(b) if name.lower().endswith(".docx") or b[:2] == b"PK" else b


ACCEPT = threading.Lock()


def accept(body: bytes, name: str, source: str, meta: dict = None) -> dict:
    """Every channel ends here. Returns {"id"} or {"error"}."""
    if not body.startswith(b"%PDF"):
        return {"error": "That file is not a PDF"}
    fict = fictional(body) if DRY else None
    if DRY and not fict:
        return {"error": "Dry run accepts only the fictional F01 to F20 files from app/pdf/"}
    h = sha(body)
    with ACCEPT:
        for r in OUT.glob("U[0-9][0-9]/received.json"):
            try:
                if json.loads(r.read_text()).get("sha256") == h:
                    return {"error": f"Duplicate: this exact file already arrived as {r.parent.name}", "duplicate": r.parent.name}
            except ValueError:
                pass
        pid = next_id()
        folder = OUT / pid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{pid}.pdf").write_bytes(body)
        (folder / "received.json").write_text(json.dumps({"at": time.time(), "name": name, "dry_run": DRY, "sha256": h,
                                                          "source": source, **(meta or {})}))
        job = {"id": pid, "name": name, "source": SOURCES.get(source, source), "fict": fict, "state": "running",
               "stage": "queued", "msg": "Waiting for the previous packet", "steps": STEPS, "log": [], "dry_run": DRY}
        JOBS[pid] = job
    threading.Thread(target=process, args=(job,), daemon=True).start()
    return {"id": pid}


def read_eml(raw: bytes):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    parts = [(part.get_content(), part.get_filename() or "") for part in msg.iter_attachments()]
    imgs = [b for b, n in parts if isinstance(b, bytes) and is_image(b, n)]
    pdfs = [to_pdf(b, n) for b, n in parts if isinstance(b, bytes) and not is_image(b, n) and (b.startswith(b"%PDF") or n.lower().endswith((".pdf", ".docx")))]
    if imgs:  # photos in one email are pages of one paper referral
        pdfs.append(images_to_pdf(imgs))
    return pdfs, {"from": str(msg.get("From", ""))[:120], "subject": str(msg.get("Subject", ""))[:160]}


def watch() -> None:
    """Pick up PDFs and .eml files saved in intake/; move each to intake/done/ (or intake/rejected/)."""
    INTAKE.mkdir(exist_ok=True)
    for d in ("done", "rejected"):
        (INTAKE / d).mkdir(exist_ok=True)
    seen = {}
    while True:
        for f in sorted(INTAKE.iterdir()):
            if not f.is_file() or f.suffix.lower() not in (".pdf", ".docx", ".eml", *IMG):
                continue
            size = f.stat().st_size
            if seen.get(f) != size:  # wait until the file stops growing (fax software still writing)
                seen[f] = size
                continue
            seen.pop(f, None)
            try:
                raw = f.read_bytes()
                if f.suffix.lower() == ".eml":
                    # one referral per attachment: joining files could merge two patients into one review
                    pdfs, meta = read_eml(raw)
                    res = {"error": "email has no PDF, Word or photo attachment"}
                    ids = []
                    for i, b in enumerate(pdfs, 1):
                        part = {**meta, "attachment": f"{i} of {len(pdfs)}"} if len(pdfs) > 1 else meta
                        r = accept(b, f.name, "email", part)
                        (ids.append(r["id"]) if "id" in r else print(f"intake folder: {f.name} attachment {i}: {r['error']}"))
                    if ids:
                        res = {"id": ", ".join(ids)}
                else:
                    res = accept(to_pdf(raw, f.name), f.name, "folder")
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {e}"}
            dest = INTAKE / ("done" if "id" in res else "rejected") / f"{time.strftime('%H%M%S')}-{f.name}"
            shutil.move(str(f), dest)
            print(f"intake folder: {f.name} -> {res.get('id') or res.get('error')}")
        time.sleep(2)


def next_id() -> str:
    used = {p.name for p in OUT.glob("U[0-9][0-9]")} | set(JOBS)
    for n in range(1, 100):
        if f"U{n:02d}" not in used:
            return f"U{n:02d}"
    raise RuntimeError("no free upload IDs (U01-U99)")


class JobLog(io.TextIOBase):
    def __init__(self, job):
        self.job = job

    def write(self, s):
        for line in s.splitlines():
            if line.strip():
                self.job["msg"] = line.strip()
                self.job["log"].append(line.strip())
        return len(s)


def step(job, name):
    job["stage"] = name
    job["msg"] = ""
    job["log"].append(f"[{name}]")


def process(job: dict) -> None:
    import clean
    import score
    import build_app
    pid, folder = job["id"], OUT / job["id"]
    src = folder / f"{pid}.pdf"
    with LOCK, contextlib.redirect_stdout(JobLog(job)):
        try:
            step(job, "fix")
            try:
                fixed = clean.fix(src, folder)
            except Exception as e:  # ocrmypdf missing or failed: use the pages as scanned
                print(f"page fixing skipped ({type(e).__name__}); using pages as scanned")
                fixed = src
            images = clean.render(fixed, folder)
            print(f"{len(images)} pages")
            pages_json = folder / f"{pid}.pages.json"

            step(job, "transcribe")
            if DRY:
                print(f"DRY RUN: reusing the prepared transcript of fictional {job['fict']}")
                pages = json.loads((REPO / f"demo/fictional/{job['fict']}/{job['fict']}.pages.json").read_text())
                pages["packet_id"] = pid
                pages_json.write_text(json.dumps(pages, indent=2))
            else:
                clean.transcribe(images, pid, pages_json)
            pages = json.loads(pages_json.read_text())
            if len(pages["pages"]) != len(images):
                raise RuntimeError(f"transcript has {len(pages['pages'])} pages, packet has {len(images)}")
            clean.build(pages, images, folder / f"{pid}.readable.pdf", job["name"])

            step(job, "check")
            if DRY:
                print(f"DRY RUN: reusing the prepared criteria check of fictional {job['fict']}")
                check = json.loads((REPO / f"demo/fictional/{job['fict']}/{job['fict']}.json").read_text())
                check["packet_id"] = pid
                (folder / f"{pid}.json").write_text(json.dumps(check, indent=2))
            else:
                import check as checker
                checker.run(pages_json, log=print)

            step(job, "score")
            scored = score.score_packet(json.loads((folder / f"{pid}.json").read_text()), pages, score.load_rules())
            (folder / f"{pid}.scored.json").write_text(json.dumps(scored, indent=2))
            v = scored["verification"]
            print(f"fit {scored['fit']['score']} ({scored['fit']['label']}), {v['verified']}/{v['quotes']} quotes found on their page")

            step(job, "build")
            build_app.main(["--real"])
            job.update(stage="done", state="done", msg="Added to the inbox")
        except Exception as e:
            raw = f"{type(e).__name__}: {e}"
            hints = [("workspace", "The API key needs a valid workspace ID (wrkspc_...), or use a key created inside a workspace. Restart start-desk.bat."),
                     ("authentication", "The API key was not accepted. Check it in console.anthropic.com and restart start-desk.bat."),
                     ("credit", "The API account is out of credits. Claim or add credits in console.anthropic.com."),
                     ("rate_limit", "Too many requests right now. Wait a minute and drop the PDF again."),
                     ("Connection", "Could not reach the Claude API. Check the internet connection and drop the PDF again.")]
            hint = next((h for k, h in hints if k.lower() in raw.lower()), None)
            job.update(state="error", msg=f"{hint}  [{raw[:200]}]" if hint else raw)
            job["log"].append(traceback.format_exc(limit=3))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(REPO), **kw)

    def log_message(self, fmt, *args):  # keep the terminal quiet; errors still show
        if args and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/output/app/index.html")
            self.end_headers()
            return
        if path == "/portal":
            self.path = "/app/portal.html"
            return super().do_GET()
        if path == "/api/ping":
            return self.send_json({"ok": True, "dry_run": DRY, "email": INTAKE_EMAIL, "key": DRY or bool(os.environ.get("ANTHROPIC_API_KEY"))})
        if path == "/api/decisions":  # append-only decision record on disk
            f = OUT / "decisions.jsonl"
            rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []
            return self.send_json(rows)
        if path == "/api/jobs":
            return self.send_json([{k: v for k, v in j.items() if k != "log"} | {"log": j["log"][-6:]} for j in JOBS.values()])
        if re.search(r"(^|/)\.(env|git)", path):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        from urllib.parse import unquote
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        limit = MAX_BYTES * 2 if path == "/api/intake/portal" else MAX_BYTES  # base64 adds a third
        if not 0 < n <= limit:
            return self.send_json({"error": "File missing or over 60 MB"}, 400)
        body = self.rfile.read(n)
        if path == "/api/decisions":
            try:
                e = json.loads(body)
                assert re.fullmatch(r"[A-Z]\d\d", str(e.get("id"))) and e.get("decision") in ("approve", "info", "deny", "replied", "arrived")
            except (ValueError, AssertionError):
                return self.send_json({"error": "bad decision record"}, 400)
            OUT.mkdir(exist_ok=True)
            with ACCEPT, open(OUT / "decisions.jsonl", "a", encoding="utf-8") as f:  # append only, never rewritten
                f.write(json.dumps(e) + "\n")
            return self.send_json({"ok": True})
        if path == "/api/upload":
            name = Path(unquote(self.headers.get("X-Filename") or "upload.pdf")).name[:120]
            try:
                res = accept(to_pdf(body, name), name, "upload")
            except ValueError as e:
                res = {"error": str(e)}
        elif path == "/api/upload/photos":
            try:
                form = json.loads(body)
                imgs = [base64.b64decode(f["b64"]) for f in form.get("files", [])][:60]
                if not imgs or not all(is_image(b) for b in imgs):
                    return self.send_json({"error": "Photos must be JPG or PNG"}, 400)
                res = accept(images_to_pdf(imgs), f"{len(imgs)} photos", "upload", {"photos": len(imgs)})
            except ValueError as e:
                res = {"error": str(e)}
        elif path == "/api/intake/fax":
            # the shape a fax service webhook would use: raw PDF body, sender's fax number in a header
            sender = unquote(self.headers.get("X-Fax-From") or "unknown")[:40]
            res = accept(body, f"fax from {sender}", "fax", {"from": sender})
        elif path == "/api/intake/portal":
            try:
                form = json.loads(body)
                raw = [(base64.b64decode(f["b64"]), str(f.get("name", ""))) for f in form.get("files", [])][:40]
                imgs = [b for b, n in raw if is_image(b, n)]
                pdfs = [to_pdf(b, n) for b, n in raw if not is_image(b, n)] + ([images_to_pdf(imgs)] if imgs else [])
                if not pdfs:
                    return self.send_json({"error": "Attach at least one PDF"}, 400)
                if not all(b.startswith(b"%PDF") for b in pdfs):
                    return self.send_json({"error": "Every attached file must be a PDF, Word file or photo"}, 400)
                clip = lambda k, n=120: str(form.get(k) or "")[:n]
                meta = {"from": clip("sender"), "hospital": clip("hospital"), "contact": clip("contact"),
                        "declared_docs": [d for d in form.get("docs", []) if re.fullmatch(r"DOC-\d{1,2}", str(d))]}
                res = accept(merge(pdfs), f"portal: {meta['hospital'] or 'hospital'}", "portal", meta)
            except (ValueError, KeyError, TypeError) as e:
                return self.send_json({"error": f"Could not read the form ({type(e).__name__})"}, 400)
        else:
            return self.send_error(404)
        return self.send_json(res, 200 if "id" in res else 409 if res.get("duplicate") else 400)


def main() -> None:
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--open", action="store_true", help="open the browser once the server is listening")
    args = ap.parse_args()
    DRY = args.dry_run
    if not DRY and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Set it in your shell (not in the repo), or use --dry-run to test.")
    if not shutil.which("ocrmypdf"):
        print("note: ocrmypdf not found, pages will be used as scanned (no auto-rotate)")
    import build_app
    build_app.main(["--real"])
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        sys.exit(f"Port {args.port} is busy ({e}). Close the other Referral Desk window, or add --port 8001.")
    url = f"http://127.0.0.1:{args.port}"
    print(f"Referral Desk{' (DRY RUN)' if DRY else ''} is running: {url}   Keep this window open. Ctrl+C to stop.")
    if args.open:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, [url]).start()
    threading.Thread(target=watch, daemon=True).start()
    print(f"Watching {INTAKE} for PDFs and .eml emails. Hospital portal: {url}/portal")
    srv.serve_forever()


if __name__ == "__main__":
    main()
