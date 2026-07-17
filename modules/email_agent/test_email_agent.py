"""Baseline offline tests for email_agent pure logic + brief generation (no network)."""

import os
import tempfile

import email_agent


def test_extract_urls_keeps_deal_domains_only():
    text = ("Check https://www.empireflippers.com/listing/123 and "
            "https://random-tracking.example.com/x and "
            "https://flippa.com/deal/9")
    urls = email_agent.extract_urls(text)
    assert any("empireflippers" in u for u in urls)
    assert any("flippa" in u for u in urls)
    assert all("random-tracking" not in u for u in urls)


def test_extract_urls_empty():
    assert email_agent.extract_urls("") == []


def test_classify_email_deal_flow():
    assert email_agent.classify_email("Business for sale", "x@y.com", "asking price $1M") == "DEAL_FLOW"


def test_classify_email_broker_sender():
    assert email_agent.classify_email("hi", "deals@empireflippers.com", "") == "DEAL_FLOW"


def test_classify_email_newsletter_and_other():
    assert email_agent.classify_email("Weekly digest", "n@y.com", "") == "NEWSLETTER"
    assert email_agent.classify_email("random subject", "a@b.com", "hello") == "OTHER"


def test_run_email_agent_empty_brief(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(email_agent, "DB_PATH", os.path.join(tmp, "deals.db"))
    monkeypatch.setattr(email_agent, "BRIEF_PATH", os.path.join(tmp, "brief.json"))
    brief = email_agent.run_email_agent(emails=[], calendar_events=[])
    assert brief["summary"]["emails_scanned"] == 0
    assert brief["summary"]["new_deals_found"] == 0
