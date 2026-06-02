# Eva — Layer 1: Communication Sources Registry

**Layer 1** is Eva's raw signal store. Every inbound or outbound communication is ingested here before processing, enrichment, or routing to Layer 2 (compressed events) or Layer 3 (permanent pattern memory).

---

## Sources by Media Type

### TEXT / Asynchronous Messaging
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Gmail | Google API (connected) | inbound + outbound | P0 |
| Slack | Slack API (connected) | inbound + outbound | P0 |
| LinkedIn Messaging | LinkedIn API / scrape | inbound + outbound | P1 |
| SMS / iMessage | Apple Messages export / Screenpipe | inbound + outbound | P1 |
| WhatsApp | WhatsApp Business API | inbound + outbound | P2 |
| Meta Messenger | Meta Graph API | inbound + outbound | P2 |

### VOICE / Audio
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Eva Voice Interface | Built-in (Whisper / Gemini TTS) | inbound | P0 |
| Phone Calls | Twilio / Screenpipe transcription | inbound + outbound | P1 |
| Voicemail | Twilio transcription | inbound | P1 |
| Zoom / Google Meet | Zoom API / Meet API | inbound | P2 |

### CALENDAR / Scheduling
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Google Calendar | Google Calendar API (connected) | inbound + outbound | P0 |
| Calendly | Calendly API | inbound | P1 |

### SOCIAL / Content Feeds
| Source | Integration | Direction | Priority |
|---|---|---|---|
| LinkedIn Feed | LinkedIn API | inbound | P1 |
| X (Twitter) | X API v2 | inbound + outbound | P2 |
| Meta (FB/IG) | Meta Graph API | inbound + outbound | P2 |
| YouTube | YouTube Data API (connected) | inbound | P3 |

### DEAL & MARKET SIGNALS
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Empire Flippers | EF API / Deal Scout agent | inbound | P0 |
| Acquire.com | Web extraction / Deal Scout | inbound | P1 |
| Flippa | Web extraction / Deal Scout | inbound | P1 |
| LoopNet / MLS | Web extraction | inbound | P2 |

### DOCUMENTS & FILES
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Google Drive | Google Drive API (connected) | inbound + outbound | P0 |
| Gmail Attachments | Parsed via Gmail API | inbound | P0 |
| Direct Upload | Eva UI file drop | inbound | P1 |
| Notion | Notion API (connected) | inbound | P2 |

### FINANCIAL / OPERATIONAL
| Source | Integration | Direction | Priority |
|---|---|---|---|
| Shopify | Shopify API | inbound | P1 |
| Stripe | Stripe API | inbound | P1 |
| QuickBooks / Bank | Plaid / QBO API | inbound | P2 |

---

## Layer 1 Record Schema

Every ingested record carries these fields regardless of source. See `layer1_schema.py` for the full SQLite table definition.

```
source          TEXT    — Gmail | Slack | LinkedIn | Voice | Calendar | ...
media_type      TEXT    — text | voice | calendar | social | deal | document | financial
direction       TEXT    — inbound | outbound | internal
contact_id      INT     — FK → contacts.id (nullable, matched post-ingest)
deal_id         INT     — FK → deals.id (nullable, matched post-ingest)
ingested_at     TEXT    — ISO8601 UTC timestamp
raw_payload     TEXT    — unprocessed JSON blob
processed       BOOL    — False on ingest, True after Layer 2 routing
priority        INT     — 0 (critical) → 3 (low)
```

---

## Connector Priority Legend

| Priority | Meaning |
|---|---|
| P0 | Live or build now — core to daily Eva operation |
| P1 | Build next sprint — high signal value |
| P2 | Queue — useful but not blocking |
| P3 | Parking lot — low urgency |

---

## Whitelabel Note

Every source connector is built as a standalone, pluggable module. Agency clients can enable/disable sources per deployment. Source registry is config-driven — no hardcoding.

---

_Last updated: 2026-06-01 | Maintainer: Eva Core Team / Mangotec LLC_
