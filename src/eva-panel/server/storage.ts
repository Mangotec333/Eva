import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc, and } from "drizzle-orm";
import {
  activities, deals, energyLogs, notifications, agentTasks, cronJobs,
  type Activity, type InsertActivity,
  type Deal, type InsertDeal,
  type EnergyLog, type InsertEnergyLog,
  type Notification, type InsertNotification,
  type AgentTask, type InsertAgentTask,
  type CronJob, type InsertCronJob,
} from "@shared/schema";

const dbPath = process.env.DATABASE_PATH || "data.db";
const sqlite = new Database(dbPath);
const db = drizzle(sqlite);

sqlite.exec(`
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
    id INTEGER PRIMARY KEY AUTOINCREMENT, cron_id TEXT NOT NULL, name TEXT NOT NULL,
    schedule TEXT NOT NULL, schedule_human TEXT, enabled INTEGER NOT NULL DEFAULT 1,
    last_run TEXT, last_status TEXT, next_run TEXT, updated_at TEXT NOT NULL DEFAULT ''
  );
`);

const now = () => new Date().toISOString();
const today = () => new Date().toISOString().split("T")[0];

export interface IStorage {
  // Activities
  getAllActivities(): Activity[];
  createActivity(data: InsertActivity): Activity;
  updateActivityStatus(id: number, status: string): Activity;
  markDone(id: number): Activity;
  updateActivity(id: number, data: Partial<InsertActivity>): Activity;
  archiveActivity(id: number): Activity;
  // Deals
  getAllDeals(): Deal[];
  createDeal(data: InsertDeal): Deal;
  updateDeal(id: number, data: Partial<InsertDeal>): Deal;
  // Energy
  getEnergyLogs(limit?: number): EnergyLog[];
  getTodayEnergy(): EnergyLog[];
  createEnergyLog(data: InsertEnergyLog): EnergyLog;
  // Notifications
  getNotifications(limit?: number): Notification[];
  getUnreadCount(): number;
  createNotification(data: InsertNotification): Notification;
  markNotificationRead(id: number): void;
  markAllRead(): void;
  // Agent Tasks (admin)
  getAgentTasks(limit?: number): AgentTask[];
  getRunningTasks(): AgentTask[];
  createAgentTask(data: InsertAgentTask): AgentTask;
  updateAgentTask(id: number, status: string, result?: string): AgentTask;
  markStalledTasks(thresholdMin?: number): AgentTask[];
  // Crons (admin)
  getCronJobs(): CronJob[];
  upsertCronJob(data: InsertCronJob): CronJob;
  toggleCronJob(id: number, enabled: boolean): CronJob;
  // Stats
  getStats(): Record<string, number>;
}

export class SqliteStorage implements IStorage {
  getAllActivities() { return db.select().from(activities).orderBy(desc(activities.updatedAt)).all().filter(a => !a.archivedAt); }
  createActivity(data: InsertActivity) { const ts = now(); return db.insert(activities).values({ ...data, createdAt: ts, updatedAt: ts }).returning().get(); }
  updateActivityStatus(id: number, status: string) {
    const ts = now();
    const updates: Record<string, unknown> = { status, updatedAt: ts };
    if (status === "completed") updates.completedAt = ts;
    return db.update(activities).set(updates).where(eq(activities.id, id)).returning().get();
  }
  markDone(id: number) { return this.updateActivityStatus(id, "completed"); }
  updateActivity(id: number, data: Partial<InsertActivity>) { return db.update(activities).set({ ...data, updatedAt: now() }).where(eq(activities.id, id)).returning().get(); }
  archiveActivity(id: number) { return db.update(activities).set({ archivedAt: now(), updatedAt: now() }).where(eq(activities.id, id)).returning().get(); }

  getAllDeals() { return db.select().from(deals).orderBy(desc(deals.updatedAt)).all().filter(d => !d.archivedAt); }
  createDeal(data: InsertDeal) { const ts = now(); return db.insert(deals).values({ ...data, createdAt: ts, updatedAt: ts }).returning().get(); }
  updateDeal(id: number, data: Partial<InsertDeal>) { return db.update(deals).set({ ...data, updatedAt: now() }).where(eq(deals.id, id)).returning().get(); }

  getEnergyLogs(limit = 30) { return db.select().from(energyLogs).orderBy(desc(energyLogs.timestamp)).limit(limit).all(); }
  getTodayEnergy() { return db.select().from(energyLogs).where(eq(energyLogs.date, today())).orderBy(desc(energyLogs.timestamp)).all(); }
  createEnergyLog(data: InsertEnergyLog) { const ts = now(); return db.insert(energyLogs).values({ ...data, timestamp: ts, date: today() }).returning().get(); }

  getNotifications(limit = 50) { return db.select().from(notifications).orderBy(desc(notifications.createdAt)).limit(limit).all().filter(n => !n.archivedAt); }
  getUnreadCount() { return db.select().from(notifications).all().filter(n => !n.read && !n.archivedAt).length; }
  createNotification(data: InsertNotification) { return db.insert(notifications).values({ ...data, createdAt: now() }).returning().get(); }
  markNotificationRead(id: number) { db.update(notifications).set({ read: 1 }).where(eq(notifications.id, id)).run(); }
  markAllRead() { db.update(notifications).set({ read: 1 }).run(); }

  getAgentTasks(limit = 50) { return db.select().from(agentTasks).orderBy(desc(agentTasks.startedAt)).limit(limit).all(); }
  getRunningTasks() { return db.select().from(agentTasks).where(eq(agentTasks.status, "running")).all(); }
  createAgentTask(data: InsertAgentTask) { const ts = now(); return db.insert(agentTasks).values({ ...data, startedAt: ts, updatedAt: ts }).returning().get(); }
  updateAgentTask(id: number, status: string, result?: string) {
    const ts = now();
    const u: Record<string, unknown> = { status, updatedAt: ts };
    if (status === "completed") u.completedAt = ts;
    if (status === "killed" || status === "stalled") u.stalledAt = ts;
    if (result) u.result = result;
    return db.update(agentTasks).set(u).where(eq(agentTasks.id, id)).returning().get();
  }
  markStalledTasks(thresholdMin = 5) {
    const cutoff = new Date(Date.now() - thresholdMin * 60000);
    return this.getRunningTasks()
      .filter(t => new Date(t.startedAt) < cutoff)
      .map(t => this.updateAgentTask(t.id, "stalled", `Auto-flagged: >${thresholdMin}min with no result`));
  }

  getCronJobs() { return db.select().from(cronJobs).orderBy(cronJobs.name).all(); }
  toggleCronJob(id: number, enabled: boolean) {
    return db.update(cronJobs).set({ enabled: enabled ? 1 : 0, updatedAt: now() }).where(eq(cronJobs.id, id)).returning().get();
  }
  upsertCronJob(data: InsertCronJob) {
    const existing = db.select().from(cronJobs).where(eq(cronJobs.cronId, data.cronId)).get();
    if (existing) return db.update(cronJobs).set({ ...data, updatedAt: now() }).where(eq(cronJobs.id, existing.id)).returning().get();
    return db.insert(cronJobs).values({ ...data, updatedAt: now() }).returning().get();
  }

  getStats() {
    const acts = db.select().from(activities).all().filter(a => !a.archivedAt);
    const dealList = db.select().from(deals).all().filter(d => !d.archivedAt);
    const unread = this.getUnreadCount();
    const running = this.getRunningTasks().length;
    return {
      tasks_total: acts.length,
      tasks_in_progress: acts.filter(a => a.status === "in_progress").length,
      tasks_completed: acts.filter(a => a.status === "completed").length,
      tasks_planned: acts.filter(a => a.status === "planned").length,
      deals_active: dealList.filter(d => ["loi","dd","negotiation"].includes(d.status)).length,
      deals_total: dealList.length,
      unread_notifications: unread,
      agents_running: running,
    };
  }
}

export const storage = new SqliteStorage();
