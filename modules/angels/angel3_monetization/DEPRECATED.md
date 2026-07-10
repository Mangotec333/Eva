# DEPRECATED — Yaksha (Angel 3, Monetization)

**Status:** Deprecated 2026-07-09. Superseded by the governed **Monetizing Agent**
at [`modules/monetizing-agent/`](../../monetizing-agent/) (HTTP `:8772`).

Yaksha's code is retained for reference only. It is **no longer registered in
autostart** (`com.eva.angel3` was removed from the `SERVICES` array in
`modules/autostart/eva-install-services.sh`). Do not extend this module.

## Why it was replaced

Yaksha worked but was **ungoverned**:

- Called OpenAI directly (no swappable brain, no offline path, no Stub for tests).
- No approval gate — nothing stopped an irreversible action from firing.
- No append-only ledger of what it proposed/executed; no immutable audit trail.
- No shared KB index integration.
- Emitted a single daily "best opportunity" rather than a ranked, scored,
  packaged weekly play list.

## What replaces each piece

| Yaksha concept                        | Monetizing Agent equivalent                          |
| ------------------------------------- | ---------------------------------------------------- |
| Direct `OpenAI` call                  | `brain.py` — `MonetizationBrain` Protocol + Stub     |
| Daily "single best opportunity"       | Weekly Mine→Match→Package→Route→Follow-up scan       |
| Ad-hoc log file                       | `memory.py` append-only `monetization_plays` ledger  |
| (none) approval                       | Approval gate: `pending → approved → executed`       |
| (none) audit                          | Immutability trigger on the ledger                   |
| (none) shared index                   | `modules/kb_index` shared Drive Master Index writer  |
| `launchd/com.eva.angel3.plist` (daily)| `modules/monetizing-agent/launchd/com.eva.monetizing.plist` (weekly Sunday) |

## Migration

Nothing to migrate operationally — the new agent mines the same repo signals
(deals, social, specs, git). Historical Yaksha logs at `~/.eva/` are untouched.

If you need the old behavior for a one-off, run it manually:

```bash
cd modules/angels/angel3_monetization && python3 angel3_monetization.py
```
