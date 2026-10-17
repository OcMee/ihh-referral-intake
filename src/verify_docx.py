"""Check that each Word file says exactly what its transcript says.

For every page it compares the transcript (RXX.pages.json) with the text pulled back out of RXX.docx:
  words      every word of the transcript is in the Word page (nothing dropped)
  redacted   same number of redaction bars
  boxes      same number of checked / unchecked boxes
  yes/no     every single-answer line turned into Yes/No boxes ticks the answer the form gave
Exit code 1 if anything fails, so it can gate a build.

  python src/verify_docx.py output/R??/R??.pages.json demo/fictional/F0?/F0?.pages.json
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from docx import Document

# must match the single-answer rule in to_docx.js
YN = re.compile(r"^([^\[\]:?]+)([:?])\s*(Yes|No)(?:\s*\[X\])?(?:\s*\(([^()\[\]]*)\))?$", re.I)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD = re.compile(r"[A-Za-z0-9]+(?:[.'][A-Za-z0-9]+)*")


def docx_pages(path: Path) -> dict:
    """Text of the Word file, split at the 'Scan page N' markers to_docx.js writes.
    Redaction bars (black-shaded runs) come back as the token REDACTION_BAR."""
    doc = Document(path)
    body = doc.element.body
    for r in body.iter():
        if r.tag.endswith("}r") and any(x.tag.endswith("}shd") and x.get(f"{{{W_NS}}}fill") == "111111" for x in r.iter()):
            for t in r.iter():
                if t.tag.endswith("}t"):
                    t.text = " REDACTION_BAR "
    lines = []
    for el in body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            lines.append("".join(t.text or "" for t in el.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            for row in el.iter():
                if row.tag.endswith("}tr"):
                    lines.append(" | ".join("".join(t.text or "" for t in c.iter() if t.tag.endswith("}t"))
                                            for c in row if c.tag.endswith("}tc")))
    pages, cur = {}, None
    for ln in lines:
        m = re.match(r"^Scan page (\d+)(?:  ·.*)?$", ln)
        if m:
            cur = int(m.group(1))
            pages[cur] = []
            continue
        if cur is not None:
            pages[cur].append(ln)
    return {k: "\n".join(v) for k, v in pages.items()}


def check_page(p: dict, got: str, form_like: bool) -> list:
    issues = []
    text = p["text"] + ("\n" + p["notes"] if p.get("notes") else "")
    exp_checked = exp_unchecked = 0
    for raw in text.split("\n"):
        line = raw.strip()
        body = line[2:] if line.startswith("- ") else line
        m = YN.match(body.rstrip()) if form_like else None
        if m:
            exp_checked += 1
            exp_unchecked += 1
            want = m.group(3).capitalize()
            label = m.group(1).strip()
            if not re.search(re.escape(label) + r"\??[^\n]*?☒ " + want, got):
                issues.append(f"yes/no: '{label}' should tick {want}")
        else:
            exp_checked += line.count("[X]")
            exp_unchecked += line.count("[ ]") + line.count("[?]")
    got_checked, got_unchecked = got.count("☒"), got.count("☐")
    if (got_checked, got_unchecked) != (exp_checked, exp_unchecked):
        issues.append(f"boxes: expected {exp_checked} checked / {exp_unchecked} unchecked, "
                      f"Word has {got_checked} / {got_unchecked}")

    exp_red = text.count("[REDACTED]")
    got_red = got.count("REDACTION_BAR")
    if exp_red != got_red:
        issues.append(f"redactions: expected {exp_red}, Word has {got_red}")

    clean = re.sub(r"\[(REDACTED|X| |\?|illegible|POSSIBLE MISSED REDACTION)\]", " ", text)
    clean = re.sub(r"^##\s+|^-\s+", "", clean, flags=re.M)
    want = Counter(w.lower() for w in WORD.findall(clean))
    have = Counter(w.lower() for w in WORD.findall(got))
    missing = {w: n - have[w] for w, n in want.items() if have[w] < n}
    if missing:
        sample = ", ".join(f"{w}" + (f" x{n}" if n > 1 else "") for w, n in list(missing.items())[:8])
        issues.append(f"words missing ({sum(missing.values())}): {sample}")
    return issues


def main(files: list) -> int:
    total_pages = bad_pages = 0
    for f in map(Path, files):
        data = json.loads(f.read_text())
        dx = f.with_name(f"{data['packet_id']}.docx")
        if not dx.exists():
            print(f"{data['packet_id']}: no .docx")
            bad_pages += 1
            continue
        got = docx_pages(dx)
        issues_here = 0
        for p in data["pages"]:
            total_pages += 1
            form_like = p["doc_type"] in ("referral_form", "calaim_auth")
            issues = ["page missing from Word file"] if p["page"] not in got else check_page(p, got[p["page"]], form_like)
            if issues:
                bad_pages += 1
                issues_here += 1
                for i in issues:
                    print(f"  {data['packet_id']} p{p['page']}: {i}")
        print(f"{data['packet_id']}: {len(data['pages']) - issues_here}/{len(data['pages'])} pages match")
    print(f"\n{total_pages - bad_pages}/{total_pages} pages match their transcript")
    return 1 if bad_pages else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
