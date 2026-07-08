"""
Offline end-to-end validation of the connected agent loop.
==========================================================

Exercises the whole wiring WITHOUT any network or API key:

  * NoopClaudeClient          -> reasoning brain degrades safely (tokens=0)
  * NoopPerplexityClient      -> enrichment degrades to an L0 record
  * MockPerplexityClient      -> enrichment mapping path (Statista/CB/Similarweb)
  * DealAnalyzerAgent loop    -> observe -> reason -> act completes, scores land
  * run_pipeline / run_loop   -> the loop actually iterates
  * directive_sync            -> a learnings entry is appended + versioned

No network, no LLM, no pip. Run:  python test_loop.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
_AGENT_DIR = os.path.join(_REPO_ROOT, "modules", "deal-analyzer-agent")
for _p in (_REPO_ROOT, _AGENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import memory  # noqa: E402  (from the agent module dir)
from agent import DealAnalyzerAgent  # noqa: E402
from enrichment import NicheCache, gather_enrichment, make_enricher  # noqa: E402
from models import DealV7  # noqa: E402

from services.directive_sync import LEARNINGS_HEADER, sync_directive  # noqa: E402
from services.remote.claude import NoopClaudeClient  # noqa: E402
from services.remote.perplexity import (  # noqa: E402
    MockPerplexityClient,
    NoopPerplexityClient,
    PerplexityResponse,
    PerplexityStatus,
)


def _mk_deal(name, category, monthly_net, annual_multiple, asking_price, age_years):
    ts = datetime.now(timezone.utc).isoformat()
    return DealV7(
        id=str(uuid.uuid4()), source="manual", listing_id="", url="",
        name=name, category=category, monthly_net=monthly_net,
        annual_multiple=annual_multiple, asking_price=asking_price,
        age_years=age_years, discovered_at=ts, created_at=ts, updated_at=ts,
    )


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="eva_loop_")
    db_path = os.path.join(tmp, "memory.db")
    cache = NicheCache(path=os.path.join(tmp, "cache.db"))

    print("=" * 72)
    print("EVA connected-loop offline validation")
    print("=" * 72)

    # --- (a) sample deal ---------------------------------------------------
    deal = _mk_deal("Acme B2B Analytics SaaS", "SaaS", 12000, 3.2, 460000, 4.0)
    print(f"\n[a] sample deal: {deal.name} (${deal.monthly_net:,.0f}/mo, "
          f"{deal.annual_multiple:g}x, {deal.age_years:g}yr)")

    # --- enrichment: Noop path degrades to L0 ------------------------------
    noop_enr = gather_enrichment("b2b analytics saas", client=NoopPerplexityClient(), cache=cache)
    assert noop_enr.research_level == "L0", noop_enr.research_level
    assert noop_enr.to_enrichment_kwargs() == {}, "L0 must project to empty kwargs"
    print(f"[enrich] Noop transport -> research_level={noop_enr.research_level} (empty, safe)")

    # --- enrichment: Mock path maps a research result ----------------------
    canned = PerplexityResponse(
        task_id="x", status=PerplexityStatus.COMPLETED,
        result={
            "tam_usd": 8.0e9, "sam_usd": 1.2e9, "market_growth_rate_pct": 14.0,
            "tam_source_url": "https://statista.example/saas", "tam_confidence_score": 70,
            "named_competitors": ["Looker", "Mode", "Metabase"],
            "estimated_market_share": 3.5, "niche_growth_score": 68,
            "market_fragmentation_score": 55, "confidence_overall": 66,
            "source_urls": [{"url": "https://cbinsights.example", "label": "CB Insights"}],
        },
    )
    mock_client = MockPerplexityClient(responder=canned)
    mock_enr = gather_enrichment("fintech b2b saas", client=mock_client, cache=cache)
    assert mock_enr.research_level == "L1", mock_enr.research_level
    assert mock_enr.tam_usd == 8.0e9 and mock_enr.named_competitors, mock_enr
    print(f"[enrich] Mock transport -> research_level={mock_enr.research_level}, "
          f"tam=${mock_enr.tam_usd:,.0f}, competitors={mock_enr.named_competitors}")
    # cache hit on second call (no re-research)
    again = gather_enrichment("fintech b2b saas", client=MockPerplexityClient(fail=True), cache=cache)
    assert again.tam_usd == 8.0e9, "second call must hit cache, not the failing client"
    print("[enrich] second call served from NicheCache (no re-research)")

    # --- (b) run the agent loop with Noop brain ----------------------------
    enricher = make_enricher(client=mock_client, cache=cache)
    agent = DealAnalyzerAgent(brain=NoopClaudeClient(), db_path=db_path, enrich_fn=enricher)
    result = agent.run_deal(deal)

    scored = result["deal"]
    print("\n[b] agent.run_deal() with NoopClaudeClient + Mock enrichment:")
    print(f"    overall_score        : {scored['overall_score']}")
    print(f"    category_v2          : {scored['category_v2']}")
    print(f"    cashflow / profit    : {scored['cashflow_score']} / {scored['profit_potential_score']}")
    print(f"    exit / moat / tam    : {scored['exit_potential_score']} / "
          f"{scored['moat_score']} / {scored['tam_score']}")
    print(f"    research_level       : {scored['research_level']}")
    print(f"    tokens (brain)       : {result['tokens']}")
    print(f"    advisory             : {result['advisory']}")

    # --- (c) assertions ----------------------------------------------------
    assert result["run_id"], "run must be persisted"
    assert 0.0 <= scored["overall_score"] <= 10.0, "overall_score out of range"
    assert scored["overall_score"] > 0, "deterministic core must produce a score"
    assert result["tokens"] == 0, "Noop brain must log zero tokens"
    assert scored["tam_score"] > 0, "Mock enrichment TAM should lift tam_score"

    runs = memory.list_runs(deal_id=scored["id"], path=db_path)
    assert len(runs) == 1, f"expected 1 agent_run, got {len(runs)}"
    assert memory.get_deal(scored["id"], path=db_path) is not None, "deal must persist"
    print(f"\n[c] agent_run logged: id={runs[0]['id']}, tokens={runs[0]['tokens']}")

    # --- run_pipeline: batch iterates --------------------------------------
    batch = [
        _mk_deal("Content Site — Pet Care", "Content", 3000, 2.5, 90000, 6.0),
        _mk_deal("Shopify Store — Home Goods", "Physical Ecommerce", 8000, 2.8, 260000, 3.0),
    ]
    pipeline_results = agent.run_pipeline(batch)
    assert len(pipeline_results) == 2, pipeline_results
    assert all("error" not in r for r in pipeline_results), pipeline_results
    print(f"[pipeline] run_pipeline scored {len(pipeline_results)} deals: "
          + ", ".join(f"{r['deal']['name']}={r['deal']['overall_score']}" for r in pipeline_results))

    # --- run_loop: bounded, real iteration ---------------------------------
    pending = [_mk_deal("SaaS — Scheduling", "SaaS", 5000, 3.0, 180000, 2.0)]

    def _source():
        # yields one batch on the first poll, then nothing (loop keeps ticking)
        return [pending.pop(0)] if pending else []

    loop_summary = agent.run_loop(_source, interval_s=0, max_iterations=3, sleep=lambda _s: None)
    assert loop_summary["iterations"] == 3, loop_summary
    assert loop_summary["scored"] == 1, loop_summary
    print(f"[loop] run_loop ran {loop_summary['iterations']} iterations, "
          f"scored {loop_summary['scored']} deal(s)")

    # --- directive-sync append ---------------------------------------------
    mod_dir = os.path.join(tmp, "modules")
    os.makedirs(os.path.join(mod_dir, "deal-analyzer-agent"))
    dpath = os.path.join(mod_dir, "deal-analyzer-agent", "directive.md")
    open(dpath, "w", encoding="utf-8").write("# Deal Analyzer Agent — Live Directive\n\n## LEARNINGS\n")

    sync = sync_directive(
        "deal-analyzer-agent",
        {"source": "test_loop", "deal_id": scored["id"], "outcome": "LOI",
         "lesson": "High TAM + strong cashflow correlated with LOI.",
         "weight_delta": {"tam": 0.01}},
        modules_dir=mod_dir,
    )
    body = open(dpath, encoding="utf-8").read()
    assert LEARNINGS_HEADER in body, "auto-synced section must exist"
    assert scored["id"] in body, "synced entry must reference the deal"

    sync_db = os.path.join(mod_dir, "deal-analyzer-agent", "memory.db")
    versions = memory.get_latest_directive(path=sync_db)
    assert versions is not None and versions["version"] == sync["version"], versions
    print(f"\n[sync] directive appended under '{LEARNINGS_HEADER}', "
          f"version={sync['version']}")

    print("\n" + "=" * 72)
    print("ALL ASSERTIONS PASSED  (deterministic core + Noop brains, fully offline)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
