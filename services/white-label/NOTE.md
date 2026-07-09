# NOTE — white-label scaffold is TypeScript v0

This directory holds the **v0 scaffold** for the Eva white-label platform
(CRM provider abstraction, LeadCaptureService, OnboardingAgent). It was authored
in **TypeScript** to mirror the working `eva-landing` `/api/lead` prototype.

## Convention mismatch (intentional, tracked)

This repo is **Python-first**: backend services live under `services/` as Python
modules (`services/brain`, `services/bridge`, `services/model`, …) and are wired
through `pyproject.toml`. The `.ts` files here do **not** match that convention.

- These files are **specification-as-code** — the canonical interface + flow, in
  the language the prototype was written in.
- They are **not** imported by any Python entrypoint and are **not** built by
  `pyproject.toml`. There is no TS toolchain in this repo yet.
- Next pass: **port to Python** to match repo conventions —
  `CRMProvider` → `Protocol`/ABC, `GHLProvider` → httpx client, `captureLead` /
  `onboard` → async service functions with a mock provider for tests (pytest).

Do not delete or rewrite these until the Python port lands; they are the
reference contract for that port.

## Files
- `providers/crm-provider.ts` — CRMProvider interface (swap & play contract)
- `providers/ghl-provider.ts` — GoHighLevel implementation (prototype token path)
- `services/lead-capture-service.ts` — LeadCaptureService v1 (provider-backed)
- `agents/onboarding-agent.ts` — OnboardingAgent v0

See `docs/white-label/architecture.md` for the full spec and build sequence.
