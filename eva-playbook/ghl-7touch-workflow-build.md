# Eva Acquisition — 7-Touch GHL Workflow Build (UI-only)

The ghl-agent adds the `eva-acquisition` tag to every captured contact. This workflow
fires on that tag and sends 7 touches over 21 days. Build it once in the GHL UI.

## 0. Booking link (wired in below)
**Eva Demo Call** calendar (id `l9jr2HfsonQDHzg3LkC1`, Active, 30 min). Permanent link (survives slug changes — use this one):
`https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1`
Already substituted into touches 3, 5, 6, 7 below. Verify it opens a booking page in a browser; if it 404s, swap for `https://book.gohighlevel.com/widget/l9jr2HfsonQDHzg3LkC1`.

## 1. Create the workflow
GHL → **Automations → Workflows → Create Workflow → Start from Scratch**.
- Name: `Eva Acquisition — 7-touch (21-day)`
- Trigger: **Contact Tag** → `eva-acquisition` (Add)

## 2. Add the 7 actions (with wait delays)

Cadence: day 0, 2, 4, 7, 10, 14, 21. After each action add a **Wait** before the next.

### Touch 1 — Day 0 — EMAIL (no wait before; this is the first action)
- Action: **Send Email**
- Subject: `The manual scanning ends here`
- Body:
```
You already know the drill.

Open the portals. Filter the listings. Copy the numbers.
Do it again tomorrow.

That work does not have to be yours anymore.

Eva watches the deal flow for you.
The manual scanning ends here.

Eva scans thousands of listings against your buy box
and hands you the 3 worth closing today.

See how it works:
https://eva-acquisition.mangotec.ai
```

### Wait 2 days

### Touch 2 — Day 2 — EMAIL
- Subject: `Not just another AI`
- Body:
```
Any tool can pull a list.

Eva is built on a playbook and a deal-outcome dataset
no generic AI can match.

It learned what a good deal looks like
from outcomes, not opinions.

So the deals it hands you are worth your time.
```

### Wait 2 days

### Touch 3 — Day 4 — EMAIL
- Subject: `Your buy box, watched around the clock`
- Body:
```
Write down what you actually buy.

The market. The price band. The cash-flow floor.
That is your buy box.

Eva holds it and watches every new listing against it.
When one fits, you hear about it the same day.

The hot deal does not wait a week for you to check.

Want to see your buy box run live?
Book a call: https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1
Or just reply to this email.
```

### Wait 3 days

### Touch 4 — Day 7 — SMS
- Action: **Send SMS**
- Body:
```
Want to see a scored deal this week? Eva can run your buy box live. Reply YES and I will set it up.
```

### Wait 3 days

### Touch 5 — Day 10 — EMAIL
- Subject: `A second founder who never sleeps`
- Body:
```
Finding the deal is half the work.

The other half is turning motion into money.

Eva's Monetizing Agent works that half.
Point it at the business you just bought and it finds the revenue left on the table.

It reads like a second founder.
One who reviews the week and points at the cash.

You stay the one who decides. Eva does the watching.

Book a call and I will show you: https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1
Or reply here.
```

### Wait 4 days

### Touch 6 — Day 14 — EMAIL
- Subject: `What one week looked like`
- Body:
```
One operator pointed Eva at a single market.

Eva scanned thousands of listings that week.
It handed back the 3 worth closing.
One went under contract.

You looked at three, not thousands.

That is the whole idea.
Less scanning. Better deals. Your time back.

(Illustrative — your market and numbers will differ.)

See it on your market: https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1
Or reply to this email.
```

### Wait 7 days

### Touch 7 — Day 21 — SMS
- Action: **Send SMS**
- Body:
```
Last note from me. If a deal that fits your buy box is worth 15 minutes, book here: https://api.leadconnectorhq.com/widget/booking/l9jr2HfsonQDHzg3LkC1 — or reply and we pick a time.
```

## 3. Publish
Toggle the workflow **ON** (top-right). Save.

## 4. Test
Submit the landing form (or `POST /lead/capture`) with a test email → confirm:
- contact created + tagged `eva-acquisition`
- the workflow enrolls the contact (check Workflows → enrollments, or the contact's activity timeline shows Touch 1 email queued/sent)

## Notes
- SMS touches (4, 7) require a GHL phone number / SMS enabled. This location currently has NO phone number — touches 4 & 7 will skip until you buy/assign a number (Settings → Phone System → Add Number). The 5 emails still send.
- The booking link is the Eva Demo Call calendar's public URL (step 0).
- Source copy: `modules/ghl-agent/campaign.py` (TOUCHES). This doc mirrors it exactly.
