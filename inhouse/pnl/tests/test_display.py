"""Testing module for :py:mod:`widgets.inhouse.pnl.display` module."""

import pytest

from widgets.inhouse.pnl.display import (
    alert_presets,
    asset_label,
    event_row,
    money,
    percent,
    period_summary,
    quantity,
    signed_money,
    summary,
    table_row,
    tone,
    unit_price,
)


def _engine_row(**kwargs):
    row = {
        "asset": "31566704",
        "lp": False,
        "name": "USDC",
        "unit": "USDC",
        "decimals": 6,
        "quantity": 2_500_000,
        "average_cost": 0.9,
        "price": 1.0,
        "value": 2_500_000,
        "cost": 2_250_000,
        "unrealized": 250_000,
        "realized": -10_000,
        "income": 0,
        "expenses": 0,
        "total": 240_000,
        "return": 0.1,
        "missing_quantity": 0,
        "unpriced": 0,
    }
    row.update(kwargs)
    return row


class TestPnlDisplayFormatting:
    """Testing class for the number formatting helpers."""

    @pytest.mark.parametrize(
        "value,currency,expected",
        [
            (None, "usd", "—"),
            (1_234_560_000, "usd", "$1,234.56"),
            (-2_500_000, "usd", "-$2.50"),
            (1_500_000, "algo", "1.50 ALGO"),
        ],
    )
    def test_pnl_display_money(self, value, currency, expected):
        assert money(value, currency) == expected

    def test_pnl_display_signed_money(self):
        assert signed_money(1_000_000, "usd") == "+$1.00"
        assert signed_money(-1_000_000, "usd") == "-$1.00"
        assert signed_money(0, "usd") == "$0.00"
        assert signed_money(None, "usd") == "—"

    def test_pnl_display_quantity(self):
        assert quantity(1_234_567, 6) == "1.234567"
        assert quantity(5, 0) == "5"
        assert quantity(10**12, 10) == "100.000000"
        assert quantity(None, 6) == "—"

    def test_pnl_display_unit_price(self):
        assert unit_price(0.25, 6, "usd") == "$0.250000"
        assert unit_price(40_000, 0, "algo") == "0.040000 ALGO"
        assert unit_price(1.5, 6, "usd") == "$1.50"
        assert unit_price(None, 6, "usd") == "—"

    def test_pnl_display_percent_and_tone(self):
        assert percent(0.123) == "+12.3%"
        assert percent(-0.5) == "-50.0%"
        assert percent(None) == "—"
        assert (tone(1), tone(-1), tone(0), tone(None)) == (
            "pnl-gain",
            "pnl-loss",
            "",
            "",
        )


class TestPnlDisplayRows:
    """Testing class for the row and summary builders."""

    def test_pnl_display_asset_label(self):
        assert asset_label({"asset": "LP123", "lp": True}) == "LP 123"
        assert asset_label({"asset": "5", "unit": "", "name": "Five"}) == "Five"
        assert asset_label({"asset": "5", "unit": "", "name": ""}) == "#5"

    def test_pnl_display_table_row(self):
        row = table_row(_engine_row(), "usd")
        assert row["label"] == "USDC"
        assert row["quantity"] == "2.500000"
        assert row["average_cost"] == "$0.900000"
        assert row["value"] == "$2.50"
        assert (row["unrealized"], row["unrealized_tone"]) == ("+$0.25", "pnl-gain")
        assert (row["realized"], row["realized_tone"]) == ("-$0.01", "pnl-loss")
        assert row["income"] == ""
        assert row["incomplete"] is False
        assert row["held"] is True

    def test_pnl_display_table_row_no_market_is_not_incomplete(self):
        row = table_row(_engine_row(unpriced=130, no_market=True), "usd")
        assert row["incomplete"] is False
        assert row["no_market"] is True

    def test_pnl_display_table_row_incomplete_and_closed(self):
        row = table_row(_engine_row(quantity=0, missing_quantity=3), "algo")
        assert row["incomplete"] is True
        assert row["held"] is False

    def test_pnl_display_summary(self):
        totals = {
            "total": 3_000_000,
            "invested": 12_000_000,
            "realized": 1_000_000,
            "unrealized": 2_500_000,
            "income": 500_000,
            "expenses": 1_000_000,
            "value": 14_000_000,
            "cost": 11_000_000,
            "unvalued_assets": 1.0,
        }
        returned = summary(totals, "usd")
        assert returned["total"] == "+$3.00"
        assert returned["return"] == "+25.0%"
        assert returned["expenses"] == "$1.00"
        assert returned["unvalued_assets"] == 1
        assert returned["assets_missing_history"] == 0
        assert returned["no_market_assets"] == 0
        assert summary({"total": 0.0}, "usd")["return"] == "—"

    def test_pnl_display_event_row(self):
        event = {
            "date": 1_700_000_000,
            "id": "TXID",
            "asset": "5",
            "kind": "swap",
            "quantity": -250,
            "value": 1_000_000,
            "cost": 800_000,
            "realized": 200_000,
        }
        row = event_row(event, 2, "usd")
        assert row["date"] == "14 Nov 2023 22:13"
        assert row["kind"] == "Swap"
        assert row["quantity"] == "-2.50"
        assert row["realized_tone"] == "pnl-gain"
        assert row["unpriced"] is False
        position = event_row({**event, "kind": "position_in", "value": None}, 2, "usd")
        assert position["unpriced"] is False
        assert event_row({**event, "value": None}, 2, "usd")["unpriced"] is True

    def test_pnl_display_period_summary(self):
        period = {
            "pnl": -2_000_000,
            "return": -0.1,
            "start_value": 20_000_000,
            "end_value": 19_000_000,
            "net_flows": 1_000_000,
            "unvalued_assets": 2,
        }
        assert period_summary(period, "usd") == {
            "pnl": "-$2.00",
            "pnl_tone": "pnl-loss",
            "return": "-10.0%",
            "start_value": "$20.00",
            "end_value": "$19.00",
            "net_flows": "+$1.00",
            "unvalued_assets": 2,
        }


class TestPnlDisplayAlertPresets:
    """Testing class for :py:func:`...pnl.display.alert_presets`."""

    def test_pnl_display_alert_presets_from_average_cost(self):
        row = _engine_row(asset="5", decimals=2, average_cost=20_000, price=15_000)
        assert alert_presets(row) == [
            {"label": "Break-even", "direction": "up", "threshold": "2"},
            {"label": "+25%", "direction": "up", "threshold": "2.5"},
            {"label": "+50%", "direction": "up", "threshold": "3"},
            {"label": "-20%", "direction": "down", "threshold": "1.6"},
        ]

    def test_pnl_display_alert_presets_break_even_below_price(self):
        row = _engine_row(asset="5", decimals=0, average_cost=1_000_000, price=3_000_000)
        assert alert_presets(row)[0] == {
            "label": "Break-even",
            "direction": "down",
            "threshold": "1",
        }
        row = _engine_row(asset="5", decimals=0, average_cost=1_000_000, price=None)
        assert alert_presets(row)[0]["direction"] == "up"

    @pytest.mark.parametrize(
        "changes",
        [
            {"asset": "0"},
            {"lp": True},
            {"no_market": True},
            {"average_cost": None},
            {"quantity": 0},
        ],
    )
    def test_pnl_display_alert_presets_none(self, changes):
        row = _engine_row(asset="5")
        row.update(changes)
        assert alert_presets(row) == []

    def test_pnl_display_alert_presets_skip_thresholds_too_small(self):
        row = _engine_row(asset="5", decimals=0, average_cost=1e-8)
        assert alert_presets(row) == []
