# Team plan

Challenge 1: referral intake for Illumination Health + Home (IHH).
Goal: a coordinator opens one page per referral and gets a recommendation, the rule-by-rule
reasons with page citations, what is missing, and what to ask the hospital.

## Who owns what

| Area | Owner | Files |
|---|---|---|
| Extraction, verify pass, accuracy eval | Cornel | `src/`, `eval/` |
| Coordinator view, README, demo | Oana | `ui/`, `README.md` |
| Shared shape | both | `CONTRACT.md` (change only after talking) |

Stay in your own folders and you won't get merge conflicts.

## Timeline (Oct 17)

| Time | What |
|---|---|
| 11:00 to 11:30 | Oana: interview IHH coordinator. Cornel: extraction on R01 and R02 |
| 12:30 | R01 end to end: JSON matching `CONTRACT.md` |
| 1:30 | All 11 packets run, accuracy vs `eval/decisions.json` |
| 2:30 | UI reads real `output/*.json` |
| 3:00 | Code freeze |
| 3:00 to 3:45 | README, demo script, recording |
| 4:00 | Submit repo + claudesocal.com form |

Pull and push every 30 to 45 minutes.

## Rules we follow

- Packets stay in `challenges/1-referral-intake/packets/` locally. Never commit them. `.gitignore`
  already blocks them.
- `output/` holds real packet output and is git ignored. Only the fake `ui/sample_output.json` is
  committed.
- The engine never reads `eval/decisions.json` while reviewing. Only the eval script reads it.
- Unknown stays unknown. Redacted dates mean `cant_tell`.
- API key lives in `ANTHROPIC_API_KEY`, never in git.

## Questions for the IHH coordinator (Oana)

1. What do you look at first when a packet arrives?
2. Which rules kill most referrals?
3. Where in the chart do you usually find the deciding fact?
4. What do you write back to the hospital when you need more info?
5. Would you trust a tool's "deny"? What would you need to see first?
