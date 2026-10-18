"""Testing module for :py:mod:`widgets.inhouse.pnl.export` module."""

import csv
import io

import pytest

from widgets.inhouse.pnl.export import HEADER, table_csv


def _row(**kwargs):
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
        "realized": -12_345.6,
        "income": 0,
        "expenses": 1_000,
        "total": 236_654.4,
        "return": 0.10518,
        "missing_quantity": 0,
        "unpriced": 0,
    }
    row.update(kwargs)
    return row


def _totals(**kwargs):
    totals = {
        "value": 2_500_000,
        "cost": 2_250_000,
        "unrealized": 250_000,
        "realized": -12_345.6,
        "income": 0,
        "expenses": 1_000,
        "total": 236_654.4,
        "invested": 2_250_000,
    }
    totals.update(kwargs)
    return totals


def _parsed(text, separator=","):
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:]), delimiter=separator))


class TestPnlExportTableCsv:
    """Testing class for :py:func:`...pnl.export.table_csv`."""

    def test_pnl_export_table_csv_header_rows_and_total(self):
        lines = _parsed(table_csv({"assets": [_row()], "totals": _totals()}))
        assert lines[0] == list(HEADER)
        assert dict(zip(HEADER, lines[1])) == {
            "Asset ID": "31566704",
            "Asset": "USDC",
            "Name": "USDC",
            "Quantity": "2.500000",
            "Average cost": "0.900000000000",
            "Price": "1.000000000000",
            "Value": "2.500000",
            "Cost basis": "2.250000",
            "Unrealized": "0.250000",
            "Realized": "-0.012346",
            "Income": "0.000000",
            "Costs and fees": "0.001000",
            "Total": "0.236654",
            "Return %": "10.52",
            "vs holding": "",
            "LP fees": "",
            "Divergence": "",
            "Farm yield": "",
            "Notes": "",
        }
        total = dict(zip(HEADER, lines[2]))
        assert total["Asset"] == "Total"
        assert total["Quantity"] == total["Price"] == ""
        assert total["Value"] == "2.500000"
        assert total["Total"] == "0.236654"
        assert total["Return %"] == "10.52"
        assert len(lines) == 3

    def test_pnl_export_table_csv_lines_end_in_crlf(self):
        text = table_csv({"assets": [], "totals": _totals()})
        assert text.count("\r\n") == 2

    @pytest.mark.parametrize("separator", [";", "\t"])
    def test_pnl_export_table_csv_separator(self, separator):
        text = table_csv({"assets": [_row()], "totals": _totals()}, separator)
        assert text.splitlines()[1].split(separator)[0] == "31566704"
        assert _parsed(text, separator)[1][1] == "USDC"

    def test_pnl_export_table_csv_unknown_figures_are_empty(self):
        row = _row(
            average_cost=None, price=None, value=None, unrealized=None, **{"return": None}
        )
        line = dict(
            zip(
                HEADER,
                _parsed(table_csv({"assets": [row], "totals": _totals(invested=0)}))[1],
            )
        )
        assert line["Price"] == line["Value"] == line["Return %"] == ""
        total = dict(
            zip(
                HEADER,
                _parsed(table_csv({"assets": [], "totals": _totals(invested=0)}))[1],
            )
        )
        assert total["Return %"] == ""

    def test_pnl_export_table_csv_non_finite_figures_are_empty(self):
        row = _row(value=float("nan"), unrealized=float("inf"))
        line = dict(
            zip(HEADER, _parsed(table_csv({"assets": [row], "totals": _totals()}))[1])
        )
        assert line["Value"] == line["Unrealized"] == ""

    def test_pnl_export_table_csv_price_of_a_whole_unit(self):
        row = _row(decimals=0, quantity=3, average_cost=1_500_000, price=2_000_000)
        line = dict(
            zip(HEADER, _parsed(table_csv({"assets": [row], "totals": _totals()}))[1])
        )
        assert line["Quantity"] == "3"
        assert line["Average cost"] == "1.500000000000"
        assert line["Price"] == "2.000000000000"

    def test_pnl_export_table_csv_names_cannot_be_formulas(self):
        row = _row(unit="=HYPERLINK(1)", name="+cmd")
        line = _parsed(table_csv({"assets": [row], "totals": _totals()}))[1]
        assert line[1] == "'=HYPERLINK(1)"
        assert line[2] == "'+cmd"

    def test_pnl_export_table_csv_negative_numbers_are_not_escaped(self):
        line = _parsed(table_csv({"assets": [_row()], "totals": _totals()}))[1]
        assert line[HEADER.index("Realized")] == "-0.012346"

    def test_pnl_export_table_csv_lp_row(self):
        row = _row(
            asset="1002",
            lp=True,
            pool="Tinyman LP ALGO/USDC",
            name="TinymanPool2.0",
            vs_hold=-50_000,
            fees=10_000,
            divergence=-60_000,
            farm_income=5_000,
        )
        line = dict(
            zip(HEADER, _parsed(table_csv({"assets": [row], "totals": _totals()}))[1])
        )
        assert line["Asset"] == "Tinyman LP ALGO/USDC"
        assert line["Name"] == ""
        assert line["vs holding"] == "-0.050000"
        assert line["LP fees"] == "0.010000"
        assert line["Divergence"] == "-0.060000"
        assert line["Farm yield"] == "0.005000"

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({"no_market": True, "unpriced": 2}, "no market"),
            ({"missing_quantity": 1}, "incomplete"),
            ({"unpriced": 1, "illiquid": True}, "incomplete; illiquid"),
            ({"illiquid": True}, "illiquid"),
            ({"nft": True}, "appraised"),
        ],
    )
    def test_pnl_export_table_csv_notes(self, kwargs, expected):
        line = _parsed(table_csv({"assets": [_row(**kwargs)], "totals": _totals()}))[1]
        assert line[-1] == expected
