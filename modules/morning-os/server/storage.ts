import { users, checkins, goals } from '@shared/schema';
import type { User, InsertUser, Checkin, InsertCheckin, Goal, InsertGoal } from '@shared/schema';
import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc } from "drizzle-orm";

const sqlite = new Database("data.db");
sqlite.pragma("journal_mode = WAL");

// Bootstrap tables (idempotent) — Drizzle has no migrate runtime by default here.
sqlite.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    energy TEXT NOT NULL,
    goals TEXT NOT NULL,
    week_status TEXT,
    week_goal TEXT,
    priority TEXT NOT NULL,
    constraint_text TEXT,
    created_at TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
`);

export const db = drizzle(sqlite);

export interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;

  listCheckins(): Promise<Checkin[]>;
  getCheckinByDate(date: string): Promise<Checkin | undefined>;
  upsertCheckin(c: InsertCheckin): Promise<Checkin>;

  listGoals(): Promise<Goal[]>;
  upsertGoal(g: InsertGoal): Promise<Goal>;
}

export class DatabaseStorage implements IStorage {
  async getUser(id: number): Promise<User | undefined> {
    return db.select().from(users).where(eq(users.id, id)).get();
  }
  async getUserByUsername(username: string): Promise<User | undefined> {
    return db.select().from(users).where(eq(users.username, username)).get();
  }
  async createUser(insertUser: InsertUser): Promise<User> {
    return db.insert(users).values(insertUser).returning().get();
  }

  async listCheckins(): Promise<Checkin[]> {
    return db.select().from(checkins).orderBy(desc(checkins.date)).all();
  }
  async getCheckinByDate(date: string): Promise<Checkin | undefined> {
    return db.select().from(checkins).where(eq(checkins.date, date)).get();
  }
  async upsertCheckin(c: InsertCheckin): Promise<Checkin> {
    const existing = db.select().from(checkins).where(eq(checkins.date, c.date)).get();
    if (existing) {
      return db.update(checkins).set(c).where(eq(checkins.date, c.date)).returning().get();
    }
    return db.insert(checkins).values(c).returning().get();
  }

  async listGoals(): Promise<Goal[]> {
    return db.select().from(goals).all();
  }
  async upsertGoal(g: InsertGoal): Promise<Goal> {
    const existing = db.select().from(goals).where(eq(goals.horizon, g.horizon)).get();
    if (existing) {
      return db.update(goals).set(g).where(eq(goals.horizon, g.horizon)).returning().get();
    }
    return db.insert(goals).values(g).returning().get();
  }
}

export const storage = new DatabaseStorage();

// Seed default goals once
async function seed() {
  const existing = await storage.listGoals();
  if (existing.length > 0) return;
  const now = new Date().toISOString();
  const seeds: InsertGoal[] = [
    {
      horizon: 'life',
      content:
        'EVA exists in the world. Family experiences the finest things. No financial stress. I stood on stages and made rooms feel what autonomous AI means for humanity.',
      updatedAt: now,
    },
    {
      horizon: 'year',
      content: 'AI Growth Agency hits $10K net/month. EVA Module 1 deployed. RCFE operational.',
      updatedAt: now,
    },
    {
      horizon: 'quarter',
      content: 'First AI agency client landed. EVA Activity Logger running. RCFE closed.',
      updatedAt: now,
    },
    { horizon: 'month', content: '', updatedAt: now },
    { horizon: 'three_year', content: '', updatedAt: now },
  ];
  for (const s of seeds) {
    if (s.content) await storage.upsertGoal(s);
    else {
      // create empty rows so the form has anchors
      await storage.upsertGoal(s);
    }
  }
}
seed().catch((e) => console.error('seed error', e));
