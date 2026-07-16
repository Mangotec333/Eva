"""Tests for the credit-saving scoring gate."""

from pipeline_models import RawDeal
from scoring_gate import evaluate, is_us_eligible


def _deal(**kw):
    base = dict(id="x", source="flippa", listing_id="1", trust_level="medium")
    base.update(kw)
    return RawDeal(**base)


def test_us_eligible_any_signal():
    assert is_us_eligible(_deal(registration_country="US"))
    assert is_us_eligible(_deal(primary_customer_market="US"))
    assert is_us_eligible(_deal(seller_location="US"))
    assert not is_us_eligible(_deal(seller_location="FR"))


def test_medium_trust_non_us_is_skipped():
    d = evaluate(_deal(seller_location="FR"))
    assert d.should_score is False
    assert "not US-eligible" in d.reason


def test_medium_trust_us_is_scored():
    d = evaluate(_deal(seller_location="US"))
    assert d.should_score is True
    assert "US-eligible" in d.reason
    assert "seller_location=US" in d.reason


def test_high_trust_bypasses_us_filter():
    d = evaluate(_deal(trust_level="high", seller_location="FR"))
    assert d.should_score is True
    assert "bypasses US filter" in d.reason


def test_closed_comp_never_scored_regardless_of_geo():
    d = evaluate(_deal(trust_level="high", seller_location="US", is_closed=True))
    assert d.should_score is False
    assert "closed comp" in d.reason
