import { sqliteTable, text, integer, real } from "drizzle-orm/sqlite-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// ─── Activities (Kanban tasks) ───────────────────────────────────────────────
export const activities = sqliteTable("activities", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  title: text("title").notNull(),
  description: text("description"),
  status: text("status").notNull().default("planned"), // planned | in_progress | completed | carry_over | parking_lot
  priority: text("priority").notNull().default("medium"), // low | medium | high | critical
  category: text("category").notNull().default("general"), // acquisition | revenue | eva_build | operations | outreach | general
  tags: text("tags").notNull().default("[]"), // JSON array of tag strings
  dueDate: text("due_date"),
  completedAt: text("completed_at"),
  archivedAt: text("archived_at"), // soft delete — never hard delete
  createdAt: text("created_at").notNull().default(""),
  updatedAt: text("updated_at").notNull().default(""),
});

// ─── Activity Events (audit log for every state change) ──────────────────────
export const activityEvents = sqliteTable("activity_events", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  activityId: integer("activity_id").notNull(),
  eventType: text("event_type").notNull(), // created | status_changed | done_clicked | edited | archived
  fromStatus: text("from_status"),
  toStatus: text("to_status"),
  note: text("note"),
  timestamp: text("timestamp").notNull().default(""),
});

// ─── Energy Logs ─────────────────────────────────────────────────────────────
export const energyLogs = sqliteTable("energy_logs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  level: integer("level").notNull(), // 1–5
  period: text("period").notNull(), // morning | midday | evening
  note: text("note"),
  timestamp: text("timestamp").notNull().default(""),
  date: text("date").notNull().default(""), // YYYY-MM-DD for easy grouping
});

// ─── Insert schemas ───────────────────────────────────────────────────────────
export const insertActivitySchema = createInsertSchema(activities).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
  completedAt: true,
  archivedAt: true,
});

export const insertActivityEventSchema = createInsertSchema(activityEvents).omit({
  id: true,
  timestamp: true,
});

export const insertEnergyLogSchema = createInsertSchema(energyLogs).omit({
  id: true,
  timestamp: true,
  date: true,
});

// ─── Types ────────────────────────────────────────────────────────────────────
export type Activity = typeof activities.$inferSelect;
export type InsertActivity = z.infer<typeof insertActivitySchema>;
export type ActivityEvent = typeof activityEvents.$inferSelect;
export type InsertActivityEvent = z.infer<typeof insertActivityEventSchema>;
export type EnergyLog = typeof energyLogs.$inferSelect;
export type InsertEnergyLog = z.infer<typeof insertEnergyLogSchema>;

export type ActivityStatus = "planned" | "in_progress" | "completed" | "carry_over" | "parking_lot";
export type ActivityPriority = "low" | "medium" | "high" | "critical";
export type ActivityCategory = "acquisition" | "revenue" | "eva_build" | "operations" | "outreach" | "general";
export type EnergyPeriod = "morning" | "midday" | "evening";
