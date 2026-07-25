# EVA Offer Agent

Scores and strengthens every offer EVA packages, using Alex Hormozi's
*$100M Offers* Value Equation and Grand Slam Offer framework as the seed
doctrine. See [`directive.md`](./directive.md) for the full framework,
scoring model, and operating rules.

**Status:** directive seeded. No microservice code yet — this module
currently ships as a documentation-only directive, following the same
`directive.md` pattern used across EVA agents
(`modules/monetizing-agent/directive.md`). Build the FastAPI service +
SQLite ledger + CLI once the scoring model has been exercised manually on a
few real offers (Storeys JV, Storeys Fund, EVA Growth Agency) and the weights
have proven out.

## Relationship to other agents

Feeds the **Package** step of Monetizing Agent's
`Mine → Match → Package → Route → Follow-up` loop — once a play is matched,
Offer Agent scores/sharpens the offer before it's routed out.
