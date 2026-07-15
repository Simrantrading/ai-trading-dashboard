"""Smoke checks for portfolio add-suggestions."""

from logic.portfolio import DEFAULT_HOLDINGS, analyze_holdings, suggest_additions


def test_default_holdings_sum():
    assert sum(DEFAULT_HOLDINGS.values()) > 10000


def test_analyze_holdings_structure():
    result = analyze_holdings({"AAPL": 5000, "MSFT": 5000})
    assert result["total_value"] == 10000
    assert len(result["holdings"]) == 2
    assert "theme_weights" in result


def test_suggest_additions_returns_ranked_list():
    result = suggest_additions({"SOXL": 9000, "INTC": 1000}, limit=3)
    assert "suggestions" in result
    assert "risks" in result
    assert any("Semiconductor" in r or "Leveraged" in r for r in result["risks"])
    for item in result["suggestions"]:
        assert "symbol" in item
        assert "add_score" in item
        assert item["symbol"] not in {"SOXL", "INTC"}
