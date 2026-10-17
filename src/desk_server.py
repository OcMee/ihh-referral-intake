"""Run Referral Desk on this computer with drag-and-drop intake of new referral PDFs.

  export ANTHROPIC_API_KEY=...        (never put it in the repo)
  python src/desk_server.py           then open http://127.0.0.1:8000

A dropped PDF is saved to output/U01/U01.pdf (git ignored) and goes through the same pipeline as the
11 IHH packets: straighten pages, transcribe with Claude, criteria check with Claude (src/check.py),
verify every quote and score (src/score.py), then the inbox rebuilds and shows it.

The server listens on 127.0.0.1 only, so nothing is reachable from other machines. Uploaded packets
are patient data: do not run this on a shared or public host.

  python src/desk_server.py --dry-run   test the plumbing without the API: accepts only the
                                        fictional app/pdf/F0X.pdf files and reuses their prepared
                                        transcript and check. Every step is logged as a dry run.
"""

import argparse
import contextlib
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
MAX_BYTES = 60 * 1024 * 1024
STEPS = ["fix", "transcribe", "check", "score", "build"]

JOBS: dict = {}
LOCK = threading.Lock()  # one packet at a time: the API calls are the slow part
DRY = False


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
                print(f"DRY RUN: reusing the prepared transcript of fictional {job['source']}")
                pages = json.loads((REPO / f"demo/fictional/{job['source']}/{job['source']}.pages.json").read_text())
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
                print(f"DRY RUN: reusing the prepared criteria check of fictional {job['source']}")
                check = json.loads((REPO / f"demo/fictional/{job['source']}/{job['source']}.json").read_text())
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
        if path == "/api/ping":
            return self.send_json({"ok": True, "dry_run": DRY, "key": DRY or bool(os.environ.get("ANTHROPIC_API_KEY"))})
        if path == "/api/jobs":
            return self.send_json([{k: v for k, v in j.items() if k != "log"} | {"log": j["log"][-6:]} for j in JOBS.values()])
        if re.search(r"(^|/)\.(env|git)", path):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/upload":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n <= MAX_BYTES:
            return self.send_json({"error": "PDF missing or over 60 MB"}, 400)
        body = self.rfile.read(n)
        if not body.startswith(b"%PDF"):
            return self.send_json({"error": "That file is not a PDF"}, 400)
        from urllib.parse import unquote
        name = Path(unquote(self.headers.get("X-Filename") or "upload.pdf")).name[:120]
        source = Path(name).stem.upper()
        if DRY and not re.fullmatch(r"F0[1-9]", source):
            return self.send_json({"error": "Dry run accepts only the fictional F01.pdf to F09.pdf from app/pdf/"}, 400)
        pid = next_id()
        folder = OUT / pid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{pid}.pdf").write_bytes(body)
        (folder / "received.json").write_text(json.dumps({"at": time.time(), "name": name, "dry_run": DRY}))
        job = {"id": pid, "name": name, "source": source, "state": "running", "stage": "queued", "msg": "Waiting for the previous packet",
               "steps": STEPS, "log": [], "dry_run": DRY}
        JOBS[pid] = job
        threading.Thread(target=process, args=(job,), daemon=True).start()
        return self.send_json({"id": pid})


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
    srv.serve_forever()


if __name__ == "__main__":
    main()
