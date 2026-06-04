import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// ─── Activities ───────────────────────────────────────────────────────────────
export const activities = sqliteTable("activities", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  title: text("title").notNull(),
  description: text("description"),
  status: text("status").notNull().default("planned"),
  priority: text("priority").notNull().default("medium"),
  category: text("category").notNull().default("general"),
  tags: text("tags").notNull().default("[]"),
  dueDate: text("due_date"),
  completedAt: text("completed_at"),
  archivedAt: text("archived_at"),
  createdAt: text("created_at").notNull().default(""),
  updatedAt: text("updated_at").notNull().default(""),
});

// ─── Deals ────────────────────────────────────────────────────────────────────
export const deals = sqliteTable("deals", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  name: text("name").notNull(),
  type: text("type").notNull().default("acquisition"), // acquisition | rcfe | saas | agency
  status: text("status").notNull().default("scouting"), // scouting | loi | dd | negotiation | closed | dead
  askPrice: text("ask_price"),
  targetPrice: text("target_price"),
  mrr: text("mrr"),
  broker: text("broker"),
  brokerEmail: text("broker_email"),
  sellerName: text("seller_name"),
  sellerEmail: text("seller_email"),
  ddFolderUrl: text("dd_folder_url"),
  score: integer("score"),
  notes: text("notes"),
  nextAction: text("next_action"),
  nextActionDue: text("next_action_due"),
  archivedAt: text("archived_at"),
  createdAt: text("created_at").notNull().default(""),
  updatedAt: text("updated_at").notNull().default(""),
});

// ─── Energy Logs ─────────────────────────────────────────────────────────────
export const energyLogs = sqliteTable("energy_logs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  level: integer("level").notNull(),
  period: text("period").notNull(),
  note: text("note"),
  timestamp: text("timestamp").notNull().default(""),
  date: text("date").notNull().default(""),
});

// ─── Notifications / Intel ────────────────────────────────────────────────────
export const notifications = sqliteTable("notifications", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  title: text("title").notNull(),
  body: text("body").notNull(),
  type: text("type").notNull().default("brief"), // brief | deal_signal | alert | system
  read: integer("read").notNull().default(0),
  archivedAt: text("archived_at"),
  createdAt: text("created_at").notNull().default(""),
});

// ─── Agent Tasks (admin watchdog) ─────────────────────────────────────────────
export const agentTasks = sqliteTable("agent_tasks", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  taskName: text("task_name").notNull(),
  taskType: text("task_type").notNull(),
  costTier: text("cost_tier").notNull().default("medium"),
  estimatedMinutes: integer("estimated_minutes"),
  status: text("status").notNull().default("running"),
  subagentId: text("subagent_id"),
  result: text("result"),
  stalledAt: text("stalled_at"),
  killedAt: text("killed_at"),
  completedAt: text("completed_at"),
  startedAt: text("started_at").notNull().default(""),
  updatedAt: text("updated_at").notNull().default(""),
});

// ─── Cron Jobs (admin view) ───────────────────────────────────────────────────
export const cronJobs = sqliteTable("cron_jobs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  cronId: text("cron_id").notNull(),
  name: text("name").notNull(),
  schedule: text("schedule").notNull(),
  scheduleHuman: text("schedule_human"),
  enabled: integer("enabled").notNull().default(1),
  lastRun: text("last_run"),
  lastStatus: text("last_status"),
  nextRun: text("next_run"),
  updatedAt: text("updated_at").notNull().default(""),
});

// ─── Insert schemas ───────────────────────────────────────────────────────────
export const insertActivitySchema = createInsertSchema(activities).omit({ id: true, createdAt: true, updatedAt: true, completedAt: true, archivedAt: true });
export const insertDealSchema = createInsertSchema(deals).omit({ id: true, createdAt: true, updatedAt: true, archivedAt: true });
export const insertEnergyLogSchema = createInsertSchema(energyLogs).omit({ id: true, timestamp: true, date: true });
export const insertNotificationSchema = createInsertSchema(notifications).omit({ id: true, createdAt: true, archivedAt: true });
export const insertAgentTaskSchema = createInsertSchema(agentTasks).omit({ id: true, startedAt: true, updatedAt: true, stalledAt: true, killedAt: true, completedAt: true });
export const insertCronJobSchema = createInsertSchema(cronJobs).omit({ id: true, updatedAt: true });

// ─── Types ────────────────────────────────────────────────────────────────────
export type Activity = typeof activities.$inferSelect;
export type Deal = typeof deals.$inferSelect;
export type EnergyLog = typeof energyLogs.$inferSelect;
export type Notification = typeof notifications.$inferSelect;
export type AgentTask = typeof agentTasks.$inferSelect;
export type CronJob = typeof cronJobs.$inferSelect;

export type InsertActivity = z.infer<typeof insertActivitySchema>;
export type InsertDeal = z.infer<typeof insertDealSchema>;
export type InsertEnergyLog = z.infer<typeof insertEnergyLogSchema>;
export type InsertNotification = z.infer<typeof insertNotificationSchema>;
export type InsertAgentTask = z.infer<typeof insertAgentTaskSchema>;
export type InsertCronJob = z.infer<typeof insertCronJobSchema>;
