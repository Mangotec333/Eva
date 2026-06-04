/**
 * EVA Panel — Seed Script
 * Run: npx tsx server/seed.ts
 */
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { migrate } from "drizzle-orm/better-sqlite3/migrator";
import * as schema from "../shared/schema";

const sqlite = new Database("eva.db");
const db = drizzle(sqlite, { schema });

// ─── Create tables ─────────────────────────────────────────────────────────
sqlite.exec(`
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

  CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'acquisition',
    status TEXT NOT NULL DEFAULT 'scouting',
    ask_price TEXT,
    target_price TEXT,
    mrr TEXT,
    broker TEXT,
    broker_email TEXT,
    seller_name TEXT,
    seller_email TEXT,
    dd_folder_url TEXT,
    score INTEGER,
    notes TEXT,
    next_action TEXT,
    next_action_due TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS energy_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level INTEGER NOT NULL,
    period TEXT NOT NULL,
    note TEXT,
    timestamp TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'brief',
    read INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    cost_tier TEXT NOT NULL DEFAULT 'medium',
    estimated_minutes INTEGER,
    status TEXT NOT NULL DEFAULT 'running',
    subagent_id TEXT,
    result TEXT,
    stalled_at TEXT,
    killed_at TEXT,
    completed_at TEXT,
    started_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_id TEXT NOT NULL,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    schedule_human TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    last_status TEXT,
    next_run TEXT,
    updated_at TEXT NOT NULL DEFAULT ''
  );
`);

const now = new Date().toISOString();
const today = now.split("T")[0];

// ─── Clear existing seed data ──────────────────────────────────────────────
sqlite.exec("DELETE FROM deals; DELETE FROM cron_jobs; DELETE FROM notifications; DELETE FROM agent_tasks;");

// ─── Deals ─────────────────────────────────────────────────────────────────
const deals = [
  {
    name: "batch.ai",
    type: "acquisition",
    status: "dd",
    askPrice: "$179,000",
    targetPrice: "$40,000–$55,000",
    mrr: "$5,528",
    broker: "Zachary Slater",
    brokerEmail: "zachary@empireflippers.com",
    sellerName: "Shawn Hawkins",
    sellerEmail: "shawnhawkins101@gmail.com",
    ddFolderUrl: "https://drive.google.com/drive/folders/1LqtzYXjiUs_jg3kXXbttikSLokJjoK7R",
    score: 62,
    notes: "LOI signed June 3. 111 subs, 8.3% churn, $57K uncollectable, zero new subs May 2026. 2023 tax: $341,901 gross / $179,189 net. 2024 financials pending.",
    nextAction: "Extract 2024 financials → send 12 DD questions to Shawn",
    nextActionDue: today,
    createdAt: now,
    updatedAt: now,
  },
  {
    name: "RCFE Portfolio — Storeys",
    type: "rcfe",
    status: "loi",
    askPrice: null,
    targetPrice: null,
    mrr: null,
    broker: null,
    brokerEmail: null,
    sellerName: null,
    sellerEmail: null,
    ddFolderUrl: null,
    score: 75,
    notes: "HELOC $10K draw completed June 4. Storeys call today at 1:30pm.",
    nextAction: "Storeys call → meet.google.com/smd-tyzh-pgq",
    nextActionDue: today,
    createdAt: now,
    updatedAt: now,
  },
  {
    name: "GHL AI Growth Agency",
    type: "agency",
    status: "scouting",
    askPrice: null,
    targetPrice: null,
    mrr: null,
    broker: null,
    brokerEmail: null,
    sellerName: null,
    sellerEmail: null,
    ddFolderUrl: null,
    score: 70,
    notes: "2 warm leads waiting. UC2 offer needs packaging. One-pager not yet built.",
    nextAction: "Build GHL AI Growth Agency one-pager",
    nextActionDue: today,
    createdAt: now,
    updatedAt: now,
  },
  {
    name: "Empire Flippers Watch",
    type: "acquisition",
    status: "scouting",
    askPrice: null,
    targetPrice: null,
    mrr: null,
    broker: "Empire Flippers",
    brokerEmail: null,
    sellerName: null,
    sellerEmail: null,
    ddFolderUrl: null,
    score: null,
    notes: "Active deal sourcing. USA only. SaaS, content, e-commerce verticals.",
    nextAction: "Daily EF marketplace scan via EVA Morning Brief",
    nextActionDue: null,
    createdAt: now,
    updatedAt: now,
  },
];

for (const d of deals) {
  sqlite.prepare(`
    INSERT INTO deals (name, type, status, ask_price, target_price, mrr, broker, broker_email,
      seller_name, seller_email, dd_folder_url, score, notes, next_action, next_action_due,
      created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    d.name, d.type, d.status, d.askPrice, d.targetPrice, d.mrr, d.broker, d.brokerEmail,
    d.sellerName, d.sellerEmail, d.ddFolderUrl, d.score, d.notes, d.nextAction, d.nextActionDue,
    d.createdAt, d.updatedAt
  );
}

// ─── Cron Jobs ─────────────────────────────────────────────────────────────
const crons = [
  {
    cronId: "a71bbb3b",
    name: "Morning Brief",
    schedule: "31 12 * * *",
    scheduleHuman: "7:00 AM PDT daily",
    enabled: 1,
    lastRun: null,
    lastStatus: "success",
    nextRun: null,
    updatedAt: now,
  },
  {
    cronId: "76e251d4",
    name: "Morning Energy Check-In",
    schedule: "0 15 * * *",
    scheduleHuman: "8:00 AM PDT daily",
    enabled: 1,
    lastRun: null,
    lastStatus: "success",
    nextRun: null,
    updatedAt: now,
  },
  {
    cronId: "8e1e32a1",
    name: "Midday Reset",
    schedule: "0 19 * * *",
    scheduleHuman: "12:00 PM PDT daily",
    enabled: 1,
    lastRun: null,
    lastStatus: "success",
    nextRun: null,
    updatedAt: now,
  },
  {
    cronId: "48b07435",
    name: "Evening Wind-Down",
    schedule: "0 1 * * *",
    scheduleHuman: "6:00 PM PDT daily",
    enabled: 1,
    lastRun: null,
    lastStatus: "success",
    nextRun: null,
    updatedAt: now,
  },
];

for (const c of crons) {
  sqlite.prepare(`
    INSERT INTO cron_jobs (cron_id, name, schedule, schedule_human, enabled, last_run, last_status, next_run, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(c.cronId, c.name, c.schedule, c.scheduleHuman, c.enabled, c.lastRun, c.lastStatus, c.nextRun, c.updatedAt);
}

// ─── Notifications ──────────────────────────────────────────────────────────
const notifications = [
  {
    title: "EVA Morning Brief — Thu, Jun 4",
    body: "📅 Today: Storeys call 1:30pm (meet.google.com/smd-tyzh-pgq)\n⚡ batch.ai DD live — extract 2024 financials → send 12 DD questions to Shawn\n💰 HELOC $10K draw: DONE\n🎯 North Star: $10K/mo by June 25 · One Man Army",
    type: "brief",
    read: 0,
    createdAt: now,
  },
  {
    title: "batch.ai — Stripe Data Confirmed",
    body: "111 active subs · $5,528 MRR · 8.3% churn · $57K uncollectable · 0 new subs May 2026. DD verdict: NO at $179K. YES at $40–55K.",
    type: "deal_signal",
    read: 0,
    createdAt: now,
  },
  {
    title: "Swoop Financing — Outreach Sent",
    body: "Email sent to deals@swoopfunding.com for batch.ai down payment financing ($17,984 needed for 10%).",
    type: "system",
    read: 1,
    createdAt: now,
  },
];

for (const n of notifications) {
  sqlite.prepare(`
    INSERT INTO notifications (title, body, type, read, created_at)
    VALUES (?, ?, ?, ?, ?)
  `).run(n.title, n.body, n.type, n.read, n.createdAt);
}

// ─── Activities ──────────────────────────────────────────────────────────────
const activityData = [
  { title: "batch.ai — Extract 2024 Financials", description: "Open Drive PDFs → Google Docs → share link for EVA extraction", status: "in_progress", priority: "high", category: "acquisition" },
  { title: "Send 12 DD Questions to Shawn", description: "After 2024 financials reviewed, send via EF message thread", status: "planned", priority: "high", category: "acquisition" },
  { title: "EF Business Verification", description: "app.empireflippers.com → My Account → Verification", status: "planned", priority: "high", category: "acquisition" },
  { title: "Storeys Call — 1:30 PM", description: "meet.google.com/smd-tyzh-pgq", status: "in_progress", priority: "high", category: "rcfe" },
  { title: "HELOC $10K Draw", description: "Draw completed June 4", status: "completed", priority: "high", category: "finance" },
  { title: "EVA Panel Build", description: "Admin + User panel — React + Express + SQLite", status: "in_progress", priority: "high", category: "eva" },
  { title: "GHL AI Growth Agency One-Pager", description: "2 warm leads waiting. Package UC2 offer.", status: "planned", priority: "medium", category: "agency" },
  { title: "Check vineeth@mangotecusa.com for Shawn Stripe Invite", description: "Check spam folder", status: "planned", priority: "medium", category: "acquisition" },
];

sqlite.exec("DELETE FROM activities;");
for (const a of activityData) {
  sqlite.prepare(`
    INSERT INTO activities (title, description, status, priority, category, tags, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, '[]', ?, ?)
  `).run(a.title, a.description, a.status, a.priority, a.category, now, now);
}

// ─── Sample energy log ──────────────────────────────────────────────────────
sqlite.prepare(`
  INSERT INTO energy_logs (level, period, note, timestamp, date)
  VALUES (?, ?, ?, ?, ?)
`).run(4, "morning", "HELOC done, panel build day", now, today);

// ─── Sample agent tasks ─────────────────────────────────────────────────────
const agentTasks = [
  {
    taskName: "batch.ai 2024 Financials Extraction",
    taskType: "browser",
    costTier: "high",
    estimatedMinutes: 5,
    status: "killed",
    subagentId: "browser-attempt-3",
    result: "Browser disconnected at T+18min. Manual path required.",
    stalledAt: now,
    killedAt: now,
    completedAt: null,
    startedAt: now,
    updatedAt: now,
  },
  {
    taskName: "EVA Activity Board Deploy",
    taskType: "deploy",
    costTier: "low",
    estimatedMinutes: 3,
    status: "completed",
    subagentId: null,
    result: "Deployed to preview. Pushed to GitHub (8e85a1e).",
    stalledAt: null,
    killedAt: null,
    completedAt: now,
    startedAt: now,
    updatedAt: now,
  },
];

for (const t of agentTasks) {
  sqlite.prepare(`
    INSERT INTO agent_tasks (task_name, task_type, cost_tier, estimated_minutes, status, subagent_id,
      result, stalled_at, killed_at, completed_at, started_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    t.taskName, t.taskType, t.costTier, t.estimatedMinutes, t.status, t.subagentId,
    t.result, t.stalledAt, t.killedAt, t.completedAt, t.startedAt, t.updatedAt
  );
}

console.log("✅ EVA seed complete");
console.log(`   ${deals.length} deals · ${crons.length} cron jobs · ${notifications.length} notifications · ${agentTasks.length} agent tasks`);
sqlite.close();
