"""The P&L table as CSV: plain numbers in whole units, one row per asset and a total."""

import csv
import io
import math
from decimal import Decimal

from .display import asset_label

#: Cells starting with these are formulas to a spreadsheet; asset names are anyone's.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

HEADER = (
    "Asset ID",
    "Asset",
    "Name",
    "Quantity",
    "Average cost",
    "Price",
    "Value",
    "Cost basis",
    "Unrealized",
    "Realized",
    "Income",
    "Costs and fees",
    "Total",
    "Return %",
    "vs holding",
    "LP fees",
    "Divergence",
    "Farm yield",
    "Notes",
)


def _text(value):
    """Return `value` safe from being read as a spreadsheet formula.

    :param value: free text such as an asset name
    :type value: str
    :return: str
    """
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _number(value, shift, places):
    """Return `value` moved `shift` decimal places and rounded to `places`, or "".

    :param value: engine figure
    :type value: float or None
    :param shift: power of ten to multiply by
    :type shift: int
    :param places: decimal places kept
    :type places: int
    :return: str
    """
    if value is None or not math.isfinite(value):
        return ""

    number = Decimal(str(value)).scaleb(shift).quantize(Decimal(1).scaleb(-places))
    return f"{number:f}"


def _money(value):
    """Return micro-unit `value` in whole currency units.

    :param value: amount in micro-units
    :type value: float or None
    :return: str
    """
    return _number(value, -6, 6)


def _price(value, decimals):
    """Return per-base-unit `value` as the price of one whole unit.

    :param value: price per base unit in micro-units
    :type value: float or None
    :param decimals: asset's decimals
    :type decimals: int
    :return: str
    """
    return _number(value, decimals - 6, 12)


def _percent(value):
    """Return ratio `value` as a percentage.

    :param value: ratio
    :type value: float or None
    :return: str
    """
    return _number(value, 2, 2)


def _notes(row):
    """Return the row's badges as words.

    :param row: engine's asset result
    :type row: dict
    :return: str
    """
    notes = []
    if row.get("no_market"):
        notes.append("no market")
    elif row["missing_quantity"] > 0 or row["unpriced"] > 0:
        notes.append("incomplete")
    if row.get("illiquid"):
        notes.append("illiquid")
    return "; ".join(notes)


def _asset_line(row):
    """Return the CSV cells of one engine asset result.

    :param row: engine's asset result
    :type row: dict
    :var decimals: asset's decimals
    :type decimals: int
    :return: list
    """
    decimals = row.get("decimals") or 0
    return [
        row["asset"],
        _text(asset_label(row)),
        _text("" if row.get("lp") else row.get("name") or ""),
        _number(row["quantity"], -decimals, decimals),
        _price(row["average_cost"], decimals),
        _price(row["price"], decimals),
        _money(row["value"]),
        _money(row.get("cost")),
        _money(row["unrealized"]),
        _money(row["realized"]),
        _money(row["income"]),
        _money(row.get("expenses")),
        _money(row.get("total")),
        _percent(row["return"]),
        _money(row.get("vs_hold")),
        _money(row.get("fees")),
        _money(row.get("divergence")),
        _money(row.get("farm_income")),
        _notes(row),
    ]


def _total_line(totals):
    """Return the CSV cells of the bundle's totals, as the summary card shows them.

    :param totals: engine's bundle totals
    :type totals: dict
    :var invested: cumulative cost of all acquisitions
    :type invested: float
    :return: list
    """
    invested = totals.get("invested") or 0
    return [
        "",
        "Total",
        "",
        "",
        "",
        "",
        _money(totals.get("value")),
        _money(totals.get("cost")),
        _money(totals.get("unrealized")),
        _money(totals.get("realized")),
        _money(totals.get("income")),
        _money(totals.get("expenses")),
        _money(totals.get("total")),
        _percent(totals["total"] / invested if invested else None),
        "",
        "",
        "",
        "",
        "",
    ]


def table_csv(data, separator=","):
    """Return the engine's evaluate response as CSV text, with a BOM for spreadsheets.

    :param data: engine's evaluate response
    :type data: dict
    :param separator: field separator character
    :type separator: str
    :var output: text buffer the rows are written to
    :type output: :class:`io.StringIO`
    :return: str
    """
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output, delimiter=separator, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(_asset_line(row) for row in data["assets"])
    writer.writerow(_total_line(data["totals"]))
    return output.getvalue()
