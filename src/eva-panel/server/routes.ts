import type { Express } from "express";
import { createServer } from "http";
import { storage } from "./storage";
import { insertActivitySchema, insertDealSchema, insertEnergyLogSchema, insertNotificationSchema, insertAgentTaskSchema } from "@shared/schema";
import { z } from "zod";

const ADMIN_PIN = process.env.ADMIN_PIN || "557799";

function requireAdmin(req: any, res: any, next: any) {
  const pin = req.headers["x-admin-pin"] || req.query.pin;
  if (pin !== ADMIN_PIN) return res.status(401).json({ error: "Unauthorized" });
  next();
}

export function registerRoutes(httpServer: ReturnType<typeof createServer>, app: Express) {

  // ── Stats (used by both panels) ──────────────────────────────────────────────
  app.get("/api/stats", (_req, res) => res.json(storage.getStats()));

  // ── Activities ───────────────────────────────────────────────────────────────
  app.get("/api/activities", (_req, res) => res.json(storage.getAllActivities()));
  app.post("/api/activities", (req, res) => {
    try { res.json(storage.createActivity(insertActivitySchema.parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.post("/api/activities/:id/done", (req, res) => {
    try { res.json(storage.markDone(parseInt(req.params.id))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.patch("/api/activities/:id/status", (req, res) => {
    try {
      const { status } = z.object({ status: z.string() }).parse(req.body);
      res.json(storage.updateActivityStatus(parseInt(req.params.id), status));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.patch("/api/activities/:id", (req, res) => {
    try { res.json(storage.updateActivity(parseInt(req.params.id), insertActivitySchema.partial().parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.delete("/api/activities/:id", (req, res) => {
    try { res.json(storage.archiveActivity(parseInt(req.params.id))); }
    catch (e) { res.status(500).json({ error: String(e) }); }
  });

  // ── Deals ────────────────────────────────────────────────────────────────────
  app.get("/api/deals", (_req, res) => res.json(storage.getAllDeals()));
  app.post("/api/deals", (req, res) => {
    try { res.json(storage.createDeal(insertDealSchema.parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.patch("/api/deals/:id", (req, res) => {
    try { res.json(storage.updateDeal(parseInt(req.params.id), insertDealSchema.partial().parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });

  // ── Energy ───────────────────────────────────────────────────────────────────
  app.get("/api/energy", (_req, res) => res.json(storage.getEnergyLogs()));
  app.get("/api/energy/today", (_req, res) => res.json(storage.getTodayEnergy()));
  app.post("/api/energy", (req, res) => {
    try { res.json(storage.createEnergyLog(insertEnergyLogSchema.parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });

  // ── Notifications / Intel ────────────────────────────────────────────────────
  app.get("/api/notifications", (_req, res) => res.json(storage.getNotifications()));
  app.get("/api/notifications/unread", (_req, res) => res.json({ count: storage.getUnreadCount() }));
  app.post("/api/notifications", (req, res) => {
    try { res.json(storage.createNotification(insertNotificationSchema.parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.post("/api/notifications/:id/read", (req, res) => {
    storage.markNotificationRead(parseInt(req.params.id));
    res.json({ ok: true });
  });
  app.post("/api/notifications/read-all", (_req, res) => {
    storage.markAllRead();
    res.json({ ok: true });
  });

  // ── ADMIN — Agent Tasks (PIN-gated) ──────────────────────────────────────────
  app.get("/api/admin/agent-tasks", requireAdmin, (_req, res) => res.json(storage.getAgentTasks()));
  app.post("/api/admin/agent-tasks", requireAdmin, (req, res) => {
    try { res.json(storage.createAgentTask(insertAgentTaskSchema.parse(req.body))); }
    catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.patch("/api/admin/agent-tasks/:id", requireAdmin, (req, res) => {
    try {
      const { status, result } = z.object({ status: z.string(), result: z.string().optional() }).parse(req.body);
      res.json(storage.updateAgentTask(parseInt(req.params.id), status, result));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.post("/api/admin/watchdog", requireAdmin, (_req, res) => {
    const stalled = storage.markStalledTasks(5);
    res.json({ stalled: stalled.length, tasks: stalled });
  });

  // ── ADMIN — Crons (PIN-gated) ─────────────────────────────────────────────────
  app.get("/api/admin/crons", requireAdmin, (_req, res) => res.json(storage.getCronJobs()));
  app.patch("/api/admin/crons/:id", requireAdmin, (req, res) => {
    try {
      const { enabled } = z.object({ enabled: z.boolean() }).parse(req.body);
      res.json(storage.toggleCronJob(parseInt(req.params.id), enabled));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });
  app.post("/api/admin/crons/refresh", requireAdmin, (_req, res) => {
    res.json({ ok: true, message: "Cron registry synced" });
  });

  // ── ADMIN — Kill task ────────────────────────────────────────────────────────
  app.post("/api/admin/agent-tasks/:id/kill", requireAdmin, (req, res) => {
    try {
      res.json(storage.updateAgentTask(parseInt(req.params.id), "killed", "Killed via admin panel"));
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });

  // ── ADMIN — Auth check ────────────────────────────────────────────────────────
  app.post("/api/admin/auth", (req, res) => {
    const { pin } = z.object({ pin: z.string() }).parse(req.body);
    res.json({ ok: pin === ADMIN_PIN });
  });
}
