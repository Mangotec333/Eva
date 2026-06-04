// Seed EVA Activity Board with current session tasks
import Database from "better-sqlite3";

const db = new Database("data.db");

function now() { return new Date().toISOString(); }

db.exec(`
  CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    priority TEXT NOT NULL DEFAULT 'medium',
    category TEXT NOT NULL DEFAULT 'general',
    tags TEXT NOT NULL DEFAULT '[]',
    due_date TEXT,
    completed_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    note TEXT,
    timestamp TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS energy_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level INTEGER NOT NULL,
    period TEXT NOT NULL,
    note TEXT,
    timestamp TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT ''
  );
`);

const tasks = [
  // IN PROGRESS
  {
    title: "batch.ai Due Diligence — 2024 Financials Extraction",
    description: "Extract BATCHAILLC + HAWKINSPNGINC 2024 Form 1120S, QB 2021, Assets Included.docx from seller DD folder",
    status: "in_progress",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "dd", "financials"]),
  },
  {
    title: "EVA Activity Board Build + Deploy",
    description: "Jira/Monday-style kanban with energy log, task states, timestamps, done buttons. Deploy to eva.mangotec.ai",
    status: "in_progress",
    priority: "high",
    category: "eva_build",
    tags: JSON.stringify(["eva", "ui", "kanban"]),
  },
  {
    title: "EF Business Verification — Mangotec LLC",
    description: "app.empireflippers.com → My Account → Verification → Business Ownership. Upload Mangotec LLC proof",
    status: "in_progress",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "ef", "verification"]),
  },
  // PLANNED
  {
    title: "Send Shawn Questions (12 prepared) — After 2024 Returns Reviewed",
    description: "12 DD questions ready. Await 2024 tax return data before sending. Key: sub count at listing, zero new subs May, churn cause, QB upload request",
    status: "planned",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "dd", "shawn"]),
  },
  {
    title: "GHL AI Growth Agency One-Pager",
    description: "Build one-pager for aigrowthagency.org DFY offer. Tony's retainer $1,500/mo. Critical path to $10K by June 25",
    status: "planned",
    priority: "critical",
    category: "revenue",
    tags: JSON.stringify(["ghl", "agency", "revenue"]),
  },
  {
    title: "Check Stripe Invite from Shawn (vineeth@mangotecusa.com spam folder)",
    description: "Shawn sent Stripe access invite. Check spam. Needed to verify live subscriber data",
    status: "planned",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "stripe"]),
  },
  {
    title: "Make Copy of EF Asset Purchase Agreement Template",
    description: "Copy EF's APA template — needed before close. Don't use original",
    status: "planned",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "legal"]),
  },
  {
    title: "Storeys Follow-up Call — 1:30pm today",
    description: "meet.google.com/smd-tyzh-pgq — RCFE Healthcare + Storeys portfolio review",
    status: "planned",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["storeys", "rcfe", "call"]),
  },
  {
    title: "Deploy 3-Tier EVA DB (PG + Qdrant + ArcadeDB)",
    description: "Schema designed, never deployed. Run docker compose up -d from /Users/vineetravi/Eva/ops/docker/. Docker Desktop must be running first",
    status: "planned",
    priority: "high",
    category: "eva_build",
    tags: JSON.stringify(["eva", "db", "infrastructure"]),
  },
  {
    title: "Screenpipe Install + Activity Logger Wire-Up",
    description: "Screenpipe not installed. Activity logger code written but no DB write layer. Install screenpipe, wire to EVA DB for audio/video/event logging",
    status: "planned",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "screenpipe", "activity-logger"]),
  },
  {
    title: "Swoop Financing — Await Response from deals@swoopfunding.com",
    description: "Email sent June 4. Seeking financing for batch.ai $179K acquisition. Down payment needed: $17,984 (10%)",
    status: "planned",
    priority: "medium",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "financing", "swoop"]),
  },
  {
    title: "Apollo + instantly.ai Outreach — AI Growth Agency",
    description: "Apollo outreach running. instantly.ai warm inboxed. Check reply rates, iterate on copy",
    status: "planned",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["agency", "outreach", "apollo"]),
  },
  {
    title: "EVA Angels Architecture — Remove AI Employee Language from All Copy",
    description: "Locked: EVA uses ANGELS (outcome-based) NOT Employees (role-based). Update all docs, landing page, LinkedIn copy",
    status: "planned",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "angels", "copy"]),
  },
  {
    title: "Provisional Patents — Final Filing (needs $$$)",
    description: "Provisional patents filed under Mangotec. Final filing requires funds — watch for Swoop approval or HELOC draw",
    status: "planned",
    priority: "low",
    category: "operations",
    tags: JSON.stringify(["mangotec", "ip", "patents"]),
  },
  // COMPLETED
  {
    title: "HELOC $10K Draw",
    description: "RCFE Healthcare HELOC draw completed June 4",
    status: "completed",
    priority: "critical",
    category: "operations",
    tags: JSON.stringify(["heloc", "rcfe", "funding"]),
    completed_at: new Date("2026-06-04T09:00:00").toISOString(),
  },
  {
    title: "Swoop Financing Email Sent",
    description: "Sent to deals@swoopfunding.com — batch.ai acquisition financing request",
    status: "completed",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "swoop", "financing"]),
    completed_at: new Date("2026-06-04T10:00:00").toISOString(),
  },
  {
    title: "batch.ai LOI Signed",
    description: "LOI signed June 3. DD live with Veronica Ochoa (EF). Broker: Zachary Slater",
    status: "completed",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "loi", "ef"]),
    completed_at: new Date("2026-06-03T12:00:00").toISOString(),
  },
  {
    title: "batch.ai Stripe Data Extraction",
    description: "Extracted: 111 active subs (NOT 160), MRR $5,528, 8.3% monthly churn, $57K uncollectable invoices, zero new subs May 2026",
    status: "completed",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "stripe", "dd"]),
    completed_at: new Date("2026-06-04T09:30:00").toISOString(),
  },
  {
    title: "EVA Activity Board Spec → GitHub Backlog",
    description: "Full spec committed to Mangotec333/Eva repo. Commit: caeddd3",
    status: "completed",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "github", "spec"]),
    completed_at: new Date("2026-06-04T10:30:00").toISOString(),
  },
  {
    title: "AI Employee Blueprint Infographic — LinkedIn",
    description: "1200x1600px infographic built and shared. Angels vs AI Employees distinction locked",
    status: "completed",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["eva", "linkedin", "content"]),
    completed_at: new Date("2026-06-04T10:00:00").toISOString(),
  },
  // PARKING LOT
  {
    title: "Tatiana AI Workroom — Partnership / Funnel Strategy",
    description: "$47/mo, 19 members. Her DIY model → EVA DFY model. Explore: affiliate, joint webinar, or cross-promotion. Her members = future $1,500/mo clients",
    status: "parking_lot",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["tatiana", "partnership", "agency"]),
  },
  {
    title: "Jay Prasad — GSA/Federal Projects",
    description: "Deferred payment arrangement. BWConsultants grants for POCs — needs $5K deposit. EVA as proof of concept",
    status: "parking_lot",
    priority: "low",
    category: "revenue",
    tags: JSON.stringify(["jay", "federal", "mangotec"]),
  },
  {
    title: "PurePlate + Glossai Shopify Stores",
    description: "Dropshipping: PurePlate (kitchenware) + Glossai (organic skincare). Testing mode. Build-in-public strategy active",
    status: "parking_lot",
    priority: "low",
    category: "revenue",
    tags: JSON.stringify(["shopify", "dropshipping", "ecommerce"]),
  },
  {
    title: "Signature Talk — Finalize Draft",
    description: "Raw input collected this session and appended to Google Doc worksheet. Was: finalize Sat/Sun May 30-31 — slipped. Now: TBD",
    status: "parking_lot",
    priority: "low",
    category: "outreach",
    tags: JSON.stringify(["signature-talk", "linkedin", "content"]),
  },
];

const ts = now();
for (const task of tasks) {
  const { completed_at, ...rest } = task as typeof task & { completed_at?: string };
  const row = db.prepare(`
    INSERT INTO activities (title, description, status, priority, category, tags, completed_at, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    rest.title,
    rest.description || null,
    rest.status,
    rest.priority,
    rest.category,
    rest.tags,
    completed_at || null,
    completed_at || ts,
    completed_at || ts,
  );

  // Log creation event
  db.prepare(`
    INSERT INTO activity_events (activity_id, event_type, from_status, to_status, note, timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(row.lastInsertRowid, "created", null, rest.status, "Seeded from EVA session context", ts);
}

console.log(`Seeded ${tasks.length} tasks`);
db.close();
