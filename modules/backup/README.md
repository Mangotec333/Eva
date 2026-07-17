# EVA Backup

Periodic, cron-safe backup of every EVA module's local SQLite files to Google
Drive, with simple retention.

On each `tick` the service:

1. Scans `modules/*/*.db` — every module's local SQLite files — at runtime.
2. `tar`+`gzip`s them into one timestamped archive (`eva-backup-YYYYMMDDTHHMMSSZ.tar.gz`).
   Each db is stored under `<module>/<file>.db` inside the archive so it is
   self-describing.
3. Uploads the archive to the configured Drive folder.
4. Applies retention: keeps the newest **N** archives (default 14), deletes older
   ones via the Drive API. Only files named `eva-backup-*` are ever touched.
5. Logs success/failure and every retention delete to its own `memory` table and
   an append-only `backup_ledger` (immutable — `UPDATE`/`DELETE` are blocked by
   triggers, the canonical `modules/postcards` pattern).

`tick` is idempotent and cron-safe: each run just produces the next timestamped
archive, and retention converges the folder to N archives no matter how many
ticks fire.

Google Drive is the **single network chokepoint**. All Drive I/O lives behind a
`DriveClient` Protocol with a `StubDriveClient` (offline, in-memory — used in
tests, no network) and a `RealDriveClient` (real `googleapiclient`). The service
is **offline by default** so nothing real fires until you opt in.

## Endpoints (port 8793)

| Method | Path             | Description                                        |
|--------|------------------|----------------------------------------------------|
| GET    | `/health`        | Health + config (drive impl, folder set?, retention) |
| POST   | `/backup/tick`   | Run one backup cycle (scan → archive → upload → retain) |
| GET    | `/backup/status` | Config + last run + archives currently in Drive    |
| GET    | `/backup/ledger` | Append-only audit trail (`?event_type=&limit=`)    |

## CLI

```bash
python cli.py tick                     # run one backup cycle
python cli.py status                   # config + last run + Drive archives
python cli.py ledger --event backup_ok # append-only audit trail
```

## Prerequisites to go live

By default the module runs against the offline `StubDriveClient` (no creds, no
network — this is what the tests use). To back up to **real** Google Drive:

1. **Drive OAuth credentials** at `~/.eva/drive_credentials.json` — the **same
   file `meet-ingest` / `drive_organizer` use**. Download an OAuth
   `client_secret.json` from Google Cloud (Drive API enabled, scope
   `https://www.googleapis.com/auth/drive`) and save it there. First real run
   opens a browser consent flow and caches a token at
   `~/.eva/drive_token.pickle`.
2. **`EVA_BACKUP_DRIVE_FOLDER_ID`** — the Drive folder ID to upload archives
   into. Without it, a real tick refuses to upload (logged as `backup_error`).
3. **`EVA_BACKUP_DRIVE=real`** — switch the factory from the stub to the real
   client.

```bash
export EVA_BACKUP_DRIVE=real
export EVA_BACKUP_DRIVE_FOLDER_ID="<your-drive-folder-id>"
export EVA_BACKUP_RETENTION=14        # optional; default 14
./setup.sh
```

## Environment variables

| Variable                     | Default          | Purpose                                  |
|------------------------------|------------------|------------------------------------------|
| `EVA_BACKUP_DRIVE`           | `stub`           | `real` to use live Google Drive          |
| `EVA_BACKUP_DRIVE_FOLDER_ID` | *(unset)*        | Drive folder archives are uploaded into  |
| `EVA_BACKUP_RETENTION`       | `14`             | Number of archives to keep in Drive      |
| `EVA_BACKUP_DB`              | `eva-backup.db`  | Path to this module's own SQLite db       |
| `EVA_BACKUP_PORT`            | `8793`           | HTTP port                                |

## Tests

Fully offline (zero network) via `StubDriveClient` and temp dirs:

```bash
pytest test_backup.py
```

Covers db discovery, tar+gzip archive contents, upload params, ledger + memory
logging, retention (keep newest N / delete older, never touching foreign files),
and ledger append-only immutability.

## Scheduling

Point cron (or the EVA scheduler) at the tick — e.g. daily at 03:17:

```cron
17 3 * * *  curl -fsS -X POST http://localhost:8793/backup/tick
```
