/**
 * EVA Panel Storage — sql.js (pure WASM, zero native binaries)
 * Persists to DATABASE_PATH (/tmp/eva.db on Vercel, data.db locally).
 * sql.js is synchronous and in-memory; we flush to disk after every write.
 */
import * as fs from "fs";
import * as path from "path";
import type {
  Activity, InsertActivity,
  Deal, InsertDeal,
  EnergyLog, InsertEnergyLog,
  Notification, InsertNotification,
  AgentTask, InsertAgentTask,
  CronJob, InsertCronJob,
  KpiMetric,
} from "@shared/schema";

// ── DB init ────────────────────────────────────────────────────────────────
import initSqlJs from "sql.js";
import { wasmBase64 } from "./wasm-binary";

let _db: any = null;
let _SQL: any = null;

const dbPath = path.resolve(process.env.DATABASE_PATH || "data.db");

async function ensureDb() {
  if (_db) return _db;
  if (!_SQL) {
    // Decode embedded base64 WASM — zero filesystem/network dependency.
    // Works in any serverless environment regardless of __dirname.
    const wasmBinary = Buffer.from(wasmBase64, "base64");
    _SQL = await initSqlJs({ wasmBinary });
  }
  if (fs.existsSync(dbPath)) {
    const buf = fs.readFileSync(dbPath);
    _db = new _SQL.Database(buf);
  } else {
    _db = new _SQL.Database();
  }
  _db.run("PRAGMA journal_mode=MEMORY;");
  createTables(_db);
  seedIfEmpty(_db);
  flush();
  return _db;
}

function flush() {
  if (!_db) return;
  try {
    const data: Uint8Array = _db.export();
    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(dbPath, Buffer.from(data));
  } catch (e) {
    console.error("EVA: flush failed", (e as Error).message);
  }
}

function run(sql: string, params: any[] = []) {
  if (!_db) throw new Error("DB not initialized — call ensureDb() first");
  _db.run(sql, params);
  flush();
}

function get<T = any>(sql: string, params: any[] = []): T | undefined {
  if (!_db) throw new Error("DB not initialized");
  const stmt = _db.prepare(sql);
  stmt.bind(params);
  if (stmt.step()) {
    const row = stmt.getAsObject();
    stmt.free();
    return row as T;
  }
  stmt.free();
  return undefined;
}

function all<T = any>(sql: string, params: any[] = []): T[] {
  if (!_db) throw new Error("DB not initialized");
  const res = _db.exec(sql, params);
  if (!res.length) return [];
  const { columns, values } = res[0];
  return values.map((row: any[]) => {
    const obj: any = {};
    columns.forEach((col: string, i: number) => { obj[col] = row[i]; });
    return obj as T;
  });
}

function lastInsertRowid(): number {
  const r = get<{ id: number }>("SELECT last_insert_rowid() as id");
  return r?.id ?? 0;
}

// ── DDL ────────────────────────────────────────────────────────────────────
function createTables(db: any) {
  db.run(`
    CREATE TABLE IF NOT EXISTS activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
      status TEXT NOT NULL DEFAULT 'planned', priority TEXT NOT NULL DEFAULT 'medium',
      category TEXT NOT NULL DEFAULT 'general', tags TEXT NOT NULL DEFAULT '[]',
      due_date TEXT, completed_at TEXT, archived_at TEXT,
      created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS deals (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      type TEXT NOT NULL DEFAULT 'acquisition', status TEXT NOT NULL DEFAULT 'scouting',
      ask_price TEXT, target_price TEXT, mrr TEXT, broker TEXT, broker_email TEXT,
      seller_name TEXT, seller_email TEXT, dd_folder_url TEXT, score INTEGER,
      notes TEXT, next_action TEXT, next_action_due TEXT, archived_at TEXT,
      created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS energy_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, level INTEGER NOT NULL, period TEXT NOT NULL,
      note TEXT, timestamp TEXT NOT NULL DEFAULT '', date TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
      type TEXT NOT NULL DEFAULT 'brief', read INTEGER NOT NULL DEFAULT 0,
      archived_at TEXT, created_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS agent_tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT NOT NULL, task_type TEXT NOT NULL,
      cost_tier TEXT NOT NULL DEFAULT 'medium', estimated_minutes INTEGER,
      status TEXT NOT NULL DEFAULT 'running', subagent_id TEXT, result TEXT,
      stalled_at TEXT, killed_at TEXT, completed_at TEXT,
      started_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS cron_jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, cron_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
      schedule TEXT NOT NULL, schedule_human TEXT, enabled INTEGER NOT NULL DEFAULT 1,
      last_run TEXT, last_status TEXT, next_run TEXT, updated_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS kpi_metrics (
      id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
      value TEXT NOT NULL DEFAULT '0', unit TEXT NOT NULL DEFAULT '$',
      category TEXT NOT NULL DEFAULT 'revenue', updated_at TEXT NOT NULL DEFAULT ''
    );
  `);
}

function seedIfEmpty(db: any) {
  const ts = now();

  const kpiCnt = (db.exec("SELECT COUNT(*) c FROM kpi_metrics")[0]?.values[0][0] ?? 0) as number;
  if (kpiCnt === 0) {
    const kpis: [string,string,string,string,string][] = [
      ["mrr","MRR","0","$","revenue"],
      ["revenue_total","Total Revenue","100","$","revenue"],
      ["paying_customers","Paying Customers","0","#","revenue"],
      ["hard_costs","Hard Costs","500","$","cost"],
      ["heloc_drawn","HELOC Drawn","10000","$","cost"],
      ["opportunity_cost","Opp. Cost (Time)","20000","$","cost"],
      ["hours_invested","Hours Invested","204","hrs","time"],
      ["days_since_start","Days Since Start","34","days","time"],
      ["target_mrr","Target MRR","10000","$","target"],
      ["target_date","Target Date","Jun 25","","target"],
      ["days_to_target","Days to Target","21","days","target"],
    ];
    for (const [key,label,value,unit,category] of kpis) {
      db.run("INSERT OR IGNORE INTO kpi_metrics (key,label,value,unit,category,updated_at) VALUES (?,?,?,?,?,?)",
        [key,label,value,unit,category,ts]);
    }
  }

  const cronCnt = (db.exec("SELECT COUNT(*) c FROM cron_jobs")[0]?.values[0][0] ?? 0) as number;
  if (cronCnt === 0) {
    db.run("INSERT OR IGNORE INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",["76e251d4","Morning Energy Check-In","0 15 * * *","8:00 AM PDT daily",ts]);
    db.run("INSERT OR IGNORE INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",["8e1e32a1","Midday Reset","0 19 * * *","12:00 PM PDT daily",ts]);
    db.run("INSERT OR IGNORE INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",["48b07435","Evening Wind-Down","0 1 * * *","6:00 PM PDT daily",ts]);
    db.run("INSERT OR IGNORE INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",["3e93306e","EVA Morning Brief","31 12 * * *","5:31 AM PDT daily",ts]);
  }
  // Always ensure Life Design cron exists (added post-initial seed)
  db.run("INSERT OR IGNORE INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",["aa11e49d","Life Design Check-In","0 2 * * *","7:00 PM PDT daily",ts]);

  const dealCnt = (db.exec("SELECT COUNT(*) c FROM deals")[0]?.values[0][0] ?? 0) as number;
  if (dealCnt === 0) {
    db.run(`INSERT INTO deals (name,type,status,ask_price,target_price,mrr,broker,broker_email,seller_name,seller_email,dd_folder_url,score,notes,next_action,next_action_due,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      ["batch.ai","acquisition","dd","$179,000","$40,000–$55,000","$5,528","Zachary Slater (EF)","zachary@empireflippers.com","Shawn Hawkins","shawnhawkins101@gmail.com","https://drive.google.com/drive/folders/1LqtzYXjiUs_jg3kXXbttikSLokJjoK7R",62,"111 subs, 8.3% churn, 2024 net $33K. Target $40-55K.","Send 12 DD questions to Shawn","2026-06-05",ts,ts]);
    db.run(`INSERT INTO deals (name,type,status,ask_price,target_price,notes,next_action,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)`,
      ["Mission Villa RCFE","rcfe","loi","TBD","TBD","HELOC $10K drawn. NOI $7,128/mo.","Confirm HELOC wired + term sheet",ts,ts]);
    db.run(`INSERT INTO deals (name,type,status,notes,next_action,created_at,updated_at) VALUES (?,?,?,?,?,?,?)`,
      ["GHL AI Growth Agency","agency","scouting","2 warm leads waiting. One-pager needed.","Draft GHL one-pager",ts,ts]);
  }

  const actCnt = (db.exec("SELECT COUNT(*) c FROM activities")[0]?.values[0][0] ?? 0) as number;
  if (actCnt === 0) {
    const acts: [string,string,string,string,string][] = [
      ["batch.ai DD — Send 12 Questions to Shawn","2024 financials extracted. Send DD questions now.","in_progress","critical","acquisition"],
      ["EF Business Verification — Mangotec LLC","app.empireflippers.com → My Account → Verification","in_progress","high","acquisition"],
      ["GHL AI Growth Agency One-Pager","2 warm leads waiting. Draft the offer.","planned","critical","revenue"],
      ["Signature Talk — Finalize Draft 1","EOD Friday June 5 — HARD DEADLINE. Send to Leadr.","planned","critical","outreach"],
      ["LinkedIn BRIEF Comment Monitoring","Reply 'BRIEF' comments with Calendly link","planned","high","outreach"],
      ["GLÖSSAI — Wire Stripe Checkout","Confirm checkout is live. Activate founding counter.","planned","high","revenue"],
      ["Eva Panel Regressions — Edit + Audit Trail","Add task edit button, audit trail, tags/due date","planned","medium","eva"],
      ["HELOC $10K Draw","Drawn June 4, 2026","completed","critical","finance"],
    ];
    for (const [title,desc,status,priority,category] of acts) {
      db.run("INSERT INTO activities (title,description,status,priority,category,tags,created_at,updated_at) VALUES (?,?,?,?,?,'[]',?,?)",
        [title,desc,status,priority,category,ts,ts]);
    }
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
const now = () => new Date().toISOString();
const today = () => new Date().toISOString().split("T")[0];

function toActivity(row: any): Activity {
  return { ...row, tags: JSON.parse(row.tags || "[]") };
}

// ── Storage API ────────────────────────────────────────────────────────────
// All methods are async to allow top-level await at call sites
export const storage = {
  async getAllActivities(): Promise<Activity[]> {
    await ensureDb();
    return all("SELECT * FROM activities WHERE archived_at IS NULL ORDER BY updated_at DESC").map(toActivity);
  },
  async createActivity(data: InsertActivity): Promise<Activity> {
    await ensureDb();
    const ts = now();
    run("INSERT INTO activities (title,description,status,priority,category,tags,due_date,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
      [data.title, data.description||null, data.status||"planned", data.priority||"medium", data.category||"general", JSON.stringify(data.tags||[]), data.dueDate||null, ts, ts]);
    return toActivity(get("SELECT * FROM activities WHERE id=?", [lastInsertRowid()])!);
  },
  async updateActivityStatus(id: number, status: string): Promise<Activity> {
    await ensureDb();
    const ts = now();
    if (status === "completed") {
      run("UPDATE activities SET status=?,completed_at=?,updated_at=? WHERE id=?", [status,ts,ts,id]);
    } else {
      run("UPDATE activities SET status=?,updated_at=? WHERE id=?", [status,ts,id]);
    }
    return toActivity(get("SELECT * FROM activities WHERE id=?", [id])!);
  },
  async markDone(id: number): Promise<Activity> { return this.updateActivityStatus(id,"completed"); },
  async updateActivity(id: number, data: Partial<InsertActivity>): Promise<Activity> {
    await ensureDb();
    const ts = now();
    const sets: string[] = ["updated_at=?"];
    const vals: any[] = [ts];
    if (data.title !== undefined) { sets.push("title=?"); vals.push(data.title); }
    if (data.description !== undefined) { sets.push("description=?"); vals.push(data.description); }
    if (data.status !== undefined) { sets.push("status=?"); vals.push(data.status); }
    if (data.priority !== undefined) { sets.push("priority=?"); vals.push(data.priority); }
    if (data.category !== undefined) { sets.push("category=?"); vals.push(data.category); }
    if (data.tags !== undefined) { sets.push("tags=?"); vals.push(JSON.stringify(data.tags)); }
    if (data.dueDate !== undefined) { sets.push("due_date=?"); vals.push(data.dueDate); }
    vals.push(id);
    run(`UPDATE activities SET ${sets.join(",")} WHERE id=?`, vals);
    return toActivity(get("SELECT * FROM activities WHERE id=?", [id])!);
  },
  async archiveActivity(id: number): Promise<Activity> {
    await ensureDb();
    const ts = now();
    run("UPDATE activities SET archived_at=?,updated_at=? WHERE id=?", [ts,ts,id]);
    return toActivity(get("SELECT * FROM activities WHERE id=?", [id])!);
  },

  async getAllDeals(): Promise<Deal[]> {
    await ensureDb();
    return all("SELECT * FROM deals WHERE archived_at IS NULL ORDER BY updated_at DESC");
  },
  async createDeal(data: InsertDeal): Promise<Deal> {
    await ensureDb();
    const ts = now();
    run(`INSERT INTO deals (name,type,status,ask_price,target_price,mrr,broker,broker_email,seller_name,seller_email,dd_folder_url,score,notes,next_action,next_action_due,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [data.name, data.type||"acquisition", data.status||"scouting", data.askPrice||null, data.targetPrice||null, data.mrr||null, data.broker||null, data.brokerEmail||null, data.sellerName||null, data.sellerEmail||null, data.ddFolderUrl||null, data.score||null, data.notes||null, data.nextAction||null, data.nextActionDue||null, ts, ts]);
    return get("SELECT * FROM deals WHERE id=?", [lastInsertRowid()])!;
  },
  async updateDeal(id: number, data: Partial<InsertDeal>): Promise<Deal> {
    await ensureDb();
    const ts = now();
    const sets: string[] = ["updated_at=?"];
    const vals: any[] = [ts];
    if (data.name !== undefined) { sets.push("name=?"); vals.push(data.name); }
    if (data.status !== undefined) { sets.push("status=?"); vals.push(data.status); }
    if (data.notes !== undefined) { sets.push("notes=?"); vals.push(data.notes); }
    if (data.nextAction !== undefined) { sets.push("next_action=?"); vals.push(data.nextAction); }
    if (data.nextActionDue !== undefined) { sets.push("next_action_due=?"); vals.push(data.nextActionDue); }
    if (data.score !== undefined) { sets.push("score=?"); vals.push(data.score); }
    if (data.askPrice !== undefined) { sets.push("ask_price=?"); vals.push(data.askPrice); }
    if (data.targetPrice !== undefined) { sets.push("target_price=?"); vals.push(data.targetPrice); }
    vals.push(id);
    run(`UPDATE deals SET ${sets.join(",")} WHERE id=?`, vals);
    return get("SELECT * FROM deals WHERE id=?", [id])!;
  },

  async getEnergyLogs(limit = 30): Promise<EnergyLog[]> {
    await ensureDb();
    return all("SELECT * FROM energy_logs ORDER BY timestamp DESC LIMIT ?", [limit]);
  },
  async getTodayEnergy(): Promise<EnergyLog[]> {
    await ensureDb();
    return all("SELECT * FROM energy_logs WHERE date=? ORDER BY timestamp DESC", [today()]);
  },
  async createEnergyLog(data: InsertEnergyLog): Promise<EnergyLog> {
    await ensureDb();
    const ts = now();
    run("INSERT INTO energy_logs (level,period,note,timestamp,date) VALUES (?,?,?,?,?)",
      [data.level, data.period, data.note||null, ts, today()]);
    return get("SELECT * FROM energy_logs WHERE id=?", [lastInsertRowid()])!;
  },

  async getNotifications(limit = 50): Promise<Notification[]> {
    await ensureDb();
    return all("SELECT * FROM notifications WHERE archived_at IS NULL ORDER BY created_at DESC LIMIT ?", [limit]);
  },
  async getUnreadCount(): Promise<number> {
    await ensureDb();
    return ((_db.exec("SELECT COUNT(*) c FROM notifications WHERE read=0 AND archived_at IS NULL")[0]?.values[0][0]) ?? 0) as number;
  },
  async createNotification(data: InsertNotification): Promise<Notification> {
    await ensureDb();
    run("INSERT INTO notifications (title,body,type,read,created_at) VALUES (?,?,?,0,?)",
      [data.title, data.body, data.type||"brief", now()]);
    return get("SELECT * FROM notifications WHERE id=?", [lastInsertRowid()])!;
  },
  async markNotificationRead(id: number): Promise<void> {
    await ensureDb();
    run("UPDATE notifications SET read=1 WHERE id=?", [id]);
  },
  async markAllRead(): Promise<void> {
    await ensureDb();
    run("UPDATE notifications SET read=1");
  },

  async getAgentTasks(limit = 50): Promise<AgentTask[]> {
    await ensureDb();
    return all("SELECT * FROM agent_tasks ORDER BY started_at DESC LIMIT ?", [limit]);
  },
  async getRunningTasks(): Promise<AgentTask[]> {
    await ensureDb();
    return all("SELECT * FROM agent_tasks WHERE status='running'");
  },
  async createAgentTask(data: InsertAgentTask): Promise<AgentTask> {
    await ensureDb();
    const ts = now();
    run("INSERT INTO agent_tasks (task_name,task_type,cost_tier,estimated_minutes,status,started_at,updated_at) VALUES (?,?,?,?,'running',?,?)",
      [data.taskName, data.taskType, data.costTier||"medium", data.estimatedMinutes||null, ts, ts]);
    return get("SELECT * FROM agent_tasks WHERE id=?", [lastInsertRowid()])!;
  },
  async updateAgentTask(id: number, status: string, result?: string): Promise<AgentTask> {
    await ensureDb();
    const ts = now();
    const sets = ["status=?","updated_at=?"];
    const vals: any[] = [status,ts];
    if (status==="completed") { sets.push("completed_at=?"); vals.push(ts); }
    if (status==="stalled"||status==="killed") { sets.push("stalled_at=?"); vals.push(ts); }
    if (result) { sets.push("result=?"); vals.push(result); }
    vals.push(id);
    run(`UPDATE agent_tasks SET ${sets.join(",")} WHERE id=?`, vals);
    return get("SELECT * FROM agent_tasks WHERE id=?", [id])!;
  },
  async markStalledTasks(thresholdMin = 5): Promise<AgentTask[]> {
    const running = await this.getRunningTasks();
    const cutoff = new Date(Date.now() - thresholdMin * 60000);
    return Promise.all(running.filter(t => new Date(t.startedAt) < cutoff).map(t => this.updateAgentTask(t.id,"stalled",`Auto-flagged: >${thresholdMin}min`)));
  },

  async getCronJobs(): Promise<CronJob[]> {
    await ensureDb();
    return all("SELECT * FROM cron_jobs ORDER BY name");
  },
  async toggleCronJob(id: number, enabled: boolean): Promise<CronJob> {
    await ensureDb();
    run("UPDATE cron_jobs SET enabled=?,updated_at=? WHERE id=?", [enabled?1:0, now(), id]);
    return get("SELECT * FROM cron_jobs WHERE id=?", [id])!;
  },
  async upsertCronJob(data: InsertCronJob): Promise<CronJob> {
    await ensureDb();
    const ts = now();
    const existing = get("SELECT * FROM cron_jobs WHERE cron_id=?", [data.cronId]);
    if (existing) {
      run("UPDATE cron_jobs SET name=?,schedule=?,schedule_human=?,updated_at=? WHERE cron_id=?",
        [data.name, data.schedule, data.scheduleHuman||null, ts, data.cronId]);
    } else {
      run("INSERT INTO cron_jobs (cron_id,name,schedule,schedule_human,enabled,updated_at) VALUES (?,?,?,?,1,?)",
        [data.cronId, data.name, data.schedule, data.scheduleHuman||null, ts]);
    }
    return get("SELECT * FROM cron_jobs WHERE cron_id=?", [data.cronId])!;
  },

  async getAllKpi(): Promise<KpiMetric[]> {
    await ensureDb();
    return all("SELECT * FROM kpi_metrics ORDER BY category, key");
  },
  async upsertKpi(key: string, value: string, label?: string, unit?: string, category?: string): Promise<KpiMetric> {
    await ensureDb();
    const ts = now();
    const existing = get("SELECT * FROM kpi_metrics WHERE key=?", [key]);
    if (existing) {
      const sets = ["value=?","updated_at=?"];
      const vals: any[] = [value,ts];
      if (label) { sets.push("label=?"); vals.push(label); }
      if (unit) { sets.push("unit=?"); vals.push(unit); }
      if (category) { sets.push("category=?"); vals.push(category); }
      vals.push(key);
      run(`UPDATE kpi_metrics SET ${sets.join(",")} WHERE key=?`, vals);
    } else {
      run("INSERT OR IGNORE INTO kpi_metrics (key,label,value,unit,category,updated_at) VALUES (?,?,?,?,?,?)",
        [key, label||key, value, unit||"$", category||"revenue", ts]);
    }
    return get("SELECT * FROM kpi_metrics WHERE key=?", [key])!;
  },

  async getStats(): Promise<Record<string,number>> {
    await ensureDb();
    const acts = await this.getAllActivities();
    const dealList = await this.getAllDeals();
    return {
      tasks_total: acts.length,
      tasks_in_progress: acts.filter(a => a.status==="in_progress").length,
      tasks_completed: acts.filter(a => a.status==="completed").length,
      tasks_planned: acts.filter(a => a.status==="planned").length,
      deals_active: dealList.filter(d => ["loi","dd","negotiation"].includes(d.status)).length,
      deals_total: dealList.length,
      unread_notifications: await this.getUnreadCount(),
      agents_running: (await this.getRunningTasks()).length,
    };
  },
};
