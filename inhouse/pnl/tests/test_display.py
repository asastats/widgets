"""Testing module for :py:mod:`widgets.inhouse.pnl.display` module."""

import pytest

from widgets.inhouse.pnl.display import (
    alert_presets,
    asset_label,
    chart,
    concentration,
    drawdown,
    event_row,
    issues,
    money,
    percent,
    period_summary,
    processed_iso,
    processed_time,
    quantity,
    reprocess_changes,
    signed_money,
    summary,
    table_row,
    tone,
    unit_price,
    winners_and_losers,
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


class TestPnlDisplayIssues:
    """Testing class for the assets behind the coverage notes."""

    def test_pnl_display_issues_grouped_largest_first(self):
        assets = [
            _engine_row(asset="1", name="Small", value=None, cost=1_000_000),
            _engine_row(asset="2", name="Big", value=None, cost=9_000_000, unpriced=1),
            _engine_row(asset="3", name="Pool", lp=True, value=None, cost=5_000_000),
            _engine_row(
                asset="4", name="Sold", missing_quantity=1_500_000, missing_proceeds=3e6
            ),
            _engine_row(asset="5", name="Two", unpriced=2),
            _engine_row(asset="6", name="Spam", value=None, unpriced=4, no_market=True),
            _engine_row(asset="7", name="Gone", quantity=0, value=None),
        ]
        unvalued, missing, unpriced = issues(assets, "usd")
        assert (unvalued["title"], unvalued["total"], unvalued["more"]) == (
            "Holdings without a current price",
            3,
            0,
        )
        assert [(item["name"], item["detail"], item["effect"]) for item in unvalued["items"]] == [
            ("Big", "No current price", "$9.00"),
            ("LP token 3", "LP token without a pool price", "$5.00"),
            ("Small", "No current price", "$1.00"),
        ]
        assert [(item["label"], item["detail"], item["effect"]) for item in missing["items"]] == [
            ("USDC", "1.500000 units", "$3.00")
        ]
        assert [item["detail"] for item in unpriced["items"]] == ["2 events", "1 event"]

    def test_pnl_display_issues_shows_the_first_ones(self, mocker):
        mocker.patch("widgets.inhouse.pnl.display.ISSUES_SHOWN", 2)
        assets = [_engine_row(asset=str(i), unpriced=i) for i in range(1, 6)]
        (group,) = issues(assets, "usd")
        assert (len(group["items"]), group["total"], group["more"]) == (2, 5, 3)

    def test_pnl_display_issues_without_any(self):
        assert issues([_engine_row()], "usd") == []


class TestPnlDisplayFormatting:
    """Testing class for the number formatting helpers."""

    @pytest.mark.parametrize(
        "value,currency,expected",
        [
            (None, "usd", "—"),
            (1_234_560_000, "usd", "$1,234.56"),
            (-2_500_000, "usd", "-$2.50"),
            (1_500_000, "algo", "1.50 ALGO"),
            (-2_500_000, "eur", "-€2.50"),
            (1_500_000, "chf", "1.50 CHF"),
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
        assert unit_price(1.5, 6, "eur") == "€1.50"
        assert unit_price(1.5, 6, "chf") == "1.50 CHF"

    def test_pnl_display_unit_price_below_a_millionth(self):
        assert unit_price(0.0287, 0, "usd") == "$0.0000000287"
        assert unit_price(0.00000099, 6, "algo") == "0.000000990 ALGO"
        assert unit_price(1e-15, 0, "usd") == "$0.000000000000"
        assert unit_price(0, 6, "usd") == "$0.000000"

    def test_pnl_display_unit_price_sign_before_the_symbol(self):
        assert unit_price(-0.0287, 0, "usd") == "-$0.0000000287"
        assert unit_price(-1.5, 6, "eur") == "-€1.50"
        assert unit_price(-1e-15, 0, "usd") == "$0.000000000000"

    def test_pnl_display_percent_and_tone(self):
        assert percent(0.123) == "+12.3%"
        assert percent(-0.5) == "-50.0%"
        assert percent(None) == "—"
        assert (tone(10_000), tone(-10_000), tone(4_999), tone(None)) == (
            "pnl-gain",
            "pnl-loss",
            "",
            "",
        )
        assert tone(0.001, 0.0005) == "pnl-gain"
        assert percent(0.0001) == "0.0%"
        assert percent(-0.0004) == "0.0%"

    def test_pnl_display_amounts_rounding_to_zero_are_plain(self):
        assert money(-4_000, "usd") == "$0.00"
        assert signed_money(4_000, "usd") == "$0.00"
        assert signed_money(-6_000, "usd") == "-$0.01"
        assert signed_money(6_000, "algo") == "+0.01 ALGO"


class TestPnlDisplayRows:
    """Testing class for the row and summary builders."""

    def test_pnl_display_asset_label(self):
        assert asset_label({"asset": "1041116468", "lp": True}) == "LP 1041116468"
        assert (
            asset_label({"asset": "55", "lp": True, "pool": "Tinyman2 LP ALGO/U"})
            == "Tinyman2 LP ALGO/U"
        )
        lp_row = table_row(_engine_row(lp=True, pool="Pact LP ALGO/U", name="PLP"), "usd")
        assert (lp_row["label"], lp_row["name"]) == ("Pact LP ALGO/U", "LP token 31566704")
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
        assert row["illiquid"] is False
        assert table_row(_engine_row(illiquid=True), "usd")["illiquid"] is True
        assert row["nft"] is False
        assert table_row(_engine_row(nft=True), "usd")["nft"] is True
        assert (row["fees"], row["divergence"]) == ("", "")
        assert row["farm_income"] == ""
        farm = table_row(
            _engine_row(farm_income=3_500_000, farm_assets=["5"], farm_unpriced=0), "usd"
        )
        assert (farm["farm_income"], farm["farm_assets"]) == ("$3.50", ["5"])
        tiny = table_row(_engine_row(farm_income=4_000, farm_unpriced=0), "usd")
        assert tiny["farm_income"] == ""
        unpriced = table_row(_engine_row(farm_income=0.0, farm_unpriced=2), "usd")
        assert (unpriced["farm_income"], unpriced["farm_unpriced"]) == ("$0.00", 2)
        assert table_row(_engine_row(fees=4_000, divergence=-3_000), "usd")["fees"] == ""
        split = table_row(_engine_row(fees=4_000, divergence=-500_000), "algo")
        assert (split["fees"], split["divergence"]) == ("0.00 ALGO", "-0.50 ALGO")

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
        assert (returned["illiquid_assets"], returned["mve"]) == (0, False)
        assert returned["nft_value"] == ""
        assert summary({"total": 0.0, "nft_value": 2_500_000}, "usd")["nft_value"] == (
            "$2.50"
        )
        assert summary({"total": 0.0, "valuation": "mve"}, "usd")["mve"] is True
        assert summary({"total": 0.0}, "usd")["return"] == "—"

    def test_pnl_display_summary_against_money_brought_in(self):
        totals = {"total": -1_000_000, "inflows": 30_000_000, "outflows": 10_000_000}
        returned = summary(totals, "usd")
        assert returned["brought_in"] == "+$20.00"
        assert returned["return_brought_in"] == "-5.0%"
        taken_out = summary({"total": 1.0, "inflows": 1.0, "outflows": 3.0}, "usd")
        assert taken_out["return_brought_in"] is None
        assert summary({"total": 0.0}, "usd")["return_brought_in"] is None

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
        assert row["description"] == ""
        withdrawal = {**event, "kind": "withdrawal", "value": None, "unpriced": False}
        assert event_row(withdrawal, 2, "usd")["unpriced"] is False
        assert event_row({**event, "value": None}, 2, "usd")["unpriced"] is True
        assert event_row({**event, "description": "Pact AMM swap"}, 2, "usd")[
            "description"
        ] == "Pact AMM swap"
        assert row["deposit"] is False
        assert event_row({**event, "kind": "deposit"}, 2, "usd")["deposit"] is True
        assert event_row({**event, "kind": "own_out"}, 2, "usd")["kind"] == (
            "To your other wallet"
        )
        assert event_row({**event, "kind": "own_in"}, 2, "usd")["kind"] == (
            "From your other wallet"
        )
        position = event_row({**event, "kind": "position_in", "value": None}, 2, "usd")
        assert position["unpriced"] is False
        assert event_row({**event, "value": None}, 2, "usd")["unpriced"] is True
        assert row["link"] == ""
        assert event_row(event, 2, "usd", "allo")["link"] == (
            "https://allo.info/tx/group/TXID"
        )
        transaction = {**event, "id": "A" * 52}
        assert event_row(transaction, 2, "usd", "lora")["link"] == (
            "https://lora.algokit.io/mainnet/transaction/" + "A" * 52
        )
        group = {**event, "id": "ab/c+="}
        assert event_row(group, 2, "usd", "lora")["link"] == (
            "https://allo.info/tx/group/ab%2Fc%2B%3D"
        )

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


class TestPnlDisplayVsHold:
    """Testing class for the LP vs holding figure."""

    def test_pnl_display_vs_hold(self):
        row = table_row(_engine_row(vs_hold=-2_000_000), "usd")
        assert (row["vs_hold"], row["vs_hold_tone"]) == ("-$2.00", "pnl-loss")
        row = table_row(_engine_row(), "usd")
        assert (row["vs_hold"], row["vs_hold_tone"]) == ("", "")


class TestPnlDisplayChart:
    """Testing class for the cumulative P&L chart layout."""

    def test_pnl_display_chart_without_points(self):
        assert chart([], "usd") is None
        assert chart(None, "usd") is None

    def test_pnl_display_chart_layout(self):
        day = 86_400
        points = [
            {"date": 1_700_000_000, "pnl": 0.0, "unvalued_assets": 0},
            {"date": 1_700_000_000 + day, "pnl": -2_000_000.0, "unvalued_assets": 1},
            {"date": 1_700_000_000 + 2 * day, "pnl": 6_000_000.0},
        ]
        returned = chart(points, "usd")
        # 8 USD span over 168 units of height: zero sits three quarters down
        assert returned["zero_y"] == 132.0
        assert [(point["x"], point["y"]) for point in returned["points"]] == [
            (6.0, 132.0),
            (300.0, 174.0),
            (594.0, 6.0),
        ]
        assert returned["line"] == "6.0,132.0 300.0,174.0 594.0,6.0"
        assert returned["area"] == (
            "6.0,132.0 6.0,132.0 300.0,174.0 594.0,6.0 594.0,132.0"
        )
        assert returned["points"][1]["title"] == "15 Nov 2023: -$2.00"
        assert (returned["start"], returned["end"]) == ("14 Nov 2023", "16 Nov 2023")
        assert (returned["high"], returned["low"]) == ("+$6.00", "-$2.00")
        assert (returned["last"], returned["last_tone"]) == ("+$6.00", "pnl-gain")
        assert returned["unvalued"] == 1

    def test_pnl_display_chart_single_flat_point(self):
        returned = chart([{"date": 5, "pnl": 0.0}], "algo")
        assert returned["points"] == [
            {"x": 6.0, "y": 90.0, "title": "1 Jan 1970: 0.00 ALGO"}
        ]
        assert (returned["high"], returned["low"]) == ("0.00 ALGO", "0.00 ALGO")
        assert returned["unvalued"] == 0



class TestPnlDisplayProcessedTime:
    """Testing class for :py:func:`...pnl.display.processed_time`."""

    @pytest.mark.parametrize(
        "timestamp,expected",
        [(None, ""), (0, ""), (1_760_000_000, "9 Oct 2025, 08:53 UTC")],
    )
    def test_pnl_display_processed_time(self, timestamp, expected):
        assert processed_time(timestamp) == expected


class TestPnlDisplayProcessedIso:
    """Testing class for :py:func:`...pnl.display.processed_iso`."""

    @pytest.mark.parametrize(
        "timestamp,expected",
        [(None, ""), (0, ""), (1_760_000_000, "2025-10-09T08:53:20Z")],
    )
    def test_pnl_display_processed_iso(self, timestamp, expected):
        assert processed_iso(timestamp) == expected


class TestPnlDisplayReprocessChanges:
    """Testing class for :py:func:`...pnl.display.reprocess_changes`."""

    def test_pnl_display_reprocess_changes_without_any(self):
        assert reprocess_changes(None, [], "usd") is None

    def test_pnl_display_reprocess_changes(self):
        changes = {
            "since": 1_760_000_000,
            "assets_changed": 3,
            "cost": -2_000_000,
            "realized": 500_000,
            "income": 0.0,
            "expenses": 0.0,
            "assets": [
                {
                    "asset": "31566704",
                    "quantity": 1_500_000,
                    "cost": -2_000_000,
                    "realized": 500_000,
                    "income": 0.0,
                    "expenses": 0.0,
                },
                {
                    "asset": "99",
                    "quantity": -1,
                    "cost": 0.0,
                    "realized": 0.0,
                    "income": 0.0,
                    "expenses": 0.0,
                },
            ],
        }
        returned = reprocess_changes(changes, [_engine_row()], "usd")
        assert returned["since"] == "9 Oct 2025, 08:53 UTC"
        assert returned["since_iso"] == "2025-10-09T08:53:20Z"
        assert (returned["count"], returned["more"]) == (3, 1)
        assert (returned["cost"], returned["realized"]) == ("-$2.00", "+$0.50")
        first, gone = returned["rows"]
        assert (first["label"], first["quantity"], first["cost"]) == (
            "USDC",
            "1.500000",
            "-$2.00",
        )
        assert (gone["label"], gone["quantity"]) == ("#99", "")


def _ranked(asset, total, value=None):
    return {
        **_engine_row(),
        "asset": asset,
        "unit": f"U{asset}",
        "total": total,
        "value": value,
        "return": 0.1,
    }


class TestPnlDisplayInsights:
    """Testing class for winners and losers, concentration and drawdown."""

    def test_pnl_display_winners_and_losers(self):
        assets = [_ranked(str(n), (n - 4) * 1_000_000) for n in range(12)]
        assets.append(_ranked("hid", 99_000_000))
        assets.append(_ranked("tiny", 1_000))
        assets.append({**_ranked("spam", 50_000_000), "no_market": True})
        returned = winners_and_losers(assets, "usd", hidden=["hid"])
        winners = [row["label"] for row in returned["winners"]]
        assert winners == ["U11", "U10", "U9", "U8", "U7"]
        assert [row["label"] for row in returned["losers"]] == ["U0", "U1", "U2", "U3"]
        assert returned["winners"][0]["total"] == "+$7.00"
        assert returned["losers"][0]["tone"] == "pnl-loss"
        assert len(returned["pairs"]) == 5
        assert returned["pairs"][4][1] is None

    def test_pnl_display_winners_and_losers_without_any(self):
        assert winners_and_losers([_ranked("1", 0.0)], "usd") is None

    def test_pnl_display_concentration(self):
        assets = [_ranked(str(n), 0, value=(n + 1) * 1_000_000) for n in range(6)]
        assets.append(_ranked("sold", 0, value=None))
        returned = concentration(assets, {"value": 21_000_000}, "usd")
        assert returned["count"] == 5
        assert returned["share"] == "95.2%"
        assert returned["rows"][0] == {
            "asset": "5",
            "label": "U5",
            "value": "$6.00",
            "share": "28.6%",
        }

    @pytest.mark.parametrize("totals", [{"value": 0}, {}])
    def test_pnl_display_concentration_without_value(self, totals):
        assert concentration([_ranked("1", 0, value=5)], totals, "usd") is None

    def test_pnl_display_drawdown(self):
        points = [
            {"date": 1_700_000_000, "pnl": 0.0},
            {"date": 1_700_086_400, "pnl": 5_000_000},
            {"date": 1_700_172_800, "pnl": 1_000_000},
            {"date": 1_700_259_200, "pnl": 8_000_000},
            {"date": 1_700_345_600, "pnl": 6_000_000},
        ]
        assert drawdown(points, "usd") == {
            "amount": "-$4.00",
            "start": "15 Nov 2023",
            "end": "16 Nov 2023",
        }
        assert chart(points, "usd")["drawdown"]["amount"] == "-$4.00"

    def test_pnl_display_drawdown_without_a_fall(self):
        points = [{"date": 1, "pnl": 1_000_000}, {"date": 2, "pnl": 2_000_000}]
        assert drawdown(points, "usd") is None
