"""The recon scorer must flag job-bearing JSON and find total-count hints."""

from __future__ import annotations

from job_intelligence.extraction.network_discovery import _deep_get_int, _score_json


def test_scores_job_like_payload_high() -> None:
    payload = {
        "totalCount": 1254,
        "items": [{"jobId": "1", "title": "Engineer", "location": "NYC", "description": "..."}],
    }
    score, matched, total = _score_json(payload)
    assert score >= 3
    assert "totalcount" in matched and "items" in matched
    assert total == 1254


def test_scores_unrelated_payload_low() -> None:
    score, matched, total = _score_json({"theme": "dark", "locale": "en"})
    assert score == 0
    assert matched == []
    assert total is None


def test_deep_get_int_finds_nested_total() -> None:
    assert _deep_get_int({"items": [{"TotalJobsCount": 1689}]}, "TotalJobsCount") == 1689
    assert _deep_get_int({"a": {"b": {"c": 5}}}, "missing") is None
