import type { Express } from "express";
import { createServer } from "http";
import { storage } from "./storage";
import { insertActivitySchema, insertEnergyLogSchema, insertAgentTaskSchema } from "@shared/schema";
import { z } from "zod";

export function registerRoutes(httpServer: ReturnType<typeof createServer>, app: Express) {
  // ─── Activities ──────────────────────────────────────────────────────────────
  app.get("/api/activities", (_req, res) => {
    try {
      const all = storage.getAllActivities();
      res.json(all);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.post("/api/activities", (req, res) => {
    try {
      const data = insertActivitySchema.parse(req.body);
      const activity = storage.createActivity(data);
      res.json(activity);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  app.patch("/api/activities/:id/status", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const { status, note } = z.object({ status: z.string(), note: z.string().optional() }).parse(req.body);
      const activity = storage.updateActivityStatus(id, status, note);
      res.json(activity);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  app.post("/api/activities/:id/done", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const activity = storage.markActivityDone(id);
      res.json(activity);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  app.patch("/api/activities/:id", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const data = insertActivitySchema.partial().parse(req.body);
      const activity = storage.updateActivity(id, data);
      res.json(activity);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  app.delete("/api/activities/:id", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const activity = storage.archiveActivity(id);
      res.json(activity);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  // ─── Activity Events ──────────────────────────────────────────────────────────
  app.get("/api/activities/:id/events", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const events = storage.getEventsForActivity(id);
      res.json(events);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.get("/api/events", (req, res) => {
    try {
      const limit = req.query.limit ? parseInt(req.query.limit as string) : 50;
      const events = storage.getAllEvents(limit);
      res.json(events);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // ─── Energy Logs ─────────────────────────────────────────────────────────────
  app.get("/api/energy", (req, res) => {
    try {
      const days = req.query.days ? parseInt(req.query.days as string) : 7;
      const logs = storage.getLatestEnergyLogs(days);
      res.json(logs);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.get("/api/energy/today", (req, res) => {
    try {
      const today = new Date().toISOString().split("T")[0];
      const logs = storage.getEnergyLogsByDate(today);
      res.json(logs);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.post("/api/energy", (req, res) => {
    try {
      const data = insertEnergyLogSchema.parse(req.body);
      const log = storage.createEnergyLog(data);
      res.json(log);
    } catch (e) {
      res.status(400).json({ error: String(e) });
    }
  });

  // ─── Agent Tasks (Watchdog) ─────────────────────────────────────────────────
  app.get("/api/agent-tasks", (req, res) => {
    try {
      const limit = req.query.limit ? parseInt(req.query.limit as string) : 50;
      res.json(storage.getAgentTasks(limit));
    } catch (e) { res.status(500).json({ error: String(e) }); }
  });

  app.post("/api/agent-tasks", (req, res) => {
    try {
      const data = insertAgentTaskSchema.parse(req.body);
      res.json(storage.createAgentTask(data));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });

  app.patch("/api/agent-tasks/:id/status", (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const { status, result } = req.body;
      res.json(storage.updateAgentTaskStatus(id, status, result));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });

  // Watchdog endpoint — call from cron every 5 min
  app.post("/api/agent-tasks/watchdog", (_req, res) => {
    try {
      const stalled = storage.markStalledTasks(5);
      res.json({ stalled: stalled.length, tasks: stalled });
    } catch (e) { res.status(500).json({ error: String(e) }); }
  });

  // ─── Stats ────────────────────────────────────────────────────────────────────
  app.get("/api/stats", (_req, res) => {
    try {
      const all = storage.getAllActivities();
      const nonArchived = all.filter(a => !a.archivedAt);
      const stats = {
        total: nonArchived.length,
        planned: nonArchived.filter(a => a.status === "planned").length,
        in_progress: nonArchived.filter(a => a.status === "in_progress").length,
        completed: nonArchived.filter(a => a.status === "completed").length,
        carry_over: nonArchived.filter(a => a.status === "carry_over").length,
        parking_lot: nonArchived.filter(a => a.status === "parking_lot").length,
        archived: all.filter(a => !!a.archivedAt).length,
      };
      res.json(stats);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });
}
