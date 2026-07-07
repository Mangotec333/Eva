# Case Study — batch.ai (moved out of the scoring engine in v7)

This narrative was hardcoded into the v6 `analyzer.py` scoring functions and
rationale strings. v7 rationales are **generic**, so the case-study content lives
here as reference material only. It informs *how* the generic dimensions were
designed; it is not injected into any score.

## Deal Intelligence Learning 001 — batch.ai / June 2026

**Q: Why would users want batch.ai when Adobe offers batch features in enterprise?**

Adobe Firefly Creative Production (announced Oct 28 2025, private beta) targets
ENTERPRISE content teams at $1,000+/month minimum — campaign production, brand
localization, content supply chains. The buyer is a CMO or content-ops team.
batch.ai's buyer is an individual wedding/portrait photographer charging
$2,000/wedding who needs a gallery of 1,000 images edited in 30 minutes in their
personal style. These markets do not overlap.

Adobe LR Classic 15.3 (Apr 2026) added background AI for Denoise and Super
Resolution ONLY. It does NOT learn the photographer's edit style and does NOT
batch-apply user adjustments — a technical utility, not workflow automation.

batch.ai's real competitors are Aftershoot ($480/yr) and Imagen AI ($810+/yr) —
both STANDALONE APPS that require leaving Lightroom. batch.ai is a plugin that
lives INSIDE LR Classic. That single UX advantage (zero context switching) is the
primary reason photographers describe it as "life-changing."

**Q: Is Adobe enterprise competition the reason users are leaving?**

No. Revenue decline ($13K → $5K, −62%) is marketing neglect. Evidence: Trustpilot
4.8/5 from 50 reviews (all 2022–2023 when the founder was active), reviews naming
"Shawn" personally, dormant Instagram + cold email list, Stripe still billing,
SDK still functional. Adobe enterprise launched AFTER the decline began. The
decline curve tracks marketing silence, not product degradation.

## Encoded Deal Intelligence Rule (now expressed generically in v7)

> When a SaaS shows sharp revenue decline with intact product metrics (billing
> still active, core product functional, positive reviews still visible), check
> the OWNER'S SOCIAL ACTIVITY TIMELINE before assuming product or market failure.
> Revenue that tracks with the founder's last marketing activity = marketing
> problem, not product problem. Marketing problems are the most recoverable form
> of decline. This pattern should RAISE profit_potential (recovery upside), not
> lower the offer price.

### How v7 generalises this

- The batch.ai-specific Adobe risk → generic `platform_dependency_risk_score`.
- The batch.ai marketing-recovery thesis → generic `owner_neglect_score` +
  `profit_potential` levers (`brand_awareness`, `content_social_presence`,
  `retention_lifecycle`) whose upside rises when revenue sits below peak.
- The batch.ai buy-vs-build narrative → generic `buy_vs_build_score` derived from
  the decision + moat depth (no hardcoded dollar figures).
