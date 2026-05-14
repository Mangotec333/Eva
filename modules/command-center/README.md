# EVA Command Center — Module 4

> Unified priority dashboard for a solo founder. Convert every ounce of time and energy to revenue. $10K/mo threshold = arrow flips.

## Stack

- **Vite 5** + **React 18** + **TypeScript**
- **Tailwind CSS 3** — dark theme, military ops aesthetic
- **Recharts** — charts and sparklines
- **Lucide React** — icons

## Backend Dependencies

| Service | Port | Endpoint |
|---|---|---|
| Deal Scout API | `8766` | `GET /deals` |
| EVA Context API | `8765` | `GET /context/today` |

Both services are optional — the dashboard gracefully shows offline states when they're unreachable.

## Dev Setup

```bash
npm install
npm run dev
# → http://localhost:5173
```

## Build

```bash
npm run build
npm run preview
```

## Architecture

```
src/
├── App.tsx                 ← Root layout, grid assembly
├── main.tsx
├── index.css               ← Tailwind + custom utilities
├── components/
│   ├── CommandHeader.tsx   ← Sticky top bar: clock, status pills, refresh
│   ├── PriorityStack.tsx   ← 6 life priorities with status badges
│   ├── DealTracker.tsx     ← Deal pipeline from Deal Scout API (polls 60s)
│   ├── RevenueGauge.tsx    ← Progress to $10K/mo threshold
│   ├── EnergyBudget.tsx    ← Today's time/energy allocation
│   ├── ActionQueue.tsx     ← Top 3 highest-leverage actions (checkboxes)
│   └── ActivityFeed.tsx    ← EVA Context API activity feed (polls 30s)
├── hooks/
│   ├── useDeals.ts         ← Fetches + polls localhost:8766/deals
│   └── useEvaContext.ts    ← Fetches + polls localhost:8765/context/today
└── types/
    └── index.ts            ← All shared TypeScript interfaces
```

## Polling Intervals

- **Deal Scout API**: every 60 seconds
- **EVA Context API**: every 30 seconds

## Color System

| Purpose | Color |
|---|---|
| Primary / Active | Cyan `#06b6d4` |
| Warnings / Alerts | Amber `#f59e0b` |
| Positive / Revenue | Green `#22c55e` |
| Critical / Danger | Red `#ef4444` |
| Background base | `gray-950` |
| Card surface | `gray-900` |

## Next Sprint

- Connect RevenueGauge to real revenue data
- Persist ActionQueue completions to localStorage
- Add editable energy budget sliders
- Historical revenue sparkline in RevenueGauge
- Deal detail modal on click
