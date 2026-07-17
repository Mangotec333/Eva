"""Tests for the source adapter registry."""

import pytest

from sources import (
    ACTIVATED_SOURCES,
    ADAPTERS,
    SEEDS,
    get_adapter,
    list_sources,
    normalize_category,
    trust_level_for,
)


def test_required_live_adapters_present():
    for key in ("empire_flippers", "acquire_com", "flippa", "bizbuysell"):
        assert key in ADAPTERS


def test_activated_sources_are_now_live_adapters():
    for key in ("quietlight", "fe_international", "websiteclosers",
                "investors_club", "motion_invest", "dealslide", "businessesforsale"):
        assert key in ADAPTERS
        assert ADAPTERS[key].live is True
        assert key in ACTIVATED_SOURCES
    # No sources remain seed-only after activation.
    assert SEEDS == {}


def test_trust_levels_match_spec():
    assert trust_level_for("empire_flippers") == "high"
    for key in ("acquire_com", "flippa", "bizbuysell"):
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


def test_activated_adapter_can_normalize_payloads():
    [deal] = get_adapter("quietlight").to_raw_deals(
        [{"listing_id": "1", "name": "QL SaaS", "annual_multiple": 3.0}])
    assert deal.source == "quietlight"
    assert deal.annual_multiple == 3.0


def test_unknown_source_raises():
    with pytest.raises(KeyError):
        get_adapter("does_not_exist")


def test_category_normalization():
    assert normalize_category("Micro-SaaS") == "SaaS"
    assert normalize_category("affiliate blog") == "Content"
    assert normalize_category("Shopify store") == "E-commerce"


def test_list_sources_all_activated_are_live():
    srcs = list_sources()
    assert srcs["flippa"]["live"] is True
    # Previously seed-only sources are now live with a feed_url + access hint.
    assert srcs["quietlight"]["live"] is True
    assert srcs["quietlight"]["feed_url"]
    assert srcs["investors_club"]["access"] == "gated"
