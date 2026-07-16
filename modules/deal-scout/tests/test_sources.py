"""Tests for the source adapter registry."""

import pytest

from sources import ADAPTERS, SEEDS, get_adapter, list_sources, normalize_category, trust_level_for


def test_required_live_adapters_present():
    for key in ("empire_flippers", "acquire", "flippa", "bizbuysell"):
        assert key in ADAPTERS


def test_required_seed_sources_present():
    for key in ("quietlight", "fe_international", "websiteclosers",
                "investors_club", "motion_invest", "dealslide", "businessesforsale"):
        assert key in SEEDS


def test_trust_levels_match_spec():
    assert trust_level_for("empire_flippers") == "high"
    for key in ("acquire", "flippa", "bizbuysell"):
        assert trust_level_for(key) == "medium"


def test_ef_multiple_normalized_to_annual():
    # EF quotes monthly multiples → adapter divides by 12.
    [deal] = get_adapter("empire_flippers").to_raw_deals(
        [{"listing_id": "1", "name": "x", "multiple": 24.0, "monthly_net": 1000}])
    assert deal.annual_multiple == 2.0
    assert deal.trust_level == "high"


def test_flippa_multiple_kept_as_is():
    [deal] = get_adapter("flippa").to_raw_deals(
        [{"listing_id": "1", "annual_multiple": 2.5}])
    assert deal.annual_multiple == 2.5


def test_seed_adapter_cannot_scrape_yet():
    with pytest.raises(NotImplementedError):
        get_adapter("quietlight").to_raw_deals([{"listing_id": "1"}])


def test_category_normalization():
    assert normalize_category("Micro-SaaS") == "SaaS"
    assert normalize_category("affiliate blog") == "Content"
    assert normalize_category("Shopify store") == "E-commerce"


def test_list_sources_flags_live_vs_seed():
    srcs = list_sources()
    assert srcs["flippa"]["live"] is True
    assert srcs["quietlight"]["live"] is False
