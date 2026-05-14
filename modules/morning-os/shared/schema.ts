import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Morning check-ins, one per day
export const checkins = sqliteTable("checkins", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  date: text("date").notNull().unique(), // YYYY-MM-DD (local)
  energy: text("energy").notNull(), // 'full' | 'good' | 'okay' | 'low'
  goals: text("goals").notNull(), // JSON array of strings
  weekStatus: text("week_status"), // 'on_track' | 'mostly' | 'off_track' | 'unset'
  weekGoal: text("week_goal"),
  priority: text("priority").notNull(),
  constraint: text("constraint_text"),
  createdAt: text("created_at").notNull(),
});

export const insertCheckinSchema = createInsertSchema(checkins, {
  goals: z.string(), // JSON-stringified list
}).omit({ id: true });

export type InsertCheckin = z.infer<typeof insertCheckinSchema>;
export type Checkin = typeof checkins.$inferSelect;

// Persistent goals by time horizon
export const goals = sqliteTable("goals", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  horizon: text("horizon").notNull().unique(), // 'month' | 'quarter' | 'year' | 'three_year' | 'life'
  content: text("content").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const insertGoalSchema = createInsertSchema(goals).omit({ id: true });
export type InsertGoal = z.infer<typeof insertGoalSchema>;
export type Goal = typeof goals.$inferSelect;

// Keep users table to satisfy any template residuals
export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
});

export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof users.$inferSelect;
