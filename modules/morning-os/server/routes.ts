import type { Express } from "express";
import { createServer } from "node:http";
import type { Server } from "node:http";
import { storage } from "./storage";
import { insertCheckinSchema, insertGoalSchema } from "@shared/schema";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // ---- check-ins ----
  app.get("/api/checkins", async (_req, res) => {
    const rows = await storage.listCheckins();
    res.json(rows);
  });

  app.get("/api/checkins/today", async (_req, res) => {
    const date = new Date().toISOString().slice(0, 10);
    const row = await storage.getCheckinByDate(date);
    res.json(row ?? null);
  });

  app.post("/api/checkins", async (req, res) => {
    try {
      const body = {
        ...req.body,
        date: req.body.date ?? new Date().toISOString().slice(0, 10),
        createdAt: new Date().toISOString(),
        goals:
          typeof req.body.goals === "string"
            ? req.body.goals
            : JSON.stringify(req.body.goals ?? []),
      };
      const parsed = insertCheckinSchema.parse(body);
      const saved = await storage.upsertCheckin(parsed);
      res.json(saved);
    } catch (err: any) {
      res.status(400).json({ error: err?.message ?? "Invalid check-in" });
    }
  });

  // ---- goals ----
  app.get("/api/goals", async (_req, res) => {
    const rows = await storage.listGoals();
    res.json(rows);
  });

  app.post("/api/goals", async (req, res) => {
    try {
      const body = {
        ...req.body,
        updatedAt: new Date().toISOString(),
      };
      const parsed = insertGoalSchema.parse(body);
      const saved = await storage.upsertGoal(parsed);
      res.json(saved);
    } catch (err: any) {
      res.status(400).json({ error: err?.message ?? "Invalid goal" });
    }
  });

  // ---- activity proxy ----
  app.get("/api/activity/today", async (_req, res) => {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 1500);
      const r = await fetch("http://localhost:8765/context/today", {
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!r.ok) {
        return res.json({ available: false, reason: `status ${r.status}` });
      }
      const data = await r.json();
      res.json({ available: true, data });
    } catch (err: any) {
      res.json({ available: false, reason: "logger_offline" });
    }
  });

  return httpServer;
}
