"""Compare the tool's calls with IHH's real decisions (eval/decisions.json).

Run only after every packet is checked; the checks never see the decisions.
  python src/evaluate.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DECISIONS = REPO / "challenges/1-referral-intake/eval/decisions.json"
BAND_CALL = {"fit": "approve", "info": "needs_info", "nofit": "deny"}


def main(argv: list[str]) -> None:
    out_root = Path(argv[1]) if len(argv) > 1 else REPO / "output"
    truth = {p["packet_id"]: p["decision"] for p in json.loads(DECISIONS.read_text())["packets"]}
    rows, tally = [], {"rule": [0, 0, 0], "claude": [0, 0, 0]}  # right, wrong, needs_info
    for pid, dec in truth.items():
        f = out_root / pid / f"{pid}.scored.json"
        if not f.exists():
            rows.append((pid, dec, "-", "-", "-", "-"))
            continue
        d = json.loads(f.read_text())
        calls = {"rule": BAND_CALL[d["fit"]["band"]], "claude": d.get("claude_fit", {}).get("recommendation", "?")}
        for k, c in calls.items():
            tally[k][2 if c == "needs_info" else 0 if c == dec else 1] += 1
        rows.append((pid, dec, f'{d["fit"]["score"]} {calls["rule"]}', calls["claude"],
                     ",".join(d["fit"]["blockers"]) or "-", d.get("claude_fit", {}).get("score", "-")))

    print(f"{'pkt':4} {'IHH':8} {'rule score':18} {'claude':11} {'c.score':7} blockers")
    for pid, dec, rule, cl, bl, cs in rows:
        print(f"{pid:4} {dec:8} {rule:18} {cl:11} {str(cs):7} {bl}")
    for k, (r, w, n) in tally.items():
        print(f"{k:7} right {r}  wrong {w}  needs_info {n}  (of {r + w + n})")


if __name__ == "__main__":
    main(sys.argv)
