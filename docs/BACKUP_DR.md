# EVA Backup & Disaster Recovery — Proposal (v1 draft)

**Status:** proposal / not yet implemented. This document describes a backup and
disaster-recovery (DR) plan for EVA's data. The actual backup **destination** is
intentionally left as a `TODO` / config placeholder — choosing where backups go
(and paying for it) is an owner decision, not something this doc should pick.

## What we are protecting

EVA follows a **SQLite-per-module** architecture (Architecture Directive: "one
module = one autonomous agent … own SQLite database"). The durable state that
matters is therefore spread across:

1. **Per-module SQLite databases** — each module keeps its own `*.db` file
   (e.g. `modules/postcards/eva-postcards.db`, `modules/health-monitor/health_monitor.db`,
   finance-tracker, deployer, ghl-agent, outreach, …). These hold the
   append-only **ledgers** (the audit trail / recovery source), the per-agent
   **memory** tables, and each module's domain data.
2. **The `~/.eva/` runtime dir** — OAuth tokens and credentials
   (`~/.eva/drive_token.pickle`, `~/.eva/drive_credentials.json`), plus any
   module data dirs a module chooses to place there.
3. **Generated artifacts** — rendered images, transcripts, exports written under
   a module's `data/` dir.

Not backed up (recreatable): Python virtualenvs, `__pycache__`, cloned repos,
anything derivable from source.

## Why the ledgers make this tractable

Every module's ledger is **append-only** (enforced by a SQLite trigger). That
means a backup is always internally consistent up to the last committed row, and
recovery can be reasoned about as "replay/inspect the ledger" rather than
"hope the mutable state was consistent." The ledger is the recovery source of
record.

## Proposed backup strategy

### 1. Periodic snapshot (the simple, frugal default)

A single scheduled job (cron / launchd, alongside the other EVA ticks) that:

1. For each module DB, takes a **consistent** copy using SQLite's own backup API
   rather than copying the file mid-write:
   ```bash
   sqlite3 "$DB" ".backup '$STAGING/$module.db'"
   ```
   (`.backup` is safe against concurrent writers; a plain `cp` is not.)
2. Copies the small credential/runtime files from `~/.eva/`.
3. Rolls the staging dir into a timestamped, compressed archive:
   ```bash
   tar -czf "eva-backup-$(date +%Y%m%dT%H%M%SZ).tar.gz" -C "$STAGING" .
   ```
4. Ships the archive to the backup **destination**:
   ```bash
   # TODO(owner): choose a destination and fill this in. Options, not decisions:
   #   - rsync/scp to an owner-controlled box
   #   - a cloud object store bucket (S3/GCS/B2) via its CLI
   #   - the existing EVA Google Drive (EVA/Backups/) via drive_organizer's OAuth
   # BACKUP_DEST="__TODO__"
   ```
5. Applies **retention** at the destination (e.g. keep hourly for 24h, daily for
   30d, weekly for 1y) — exact policy is a `TODO(owner)` tied to the chosen
   destination's cost.

Recommended cadence: **hourly** snapshots (the DBs are tiny), or after each
module `tick` for the highest-write modules (finance-tracker, deployer,
ghl-agent). Snapshots are cheap because SQLite files are small and compress well.

### 2. Off-box requirement

At least one retained copy must live **off the EVA host**. A backup on the same
disk does not survive disk loss. The destination in step 4 must be off-box;
that is the whole point of DR.

### 3. Encryption

Backups contain OAuth tokens and business data. Encrypt at rest before/at the
destination (e.g. `age`/`gpg` on the archive, or destination-side SSE). Key
custody is a `TODO(owner)`.

## Proposed restore / DR runbook

1. **Provision** a fresh host, clone the repo, run each module's `setup.sh`.
2. **Fetch** the latest good archive from the destination; decrypt; extract to
   staging.
3. **Restore** each `*.db` into its module dir and the `~/.eva/` files into place.
4. **Verify** integrity per DB before going live:
   ```bash
   sqlite3 "$DB" "PRAGMA integrity_check;"     # expect: ok
   ```
5. **Reconcile** using the append-only ledgers: confirm the last ledger event in
   each module matches the last externally-observed action; anything after the
   snapshot is replayed or re-driven manually (idempotent `tick`s make this safe).
6. **Health-check** the fleet: bring services up and run the **Health Monitor**
   (`modules/health-monitor`) `tick` — every module should report `up` before DR
   is declared complete.

## Targets (proposed, owner to ratify)

| Metric | Proposed target | Notes |
|--------|-----------------|-------|
| RPO (max data loss) | ≤ 1 hour | matches hourly snapshot cadence |
| RTO (time to restore) | ≤ 1 hour | clone + restore + verify on a fresh box |
| Retention | 24×hourly, 30×daily, 52×weekly | `TODO(owner)` — cost-dependent |
| Backup integrity test | monthly restore drill | restore to scratch, run integrity_check |

## Open decisions (owner `TODO`s)

- [ ] **Destination**: where do archives go? (off-box box / object store / Drive)
- [ ] **Encryption key custody**: who holds the key, where is it escrowed?
- [ ] **Retention policy** + budget at the chosen destination.
- [ ] **Cadence** per module tier (hourly baseline vs per-tick for money/deploy modules).
- [ ] **Monthly restore drill** owner + calendar.

## Relationship to the Health Monitor

This DR plan and `modules/health-monitor` are complementary: the monitor detects
**liveness** failures (a module is down) in near-real-time; this plan handles
**durability** failures (data/host loss). A future enhancement is to let the
monitor also emit an alert if the most recent successful backup is older than the
RPO — turning "did the backup run?" into a watched signal like everything else.
