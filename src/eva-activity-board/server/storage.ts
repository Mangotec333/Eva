import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc, and } from "drizzle-orm";
import {
  activities,
  activityEvents,
  energyLogs,
  type Activity,
  type InsertActivity,
  type ActivityEvent,
  type InsertActivityEvent,
  type EnergyLog,
  type InsertEnergyLog,
  agentTasks,
  type AgentTask,
  type InsertAgentTask,
} from "@shared/schema";

const sqlite = new Database("data.db");
const db = drizzle(sqlite);

// Run migrations
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

  CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    note TEXT,
    timestamp TEXT NOT NULL DEFAULT ''
  );

  CREATE TABLE IF NOT EXISTS agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    estimated_minutes INTEGER,
    cost_tier TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'running',
    subagent_id TEXT,
    result TEXT,
    stalled_at TEXT,
    killed_at TEXT,
    completed_at TEXT,
    started_at TEXT NOT NULL DEFAULT '',
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
`);

function now() {
  return new Date().toISOString();
}

function today() {
  return new Date().toISOString().split("T")[0];
}

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

export class SqliteStorage implements IStorage {
  getAllActivities(): Activity[] {
    return db.select().from(activities).orderBy(desc(activities.updatedAt)).all();
  }

  getActivitiesByStatus(status: string): Activity[] {
    return db.select().from(activities).where(eq(activities.status, status)).orderBy(desc(activities.updatedAt)).all();
  }

  createActivity(data: InsertActivity): Activity {
    const ts = now();
    return db.insert(activities).values({ ...data, createdAt: ts, updatedAt: ts }).returning().get();
  }

  updateActivityStatus(id: number, status: string, note?: string): Activity {
    const existing = db.select().from(activities).where(eq(activities.id, id)).get();
    if (!existing) throw new Error(`Activity ${id} not found`);

    const ts = now();
    const updates: Record<string, unknown> = { status, updatedAt: ts };
    if (status === "completed") updates.completedAt = ts;

    const updated = db.update(activities).set(updates).where(eq(activities.id, id)).returning().get();

    // Log the event
    db.insert(activityEvents).values({
      activityId: id,
      eventType: "status_changed",
      fromStatus: existing.status,
      toStatus: status,
      note: note || null,
      timestamp: ts,
    }).run();

    return updated;
  }

  markActivityDone(id: number): Activity {
    const existing = db.select().from(activities).where(eq(activities.id, id)).get();
    if (!existing) throw new Error(`Activity ${id} not found`);

    const ts = now();
    const updated = db.update(activities)
      .set({ status: "completed", completedAt: ts, updatedAt: ts })
      .where(eq(activities.id, id))
      .returning().get();

    db.insert(activityEvents).values({
      activityId: id,
      eventType: "done_clicked",
      fromStatus: existing.status,
      toStatus: "completed",
      note: "Marked done via Done button",
      timestamp: ts,
    }).run();

    return updated;
  }

  updateActivity(id: number, data: Partial<InsertActivity>): Activity {
    const ts = now();
    const updated = db.update(activities).set({ ...data, updatedAt: ts }).where(eq(activities.id, id)).returning().get();

    db.insert(activityEvents).values({
      activityId: id,
      eventType: "edited",
      fromStatus: null,
      toStatus: null,
      note: `Updated: ${Object.keys(data).join(", ")}`,
      timestamp: ts,
    }).run();

    return updated;
  }

  archiveActivity(id: number): Activity {
    const existing = db.select().from(activities).where(eq(activities.id, id)).get();
    if (!existing) throw new Error(`Activity ${id} not found`);
    const ts = now();
    const updated = db.update(activities).set({ archivedAt: ts, updatedAt: ts }).where(eq(activities.id, id)).returning().get();
    db.insert(activityEvents).values({
      activityId: id,
      eventType: "archived",
      fromStatus: existing.status,
      toStatus: null,
      note: "Soft archived — data preserved for ML",
      timestamp: ts,
    }).run();
    return updated;
  }

  getEventsForActivity(activityId: number): ActivityEvent[] {
    return db.select().from(activityEvents)
      .where(eq(activityEvents.activityId, activityId))
      .orderBy(desc(activityEvents.timestamp))
      .all();
  }

  getAllEvents(limit = 100): ActivityEvent[] {
    return db.select().from(activityEvents).orderBy(desc(activityEvents.timestamp)).limit(limit).all();
  }

  createEvent(data: InsertActivityEvent): ActivityEvent {
    return db.insert(activityEvents).values({ ...data, timestamp: now() }).returning().get();
  }

  getEnergyLogs(limit = 30): EnergyLog[] {
    return db.select().from(energyLogs).orderBy(desc(energyLogs.timestamp)).limit(limit).all();
  }

  getEnergyLogsByDate(date: string): EnergyLog[] {
    return db.select().from(energyLogs).where(eq(energyLogs.date, date)).orderBy(desc(energyLogs.timestamp)).all();
  }

  createEnergyLog(data: InsertEnergyLog): EnergyLog {
    const ts = now();
    return db.insert(energyLogs).values({ ...data, timestamp: ts, date: today() }).returning().get();
  }

  createAgentTask(data: InsertAgentTask): AgentTask {
    const ts = now();
    return db.insert(agentTasks).values({ ...data, startedAt: ts, updatedAt: ts }).returning().get();
  }

  getAgentTasks(limit = 50): AgentTask[] {
    return db.select().from(agentTasks).orderBy(desc(agentTasks.startedAt)).limit(limit).all();
  }

  getRunningAgentTasks(): AgentTask[] {
    return db.select().from(agentTasks).where(eq(agentTasks.status, "running")).all();
  }

  updateAgentTaskStatus(id: number, status: string, result?: string): AgentTask {
    const ts = now();
    const updates: Record<string, unknown> = { status, updatedAt: ts };
    if (status === "completed") updates.completedAt = ts;
    if (status === "killed" || status === "stalled") updates.stalledAt = ts;
    if (result) updates.result = result;
    return db.update(agentTasks).set(updates).where(eq(agentTasks.id, id)).returning().get();
  }

  markStalledTasks(thresholdMinutes = 5): AgentTask[] {
    const running = this.getRunningAgentTasks();
    const cutoff = new Date(Date.now() - thresholdMinutes * 60 * 1000);
    const stalled: AgentTask[] = [];
    for (const task of running) {
      const started = new Date(task.startedAt);
      if (started < cutoff) {
        const updated = this.updateAgentTaskStatus(task.id, "stalled", `Auto-flagged: running for >${thresholdMinutes}min with no result`);
        stalled.push(updated);
      }
    }
    return stalled;
  }

  getLatestEnergyLogs(days = 7): EnergyLog[] {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return db.select().from(energyLogs).orderBy(desc(energyLogs.timestamp)).limit(days * 3).all();
  }
}

export const storage = new SqliteStorage();
