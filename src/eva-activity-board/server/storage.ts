/**
 * EVA Activity Board — storage layer
 *
 * Pure-JS in-memory store with best-effort JSON persistence. Contains ZERO
 * native binaries (no better-sqlite3) so it builds and boots cleanly on
 * Vercel's serverless runtime.
 *
 * Persistence: on each write we flush the full dataset to DATABASE_PATH as
 * JSON. On Vercel the filesystem is read-only except /tmp, so in production we
 * default to /tmp (writable but ephemeral — data resets on cold start, which is
 * expected/acceptable for this dashboard). The flush is wrapped in try/catch so
 * a read-only filesystem can never crash a request. Locally it persists to
 * ./data.json across restarts.
 */
import * as fs from "fs";
import type {
  Activity,
  InsertActivity,
  ActivityEvent,
  InsertActivityEvent,
  EnergyLog,
  InsertEnergyLog,
  AgentTask,
  InsertAgentTask,
} from "../shared/schema";

// ── Persistence path ─────────────────────────────────────────────────────────
const DB_PATH =
  process.env.DATABASE_PATH ||
  (process.env.NODE_ENV === "production" ? "/tmp/eva-activity-board.json" : "data.json");

// ── In-memory dataset ─────────────────────────────────────────────────────────
interface DataSet {
  activities: Activity[];
  activityEvents: ActivityEvent[];
  energyLogs: EnergyLog[];
  agentTasks: AgentTask[];
  counters: { activity: number; event: number; energy: number; agentTask: number };
}

const data: DataSet = {
  activities: [],
  activityEvents: [],
  energyLogs: [],
  agentTasks: [],
  counters: { activity: 0, event: 0, energy: 0, agentTask: 0 },
};

function now(): string {
  return new Date().toISOString();
}

function today(): string {
  return new Date().toISOString().split("T")[0];
}

function load(): void {
  try {
    if (!fs.existsSync(DB_PATH)) return;
    const parsed = JSON.parse(fs.readFileSync(DB_PATH, "utf-8"));
    data.activities = parsed.activities ?? [];
    data.activityEvents = parsed.activityEvents ?? [];
    data.energyLogs = parsed.energyLogs ?? [];
    data.agentTasks = parsed.agentTasks ?? [];
    data.counters = parsed.counters ?? {
      activity: data.activities.reduce((m, a) => Math.max(m, a.id), 0),
      event: data.activityEvents.reduce((m, e) => Math.max(m, e.id), 0),
      energy: data.energyLogs.reduce((m, e) => Math.max(m, e.id), 0),
      agentTask: data.agentTasks.reduce((m, t) => Math.max(m, t.id), 0),
    };
  } catch (e) {
    console.error("EVA: failed to load dataset —", (e as Error).message);
  }
}

function save(): void {
  try {
    fs.writeFileSync(DB_PATH, JSON.stringify(data));
  } catch (e) {
    // Read-only filesystem (e.g. Vercel outside /tmp) — degrade to in-memory only.
    console.error("EVA: persist skipped —", (e as Error).message);
  }
}

// ── Lazy initialization ────────────────────────────────────────────────────────
// CRITICAL for Vercel cold start: perform NO filesystem I/O at module load. All
// disk hydration + seeding is deferred to the first storage access (behind this
// guard) so that importing this module can never touch the filesystem, run
// JSON.parse, or otherwise throw during serverless module evaluation. Even though
// load()/save() are individually try/catch-wrapped, keeping the entire I/O path
// out of module-init eliminates the whole class of "throws before the handler
// runs" cold-start crashes.
let initialized = false;
function ensureReady(): void {
  if (initialized) return;
  initialized = true; // set first so seedIfEmpty()'s writes don't re-enter here
  try {
    load();
    seedIfEmpty();
  } catch (e) {
    console.error("EVA: storage init failed —", (e as Error).message);
  }
}

// ── Storage interface ─────────────────────────────────────────────────────────
export interface IStorage {
  // Activities
  getAllActivities(): Activity[];
  getActivitiesByStatus(status: string): Activity[];
  createActivity(data: InsertActivity): Activity;
  updateActivityStatus(id: number, status: string, note?: string): Activity;
  markActivityDone(id: number): Activity;
  updateActivity(id: number, data: Partial<InsertActivity>): Activity;
  archiveActivity(id: number): Activity;

  // Activity Events
  getEventsForActivity(activityId: number): ActivityEvent[];
  getAllEvents(limit?: number): ActivityEvent[];
  createEvent(data: InsertActivityEvent): ActivityEvent;

  // Agent Tasks (watchdog)
  createAgentTask(data: InsertAgentTask): AgentTask;
  getAgentTasks(limit?: number): AgentTask[];
  getRunningAgentTasks(): AgentTask[];
  updateAgentTaskStatus(id: number, status: string, result?: string): AgentTask;
  markStalledTasks(thresholdMinutes?: number): AgentTask[];

  // Energy Logs
  getEnergyLogs(limit?: number): EnergyLog[];
  getEnergyLogsByDate(date: string): EnergyLog[];
  createEnergyLog(data: InsertEnergyLog): EnergyLog;
  getLatestEnergyLogs(days?: number): EnergyLog[];
}

export class MemoryStorage implements IStorage {
  // ── Activities ──────────────────────────────────────────────────────────────
  getAllActivities(): Activity[] {
    ensureReady();
    return [...data.activities].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  getActivitiesByStatus(status: string): Activity[] {
    return this.getAllActivities().filter((a) => a.status === status);
  }

  createActivity(input: InsertActivity): Activity {
    ensureReady();
    const ts = now();
    const activity: Activity = {
      id: ++data.counters.activity,
      title: input.title,
      description: input.description ?? null,
      status: input.status ?? "planned",
      priority: input.priority ?? "medium",
      category: input.category ?? "general",
      tags: input.tags ?? "[]",
      dueDate: input.dueDate ?? null,
      completedAt: null,
      archivedAt: null,
      createdAt: ts,
      updatedAt: ts,
    };
    data.activities.push(activity);
    this._logEvent(activity.id, "created", null, activity.status, "Created via API");
    save();
    return activity;
  }

  updateActivityStatus(id: number, status: string, note?: string): Activity {
    ensureReady();
    const existing = data.activities.find((a) => a.id === id);
    if (!existing) throw new Error(`Activity ${id} not found`);
    const ts = now();
    const fromStatus = existing.status;
    existing.status = status;
    existing.updatedAt = ts;
    if (status === "completed") existing.completedAt = ts;
    this._logEvent(id, "status_changed", fromStatus, status, note ?? null);
    save();
    return existing;
  }

  markActivityDone(id: number): Activity {
    ensureReady();
    const existing = data.activities.find((a) => a.id === id);
    if (!existing) throw new Error(`Activity ${id} not found`);
    const ts = now();
    const fromStatus = existing.status;
    existing.status = "completed";
    existing.completedAt = ts;
    existing.updatedAt = ts;
    this._logEvent(id, "done_clicked", fromStatus, "completed", "Marked done via Done button");
    save();
    return existing;
  }

  updateActivity(id: number, input: Partial<InsertActivity>): Activity {
    ensureReady();
    const existing = data.activities.find((a) => a.id === id);
    if (!existing) throw new Error(`Activity ${id} not found`);
    const ts = now();
    if (input.title !== undefined) existing.title = input.title;
    if (input.description !== undefined) existing.description = input.description ?? null;
    if (input.status !== undefined) existing.status = input.status;
    if (input.priority !== undefined) existing.priority = input.priority;
    if (input.category !== undefined) existing.category = input.category;
    if (input.tags !== undefined) existing.tags = input.tags ?? "[]";
    if (input.dueDate !== undefined) existing.dueDate = input.dueDate ?? null;
    existing.updatedAt = ts;
    this._logEvent(id, "edited", null, null, `Updated: ${Object.keys(input).join(", ")}`);
    save();
    return existing;
  }

  archiveActivity(id: number): Activity {
    ensureReady();
    const existing = data.activities.find((a) => a.id === id);
    if (!existing) throw new Error(`Activity ${id} not found`);
    const ts = now();
    const fromStatus = existing.status;
    existing.archivedAt = ts;
    existing.updatedAt = ts;
    this._logEvent(id, "archived", fromStatus, null, "Soft archived — data preserved for ML");
    save();
    return existing;
  }

  // ── Activity Events ─────────────────────────────────────────────────────────
  private _logEvent(
    activityId: number,
    eventType: string,
    fromStatus: string | null,
    toStatus: string | null,
    note: string | null,
  ): ActivityEvent {
    const event: ActivityEvent = {
      id: ++data.counters.event,
      activityId,
      eventType,
      fromStatus,
      toStatus,
      note,
      timestamp: now(),
    };
    data.activityEvents.push(event);
    return event;
  }

  getEventsForActivity(activityId: number): ActivityEvent[] {
    ensureReady();
    return data.activityEvents
      .filter((e) => e.activityId === activityId)
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  }

  getAllEvents(limit = 100): ActivityEvent[] {
    ensureReady();
    return [...data.activityEvents]
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, limit);
  }

  createEvent(input: InsertActivityEvent): ActivityEvent {
    ensureReady();
    const event = this._logEvent(
      input.activityId,
      input.eventType,
      input.fromStatus ?? null,
      input.toStatus ?? null,
      input.note ?? null,
    );
    save();
    return event;
  }

  // ── Energy Logs ───────────────────────────────────────────────────────────────
  getEnergyLogs(limit = 30): EnergyLog[] {
    ensureReady();
    return [...data.energyLogs]
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, limit);
  }

  getEnergyLogsByDate(date: string): EnergyLog[] {
    ensureReady();
    return data.energyLogs
      .filter((e) => e.date === date)
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  }

  createEnergyLog(input: InsertEnergyLog): EnergyLog {
    ensureReady();
    const ts = now();
    const log: EnergyLog = {
      id: ++data.counters.energy,
      level: input.level,
      period: input.period,
      note: input.note ?? null,
      timestamp: ts,
      date: today(),
    };
    data.energyLogs.push(log);
    save();
    return log;
  }

  getLatestEnergyLogs(days = 7): EnergyLog[] {
    return this.getEnergyLogs(days * 3);
  }

  // ── Agent Tasks ─────────────────────────────────────────────────────────────
  createAgentTask(input: InsertAgentTask): AgentTask {
    ensureReady();
    const ts = now();
    const task: AgentTask = {
      id: ++data.counters.agentTask,
      taskName: input.taskName,
      taskType: input.taskType,
      estimatedMinutes: input.estimatedMinutes ?? null,
      costTier: input.costTier ?? "medium",
      status: input.status ?? "running",
      subagentId: input.subagentId ?? null,
      result: input.result ?? null,
      stalledAt: null,
      killedAt: null,
      completedAt: null,
      startedAt: ts,
      updatedAt: ts,
    };
    data.agentTasks.push(task);
    save();
    return task;
  }

  getAgentTasks(limit = 50): AgentTask[] {
    ensureReady();
    return [...data.agentTasks]
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
      .slice(0, limit);
  }

  getRunningAgentTasks(): AgentTask[] {
    ensureReady();
    return data.agentTasks.filter((t) => t.status === "running");
  }

  updateAgentTaskStatus(id: number, status: string, result?: string): AgentTask {
    ensureReady();
    const existing = data.agentTasks.find((t) => t.id === id);
    if (!existing) throw new Error(`Agent task ${id} not found`);
    const ts = now();
    existing.status = status;
    existing.updatedAt = ts;
    if (status === "completed") existing.completedAt = ts;
    if (status === "killed" || status === "stalled") existing.stalledAt = ts;
    if (result) existing.result = result;
    save();
    return existing;
  }

  markStalledTasks(thresholdMinutes = 5): AgentTask[] {
    const cutoff = new Date(Date.now() - thresholdMinutes * 60 * 1000);
    const stalled: AgentTask[] = [];
    for (const task of this.getRunningAgentTasks()) {
      if (new Date(task.startedAt) < cutoff) {
        stalled.push(
          this.updateAgentTaskStatus(
            task.id,
            "stalled",
            `Auto-flagged: running for >${thresholdMinutes}min with no result`,
          ),
        );
      }
    }
    return stalled;
  }
}

export const storage = new MemoryStorage();

// ── Seed (initial demo/session data) ────────────────────────────────────────────
// Kept here so a fresh (ephemeral) Vercel instance boots with the board populated.
interface SeedActivity {
  title: string;
  description: string;
  status: string;
  priority: string;
  category: string;
  tags: string;
  completedAt?: string;
}

const SEED_ACTIVITIES: SeedActivity[] = [
  {
    title: "batch.ai Due Diligence — 2024 Financials Extraction",
    description:
      "Extract BATCHAILLC + HAWKINSPNGINC 2024 Form 1120S, QB 2021, Assets Included.docx from seller DD folder",
    status: "in_progress",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "dd", "financials"]),
  },
  {
    title: "EVA Activity Board Build + Deploy",
    description:
      "Jira/Monday-style kanban with energy log, task states, timestamps, done buttons. Deploy to eva.mangotec.ai",
    status: "in_progress",
    priority: "high",
    category: "eva_build",
    tags: JSON.stringify(["eva", "ui", "kanban"]),
  },
  {
    title: "EF Business Verification — Mangotec LLC",
    description:
      "app.empireflippers.com → My Account → Verification → Business Ownership. Upload Mangotec LLC proof",
    status: "in_progress",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "ef", "verification"]),
  },
  {
    title: "Send Shawn Questions (12 prepared) — After 2024 Returns Reviewed",
    description:
      "12 DD questions ready. Await 2024 tax return data before sending. Key: sub count at listing, zero new subs May, churn cause, QB upload request",
    status: "planned",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "dd", "shawn"]),
  },
  {
    title: "GHL AI Growth Agency One-Pager",
    description:
      "Build one-pager for aigrowthagency.org DFY offer. Tony's retainer $1,500/mo. Critical path to $10K by June 25",
    status: "planned",
    priority: "critical",
    category: "revenue",
    tags: JSON.stringify(["ghl", "agency", "revenue"]),
  },
  {
    title: "Check Stripe Invite from Shawn (vineeth@mangotecusa.com spam folder)",
    description:
      "Shawn sent Stripe access invite. Check spam. Needed to verify live subscriber data",
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
    description:
      "Schema designed, never deployed. Run docker compose up -d from /Users/vineetravi/Eva/ops/docker/. Docker Desktop must be running first",
    status: "planned",
    priority: "high",
    category: "eva_build",
    tags: JSON.stringify(["eva", "db", "infrastructure"]),
  },
  {
    title: "Screenpipe Install + Activity Logger Wire-Up",
    description:
      "Screenpipe not installed. Activity logger code written but no DB write layer. Install screenpipe, wire to EVA DB for audio/video/event logging",
    status: "planned",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "screenpipe", "activity-logger"]),
  },
  {
    title: "Swoop Financing — Await Response from deals@swoopfunding.com",
    description:
      "Email sent June 4. Seeking financing for batch.ai $179K acquisition. Down payment needed: $17,984 (10%)",
    status: "planned",
    priority: "medium",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "financing", "swoop"]),
  },
  {
    title: "Apollo + instantly.ai Outreach — AI Growth Agency",
    description:
      "Apollo outreach running. instantly.ai warm inboxed. Check reply rates, iterate on copy",
    status: "planned",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["agency", "outreach", "apollo"]),
  },
  {
    title: "EVA Angels Architecture — Remove AI Employee Language from All Copy",
    description:
      "Locked: EVA uses ANGELS (outcome-based) NOT Employees (role-based). Update all docs, landing page, LinkedIn copy",
    status: "planned",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "angels", "copy"]),
  },
  {
    title: "Provisional Patents — Final Filing (needs $$$)",
    description:
      "Provisional patents filed under Mangotec. Final filing requires funds — watch for Swoop approval or HELOC draw",
    status: "planned",
    priority: "low",
    category: "operations",
    tags: JSON.stringify(["mangotec", "ip", "patents"]),
  },
  {
    title: "HELOC $10K Draw",
    description: "RCFE Healthcare HELOC draw completed June 4",
    status: "completed",
    priority: "critical",
    category: "operations",
    tags: JSON.stringify(["heloc", "rcfe", "funding"]),
    completedAt: new Date("2026-06-04T09:00:00").toISOString(),
  },
  {
    title: "Swoop Financing Email Sent",
    description: "Sent to deals@swoopfunding.com — batch.ai acquisition financing request",
    status: "completed",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "swoop", "financing"]),
    completedAt: new Date("2026-06-04T10:00:00").toISOString(),
  },
  {
    title: "batch.ai LOI Signed",
    description: "LOI signed June 3. DD live with Veronica Ochoa (EF). Broker: Zachary Slater",
    status: "completed",
    priority: "critical",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "loi", "ef"]),
    completedAt: new Date("2026-06-03T12:00:00").toISOString(),
  },
  {
    title: "batch.ai Stripe Data Extraction",
    description:
      "Extracted: 111 active subs (NOT 160), MRR $5,528, 8.3% monthly churn, $57K uncollectable invoices, zero new subs May 2026",
    status: "completed",
    priority: "high",
    category: "acquisition",
    tags: JSON.stringify(["batchai", "stripe", "dd"]),
    completedAt: new Date("2026-06-04T09:30:00").toISOString(),
  },
  {
    title: "EVA Activity Board Spec → GitHub Backlog",
    description: "Full spec committed to Mangotec333/Eva repo. Commit: caeddd3",
    status: "completed",
    priority: "medium",
    category: "eva_build",
    tags: JSON.stringify(["eva", "github", "spec"]),
    completedAt: new Date("2026-06-04T10:30:00").toISOString(),
  },
  {
    title: "AI Employee Blueprint Infographic — LinkedIn",
    description:
      "1200x1600px infographic built and shared. Angels vs AI Employees distinction locked",
    status: "completed",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["eva", "linkedin", "content"]),
    completedAt: new Date("2026-06-04T10:00:00").toISOString(),
  },
  {
    title: "Tatiana AI Workroom — Partnership / Funnel Strategy",
    description:
      "$47/mo, 19 members. Her DIY model → EVA DFY model. Explore: affiliate, joint webinar, or cross-promotion. Her members = future $1,500/mo clients",
    status: "parking_lot",
    priority: "medium",
    category: "outreach",
    tags: JSON.stringify(["tatiana", "partnership", "agency"]),
  },
  {
    title: "Jay Prasad — GSA/Federal Projects",
    description:
      "Deferred payment arrangement. BWConsultants grants for POCs — needs $5K deposit. EVA as proof of concept",
    status: "parking_lot",
    priority: "low",
    category: "revenue",
    tags: JSON.stringify(["jay", "federal", "mangotec"]),
  },
  {
    title: "PurePlate + Glossai Shopify Stores",
    description:
      "Dropshipping: PurePlate (kitchenware) + Glossai (organic skincare). Testing mode. Build-in-public strategy active",
    status: "parking_lot",
    priority: "low",
    category: "revenue",
    tags: JSON.stringify(["shopify", "dropshipping", "ecommerce"]),
  },
  {
    title: "Signature Talk — Finalize Draft",
    description:
      "Raw input collected this session and appended to Google Doc worksheet. Was: finalize Sat/Sun May 30-31 — slipped. Now: TBD",
    status: "parking_lot",
    priority: "low",
    category: "outreach",
    tags: JSON.stringify(["signature-talk", "linkedin", "content"]),
  },
];

export function seedIfEmpty(): void {
  if (data.activities.length > 0) return;
  for (const t of SEED_ACTIVITIES) {
    const created = storage.createActivity({
      title: t.title,
      description: t.description,
      status: t.status,
      priority: t.priority,
      category: t.category,
      tags: t.tags,
    });
    if (t.completedAt) {
      const row = data.activities.find((a) => a.id === created.id)!;
      row.completedAt = t.completedAt;
      row.createdAt = t.completedAt;
      row.updatedAt = t.completedAt;
    }
  }
  save();
}

// NOTE: initialization (disk load + seed) is intentionally NOT run at module
// load. It happens lazily on first storage access via ensureReady() — see the
// guard above. This keeps the serverless cold-start import side-effect-free.
