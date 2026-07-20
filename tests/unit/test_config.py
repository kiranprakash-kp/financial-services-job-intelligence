"""Config loading is evidence-of-record for the verified extraction strategy."""

from __future__ import annotations

from job_intelligence.config import load_companies_config


def test_all_three_companies_present_and_active() -> None:
    cfg = load_companies_config()
    keys = set(cfg.companies)
    assert {"wells_fargo", "goldman_sachs", "bny"} <= keys
    assert set(cfg.active_keys()) >= {"wells_fargo", "goldman_sachs", "bny"}


def test_lookup_by_key_or_code() -> None:
    cfg = load_companies_config()
    assert cfg.get("wells_fargo").code == "WELLS_FARGO"
    assert cfg.get("WELLS_FARGO").name == "Wells Fargo"


def test_verified_strategies() -> None:
    cfg = load_companies_config()
    assert cfg.get("wells_fargo").extraction_strategy == "server_html"
    assert cfg.get("goldman_sachs").extraction_strategy == "direct_api"
    assert cfg.get("bny").extraction_strategy == "direct_api"
    # GraphQL endpoint recorded for GS; Oracle REST base for BNY.
    assert "api-higher.gs.com" in cfg.get("goldman_sachs").settings["graphql_url"]
    assert "recruitingCEJobRequisitions" in cfg.get("bny").settings["requisitions_resource"]


def test_proxy_disabled_everywhere() -> None:
    cfg = load_companies_config()
    assert all(not c.proxy_enabled for c in cfg.companies.values())
