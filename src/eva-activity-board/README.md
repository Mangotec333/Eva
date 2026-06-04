# EVA Activity Board

Kanban + Energy Log + Audit Trail for EVA Command Center.

**Stack:** React + Express + SQLite + Drizzle ORM + Tailwind + shadcn/ui

## Run locally (Mac)

```bash
cd ~/Eva/src/eva-activity-board
npm install
npm install @rollup/rollup-linux-x64-gnu --save-optional
npx tsx server/seed.ts   # seed initial tasks (first run only)
npm run dev              # http://localhost:5000
```

## Deploy via Docker

```bash
cd ~/Eva/src/eva-activity-board
docker compose -f docker-compose.activity-board.yml up -d --build
```

Runs on port 3001. Set `eva.mangotec.ai` → `localhost:3001` in your reverse proxy.

## Environment

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | HTTP port |
| `NODE_ENV` | `development` | Environment |
| `DATABASE_PATH` | `data.db` | SQLite DB path |

## Features

- Kanban board: In Progress / Planned / Completed / Carry Over / Parking Lot
- Done button on each task card (timestamped, logged to DB)
- Energy log: 1-5 rating for morning/midday/evening
- Full audit log — every event preserved by timestamp, never deleted (ML training data)
- Add/edit/archive tasks (soft delete only)
- Stats bar with completion rate

## Driving Principles

> Ship fast · Get feedback · Fail fast · Pivot · No perfect
> Simple · Modern · Minimalistic · Intuitive
