import type { Express } from "express";
import { createServer } from "http";
import rateLimit from "express-rate-limit";
import { storage } from "./storage";
import { insertActivitySchema, insertDealSchema, insertEnergyLogSchema, insertNotificationSchema, insertAgentTaskSchema } from "@shared/schema";
import { z } from "zod";
import { runFullDealEvaluation } from "./lib/dealScoring";
import type { DealScoringInputs } from "./lib/dealScoring";

// In production, ADMIN_PIN must be set via env var
if (process.env.NODE_ENV === "production" && !process.env.ADMIN_PIN) {
  console.warn("ADMIN_PIN not set in production — falling back to default (insecure)");
}
const ADMIN_PIN = process.env.ADMIN_PIN || "557799";

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  message: { error: "Too many auth attempts. Try again in 15 minutes." },
  standardHeaders: true,
  legacyHeaders: false,
});

function requireAdmin(req: any, res: any, next: any) {
  const pin = req.headers["x-admin-pin"] || req.query.pin;
  if (pin !== ADMIN_PIN) return res.status(401).json({ error: "Unauthorized" });
  next();
}

// Wrap async route handlers to catch errors
const wrap = (fn: Function) => (req: any, res: any, next: any) =>
  Promise.resolve(fn(req, res, next)).catch(next);

export function registerRoutes(httpServer: ReturnType<typeof createServer>, app: Express) {

  // ── Stats ─────────────────────────────────────────────────────────────────
  app.get("/api/stats", wrap(async (_req: any, res: any) => res.json(await storage.getStats())));

  // ── Activities ────────────────────────────────────────────────────────────
  app.get("/api/activities", wrap(async (_req: any, res: any) => res.json(await storage.getAllActivities())));
  app.post("/api/activities", wrap(async (req: any, res: any) => {
    res.json(await storage.createActivity(insertActivitySchema.parse(req.body)));
  }));
  app.post("/api/activities/:id/done", wrap(async (req: any, res: any) => {
    res.json(await storage.markDone(parseInt(req.params.id)));
  }));
  app.patch("/api/activities/:id/status", wrap(async (req: any, res: any) => {
    const { status } = z.object({ status: z.string() }).parse(req.body);
    res.json(await storage.updateActivityStatus(parseInt(req.params.id), status));
  }));
  app.patch("/api/activities/:id", wrap(async (req: any, res: any) => {
    res.json(await storage.updateActivity(parseInt(req.params.id), insertActivitySchema.partial().parse(req.body)));
  }));
  app.delete("/api/activities/:id", wrap(async (req: any, res: any) => {
    res.json(await storage.archiveActivity(parseInt(req.params.id)));
  }));

  // ── Deals ─────────────────────────────────────────────────────────────────
  app.get("/api/deals", wrap(async (_req: any, res: any) => res.json(await storage.getAllDeals())));
  app.post("/api/deals", wrap(async (req: any, res: any) => {
    res.json(await storage.createDeal(insertDealSchema.parse(req.body)));
  }));
  app.patch("/api/deals/:id", wrap(async (req: any, res: any) => {
    res.json(await storage.updateDeal(parseInt(req.params.id), insertDealSchema.partial().parse(req.body)));
  }));

  // ── Deal Scoring Engine ────────────────────────────────────────────────────
  // POST /api/deals/:id/score
  // Body: DealScoringInputs (all fields optional — only provided fields are evaluated)
  // Returns: FullScoringOutput with score, active flags, PRE_LOI_GATE result, and
  //          recommended deal status. Also persists the computed score to the deal row.
  //
  // 10 checks (batch.ai DD learnings — EF #87872):
  //   S1  platform_as_competitor      -20 pts  flag: platform_competitor_risk
  //   S2  mrr_decay_rate              -15 pts  flag: structural_mrr_decline
  //   S3  new_mrr_ratio               -20 pts  flag: acquisition_engine_broken   [LOI blocker]
  //   S4  subscriber_half_life        -15 pts  flag: structural_churn            [LOI blocker]
  //   S5  competitive_substitution    -25 pts  flag: moat_invalidated            [LOI blocker]
  //   S6  review_recency_gap            0 pts  flag: competitive_research_required [LOI blocker]
  //   S7  owner_neglect_factor          0 pts  flag: unverified_neglect_claim
  //   S8  revenue_expense_stickiness    0 pts  flag: margin_compression
  //   S9  pl_tax_gap                    0 pts  flag: reconciliation_required     [LOI blocker]
  //   S10 depreciation_anomaly          0 pts  flag: asset_review_required
  //
  // PRE_LOI_GATE: 8 gates — 2+ failures → HOLD_LOI status.
  app.post("/api/deals/:id/score", wrap(async (req: any, res: any) => {
    const dealId = parseInt(req.params.id);

    // Validate inputs loosely — all fields optional
    const DealScoringInputsSchema = z.object({
      platformBuildsNativeCompetition:    z.boolean().optional(),
      mrrTrend:                           z.array(z.number()).optional(),
      monthlyMrrBreakdown:                z.array(z.object({ newMrr: z.number(), totalMrr: z.number() })).optional(),
      monthlyChurnRate:                   z.number().min(0).max(1).optional(),
      primaryValuePropNativelyAvailable:  z.boolean().optional(),
      lastPublicReviewDate:               z.string().optional(),
      reviewGapResearchCompleted:         z.boolean().optional(),
      ownerAttributesDeclineToNeglect:    z.boolean().optional(),
      neglectCorroborationProvided:       z.boolean().optional(),
      revenueTrend:                       z.array(z.number()).optional(),
      expenseTrend:                       z.array(z.number()).optional(),
      irsGrossRevenue:                    z.number().optional(),
      plGrossRevenue:                     z.number().optional(),
      taxGapReconciled:                   z.boolean().optional(),
      depreciationAmount:                 z.number().optional(),
      grossRevenueForDepreciation:        z.number().optional(),
      mrrTrendReviewed:                   z.boolean().optional(),
      platformDependencyMapped:           z.boolean().optional(),
      financingPathConfirmed:             z.boolean().optional(),
      walkAwayPriceDocumented:            z.boolean().optional(),
    });

    const inputs: DealScoringInputs = DealScoringInputsSchema.parse(req.body);
    const result = runFullDealEvaluation(inputs);

    // Persist computed score to the deal row
    await storage.updateDeal(dealId, { score: result.scoring.score });

    res.json(result);
  }));

  // ── Energy ────────────────────────────────────────────────────────────────
  app.get("/api/energy", wrap(async (_req: any, res: any) => res.json(await storage.getEnergyLogs())));
  app.get("/api/energy/today", wrap(async (_req: any, res: any) => res.json(await storage.getTodayEnergy())));
  app.post("/api/energy", wrap(async (req: any, res: any) => {
    res.json(await storage.createEnergyLog(insertEnergyLogSchema.parse(req.body)));
  }));

  // ── Notifications ─────────────────────────────────────────────────────────
  app.get("/api/notifications", wrap(async (_req: any, res: any) => res.json(await storage.getNotifications())));
  app.get("/api/notifications/unread", wrap(async (_req: any, res: any) => res.json({ count: await storage.getUnreadCount() })));
  app.post("/api/notifications", wrap(async (req: any, res: any) => {
    res.json(await storage.createNotification(insertNotificationSchema.parse(req.body)));
  }));
  app.post("/api/notifications/:id/read", wrap(async (req: any, res: any) => {
    await storage.markNotificationRead(parseInt(req.params.id));
    res.json({ ok: true });
  }));
  app.post("/api/notifications/read-all", wrap(async (_req: any, res: any) => {
    await storage.markAllRead();
    res.json({ ok: true });
  }));

  // ── KPI Metrics ───────────────────────────────────────────────────────────
  app.get("/api/kpi", wrap(async (_req: any, res: any) => res.json(await storage.getAllKpi())));
  app.patch("/api/kpi/:key", wrap(async (req: any, res: any) => {
    const { value, label, unit, category } = z.object({
      value: z.string(),
      label: z.string().optional(),
      unit: z.string().optional(),
      category: z.string().optional(),
    }).parse(req.body);
    res.json(await storage.upsertKpi(req.params.key, value, label, unit, category));
  }));

  // ── Public cron ping ──────────────────────────────────────────────────────
  app.post("/api/crons/ping", wrap(async (req: any, res: any) => {
    const { cronId, status, note } = z.object({
      cronId: z.string(),
      status: z.enum(["success", "failed"]),
      note: z.string().optional(),
    }).parse(req.body);
    const ts = new Date().toISOString();
    const nextRun = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    const crons = await storage.getCronJobs();
    const existing = crons.find((c: any) => (c.cronId ?? c.cron_id) === cronId);
    if (!existing) return res.status(404).json({ error: "cron not found" });
    await storage.upsertCronJob({
      cronId,
      name: existing.name,
      schedule: existing.schedule,
      scheduleHuman: existing.scheduleHuman ?? null,
      enabled: existing.enabled,
      lastRun: ts,
      lastStatus: status,
      nextRun,
    });
    res.json({ ok: true, cronId, lastRun: ts, lastStatus: status });
  }));

  // ── ADMIN — Agent Tasks ───────────────────────────────────────────────────
  app.get("/api/admin/agent-tasks", requireAdmin, wrap(async (_req: any, res: any) => res.json(await storage.getAgentTasks())));
  app.post("/api/admin/agent-tasks", requireAdmin, wrap(async (req: any, res: any) => {
    res.json(await storage.createAgentTask(insertAgentTaskSchema.parse(req.body)));
  }));
  app.patch("/api/admin/agent-tasks/:id", requireAdmin, wrap(async (req: any, res: any) => {
    const { status, result } = z.object({ status: z.string(), result: z.string().optional() }).parse(req.body);
    res.json(await storage.updateAgentTask(parseInt(req.params.id), status, result));
  }));
  app.post("/api/admin/watchdog", requireAdmin, wrap(async (_req: any, res: any) => {
    const stalled = await storage.markStalledTasks(5);
    res.json({ stalled: stalled.length, tasks: stalled });
  }));

  // ── ADMIN — Crons ─────────────────────────────────────────────────────────
  app.get("/api/admin/crons", requireAdmin, wrap(async (_req: any, res: any) => res.json(await storage.getCronJobs())));
  app.patch("/api/admin/crons/:id", requireAdmin, wrap(async (req: any, res: any) => {
    const { enabled } = z.object({ enabled: z.boolean() }).parse(req.body);
    res.json(await storage.toggleCronJob(parseInt(req.params.id), enabled));
  }));
  app.post("/api/admin/crons/refresh", requireAdmin, (_req: any, res: any) => {
    res.json({ ok: true, message: "Cron registry synced" });
  });
  app.post("/api/admin/crons", requireAdmin, wrap(async (req: any, res: any) => {
    const data = z.object({
      cronId: z.string(),
      name: z.string(),
      schedule: z.string(),
      scheduleHuman: z.string().optional(),
      enabled: z.boolean().default(true),
    }).parse(req.body);
    const now = new Date().toISOString();
    const result = await storage.upsertCronJob({
      cronId: data.cronId,
      name: data.name,
      schedule: data.schedule,
      scheduleHuman: data.scheduleHuman ?? null,
      enabled: data.enabled,
      lastRun: null,
      lastStatus: null,
      nextRun: null,
    });
    res.json({ ok: true, cron: result });
  }));

  // ── ADMIN — Kill task ─────────────────────────────────────────────────────
  app.post("/api/admin/agent-tasks/:id/kill", requireAdmin, wrap(async (req: any, res: any) => {
    res.json(await storage.updateAgentTask(parseInt(req.params.id), "killed", "Killed via admin panel"));
  }));

  // ── ADMIN — Auth ──────────────────────────────────────────────────────────
  app.post("/api/admin/auth", authLimiter, (req: any, res: any) => {
    try {
      const { pin } = z.object({ pin: z.string() }).parse(req.body);
      res.json({ ok: pin === ADMIN_PIN });
    } catch (e) { res.status(400).json({ error: String(e) }); }
  });
}
