"""
EVA Signal Intelligence — Monthly Validation Cron
Runs on the 1st of each month at 6:00 AM PT.
Queries signals_due_for_validation, asks Eva to re-evaluate each,
updates status and confidence, logs outcomes.
Version 1.0 | June 2026
"""

import json
import os
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from .signal_repository import SignalRepository


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
MODEL           = "gpt-4o-mini"    # cheap + fast for batch classification
MAX_SIGNALS     = 50               # cap per run — avoid runaway costs
NOTIFICATION_URL = os.environ.get("EVA_NOTIFY_URL", "")  # optional webhook


# ─────────────────────────────────────────────
# LLM EVALUATOR
# ─────────────────────────────────────────────

EVAL_PROMPT = """You are Eva, an AI operating system for a bootstrapped founder.

You are reviewing a signal/learning that was captured from a morning brief.
Your job: evaluate if this signal is still true, partially true, outdated, or false
based on what you know about current trends (as of {today}).

Signal:
  Title: {title}
  Body: {body}
  Source: {source} | Type: {signal_type}
  Captured: {opened_at}
  Confidence at capture: {confidence}
  Domain: {domain}
  Applies to: {applies_to}

Return a JSON object with:
{{
  "verdict": "still_true" | "partially_true" | "false" | "outdated" | "needs_more_data",
  "new_confidence": 0.0–1.0,
  "evidence": "one sentence explaining why (cite data point or trend if possible)",
  "recommended_action": "keep_active" | "close_validated" | "close_invalidated" | "update_confidence"
}}

Only return the JSON. No other text."""


def evaluate_signal_with_llm(signal: Dict) -> Dict:
    """
    Ask the LLM to evaluate a single signal.
    Returns dict: {verdict, new_confidence, evidence, recommended_action}
    Falls back to 'needs_more_data' on error.
    """
    if not OPENAI_API_KEY:
        return {
            "verdict": "needs_more_data",
            "new_confidence": signal.get("confidence", 0.7),
            "evidence": "LLM not configured — manual review required",
            "recommended_action": "keep_active",
        }

    prompt = EVAL_PROMPT.format(
        today=datetime.utcnow().strftime("%B %d, %Y"),
        title=signal.get("title", ""),
        body=signal.get("body", ""),
        source=signal.get("source", ""),
        signal_type=signal.get("signal_type", ""),
        opened_at=signal.get("opened_at", ""),
        confidence=signal.get("confidence", 0.7),
        domain=signal.get("domain", "[]"),
        applies_to=signal.get("applies_to", "[]"),
    )

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        content = content.strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[EVA] LLM eval failed for signal {signal.get('id')}: {e}")
        return {
            "verdict": "needs_more_data",
            "new_confidence": signal.get("confidence", 0.7),
            "evidence": f"Eval error: {str(e)[:80]}",
            "recommended_action": "keep_active",
        }


# ─────────────────────────────────────────────
# MAIN VALIDATION RUN
# ─────────────────────────────────────────────

def run_monthly_validation() -> Dict:
    """
    Main entry point for the monthly validation cron.
    1. Fetch all signals due for validation
    2. For each: ask LLM to evaluate
    3. Apply verdict: keep, close (validated/invalidated), or update confidence
    4. Log everything in signal_validations
    5. Return summary for notification
    """
    repo = SignalRepository()
    due  = repo.due_for_validation()

    if not due:
        return {
            "run_date": datetime.utcnow().isoformat(),
            "signals_reviewed": 0,
            "message": "No signals due for validation.",
        }

    # Cap batch size
    batch = due[:MAX_SIGNALS]
    print(f"[EVA Monthly Validation] {len(batch)} signals to review (of {len(due)} due)")

    results = {
        "run_date": datetime.utcnow().isoformat(),
        "signals_reviewed": len(batch),
        "kept_active": 0,
        "closed_validated": 0,
        "closed_invalidated": 0,
        "confidence_updated": 0,
        "needs_more_data": 0,
        "errors": 0,
        "details": [],
    }

    for signal in batch:
        signal_id = signal["id"]
        print(f"  Evaluating: {signal['title'][:60]}...")

        try:
            eval_result = evaluate_signal_with_llm(signal)
            verdict     = eval_result.get("verdict", "needs_more_data")
            new_conf    = eval_result.get("new_confidence")
            evidence    = eval_result.get("evidence", "")
            action      = eval_result.get("recommended_action", "keep_active")

            if action == "close_validated":
                repo.close(signal_id, reason="outcome_proved", outcome_note=evidence, final_status="validated")
                results["closed_validated"] += 1
                taken = "closed_validated"

            elif action == "close_invalidated":
                repo.close(signal_id, reason="outcome_disproved", outcome_note=evidence, final_status="invalidated")
                results["closed_invalidated"] += 1
                taken = "closed_invalidated"

            elif action == "update_confidence" and new_conf is not None:
                repo.validate(signal_id, verdict=verdict, evidence=evidence,
                              new_confidence=new_conf, validator="monthly_cron")
                results["confidence_updated"] += 1
                taken = "confidence_updated"

            else:
                # keep_active or needs_more_data
                repo.validate(signal_id, verdict=verdict, evidence=evidence,
                              new_confidence=new_conf, validator="monthly_cron")
                results["kept_active"] += 1
                taken = "kept_active"

            if verdict == "needs_more_data":
                results["needs_more_data"] += 1

            results["details"].append({
                "id": signal_id,
                "title": signal["title"][:60],
                "verdict": verdict,
                "action": taken,
                "evidence": evidence[:100] if evidence else "",
            })

        except Exception as e:
            print(f"  [ERROR] {signal_id}: {e}")
            results["errors"] += 1
            results["details"].append({
                "id": signal_id,
                "title": signal.get("title", "")[:60],
                "verdict": "error",
                "action": "skipped",
                "evidence": str(e)[:80],
            })

    # Final stats
    final_stats = repo.stats()
    results["db_stats"] = final_stats

    _send_validation_notification(results)
    return results


# ─────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────

def _send_validation_notification(results: Dict) -> None:
    """Build a compact notification for Vineet."""
    lines = [
        f"EVA Monthly Signal Validation — {datetime.utcnow().strftime('%B %Y')}",
        f"",
        f"Reviewed: {results['signals_reviewed']} signals",
        f"✓ Validated: {results['closed_validated']}",
        f"✗ Invalidated: {results['closed_invalidated']}",
        f"↑ Confidence updated: {results['confidence_updated']}",
        f"⟳ Kept active: {results['kept_active']}",
        f"? Needs more data: {results['needs_more_data']}",
    ]

    if results["errors"]:
        lines.append(f"⚠ Errors: {results['errors']}")

    # Top invalidated (opinion changes to highlight)
    invalidated = [d for d in results["details"] if d["action"] == "closed_invalidated"]
    if invalidated:
        lines.append(f"\nOPINION CHANGES:")
        for item in invalidated[:3]:
            lines.append(f"  ✗ {item['title']} — {item['evidence']}")

    # Active DB count
    db = results.get("db_stats", {})
    lines.append(f"\nDB: {db.get('active',0)} active · {db.get('total',0)} total signals")

    body = "\n".join(lines)
    print("\n[EVA Monthly Validation Notification]")
    print(body)

    # Future: post to in-app notification via API
    # if NOTIFICATION_URL:
    #     httpx.post(NOTIFICATION_URL, json={"title": "EVA Signal Validation", "body": body})


# ─────────────────────────────────────────────
# ENTRY POINT (called by pplx cron)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    results = run_monthly_validation()
    print("\n--- Validation Summary ---")
    print(json.dumps({k: v for k, v in results.items() if k != "details"}, indent=2))
