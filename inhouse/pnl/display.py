"""Turn the engine's P&L figures into what the table shows.

Engine values are micro-units of the fiat or microALGO; quantities are base units and prices
are per base unit.
"""

import math
import re
from itertools import zip_longest
from datetime import UTC, datetime
from decimal import Decimal

from utils.explorers import marker_link
from utils.fiat import FIAT_SYMBOLS

MICRO = 1_000_000
#: Most decimals a unit price shows; smaller prices read as zero.
PRICE_MAX_PLACES = 12
#: Magnitudes below these display as zero: half a cent, a twentieth of a percent.
HALF_CENT = MICRO / 200
HALF_PERMILLE = 0.0005
#: Assets listed per kind of issue; the rest are counted.
ISSUES_SHOWN = 50
#: Assets in each of the winners and losers lists, and holdings in the concentration list.
EXTREMES_SHOWN = 5
#: An Algorand transaction id; an event's id is otherwise its group's.
TRANSACTION_ID = re.compile(r"[A-Z2-7]{52}")

EVENT_LABELS = {
    "deposit": "Deposit",
    "withdrawal": "Withdrawal",
    "swap": "Swap",
    "unpriced_swap": "Swap (no price)",
    "income": "Income",
    "expense": "Cost",
    "fee": "Fee",
    "liquidity_in": "Liquidity added",
    "liquidity_out": "Liquidity removed",
    "position_in": "Deposited in dApp",
    "position_out": "Withdrawn from dApp",
}


def money(value, currency):
    """Return `value` in micro-units as text in `currency`, or a dash.

    :param value: amount in micro-USD or microALGO
    :type value: float or None
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var amount: amount in whole units
    :type amount: float
    :return: str
    """
    if value is None:
        return "—"

    amount = round(value / MICRO, 2)
    sign = "-" if amount < 0 else ""
    symbol = FIAT_SYMBOLS.get(currency.upper())
    if symbol:
        return f"{sign}{symbol}{abs(amount):,.2f}"

    return f"{sign}{abs(amount):,.2f} {currency.upper()}"


def signed_money(value, currency):
    """Return `value` like :func:`money` with an explicit plus for gains.

    :param value: amount in micro-USD or microALGO
    :type value: float or None
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :return: str
    """
    text = money(value, currency)
    return f"+{text}" if tone(value, HALF_CENT) == "pnl-gain" else text


def quantity(value, decimals):
    """Return base-unit `value` as whole units.

    :param value: amount in base units
    :type value: float or None
    :param decimals: asset's decimals
    :type decimals: int
    :return: str
    """
    if value is None:
        return "—"

    return f"{value / 10 ** (decimals or 0):,.{min(decimals or 0, 6)}f}"


def unit_price(value, decimals, currency):
    """Return per-base-unit `value` as the price of one whole unit.

    :param value: price per base unit in micro-USD or microALGO
    :type value: float or None
    :param decimals: asset's decimals
    :type decimals: int
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var amount: price of one whole unit in whole currency units
    :type amount: float
    :var places: decimals shown, enough for three significant digits below 0.000001
    :type places: int
    :return: str
    """
    if value is None:
        return "—"

    amount = value * 10 ** (decimals or 0) / MICRO
    if abs(amount) >= 1:
        places = 2
    elif amount and abs(amount) < 0.000001:
        places = min(2 - math.floor(math.log10(abs(amount))), PRICE_MAX_PLACES)
    else:
        places = 6
    sign = "-" if round(amount, places) < 0 else ""
    symbol = FIAT_SYMBOLS.get(currency.upper())
    if symbol:
        return f"{sign}{symbol}{abs(amount):,.{places}f}"

    return f"{sign}{abs(amount):,.{places}f} {currency.upper()}"


def percent(value):
    """Return ratio `value` as a signed percentage, or a dash.

    :param value: ratio
    :type value: float or None
    :return: str
    """
    if value is None:
        return "—"

    if not tone(value, HALF_PERMILLE):
        return "0.0%"

    return f"{value * 100:+.1f}%"


def tone(value, threshold=HALF_CENT):
    """Return the CSS tone for a gain, a loss, or nothing when it rounds to zero.

    :param value: signed amount in micro-units, or a ratio with its threshold
    :type value: float or None
    :param threshold: largest magnitude shown as zero
    :type threshold: float
    :return: str
    """
    if value is None or abs(value) < threshold:
        return ""

    return "pnl-gain" if value > 0 else "pnl-loss"


def asset_label(row):
    """Return the asset's display name.

    :param row: engine's asset result
    :type row: dict
    :return: str
    """
    if row.get("lp"):
        return row.get("pool") or f"LP {row['asset']}"

    return row.get("unit") or row.get("name") or f"#{row['asset']}"


#: Price alert presets as (label, multiple of the average cost).
ALERT_PRESETS = (("Break-even", 1), ("+25%", 1.25), ("+50%", 1.5), ("-20%", 0.8))


def alert_presets(row):
    """Return price alert choices built from the asset's average cost.

    Thresholds are per whole unit, as asset prices are; none for ALGO itself,
    LP tokens, assets without a market or no longer held.

    :param row: engine's asset result
    :type row: dict
    :var unit_cost: average cost of one whole unit
    :type unit_cost: :class:`decimal.Decimal`
    :return: list
    """
    if (
        row["asset"] == "0"
        or row.get("lp")
        or row.get("no_market")
        or row["average_cost"] is None
        or row["quantity"] <= 0
    ):
        return []

    scale = Decimal(10) ** (row.get("decimals") or 0) / MICRO
    unit_cost = Decimal(str(row["average_cost"])) * scale
    unit_price = Decimal(str(row["price"])) * scale if row["price"] else None
    presets = []
    for label, factor in ALERT_PRESETS:
        threshold = (unit_cost * Decimal(str(factor))).quantize(Decimal("1e-10"))
        if threshold <= 0:
            continue

        if factor == 1:
            direction = "up" if unit_price is None or unit_price < threshold else "down"
        else:
            direction = "up" if factor > 1 else "down"

        presets.append(
            {
                "label": label,
                "direction": direction,
                "threshold": f"{threshold.normalize():f}",
            }
        )

    return presets


def table_row(row, currency):
    """Return the engine's asset result formatted for the table.

    :param row: engine's asset result
    :type row: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var decimals: asset's decimals
    :type decimals: int
    :return: dict
    """
    decimals = row.get("decimals") or 0
    return {
        "asset": row["asset"],
        "label": asset_label(row),
        "name": f"LP token {row['asset']}" if row.get("lp") else row.get("name") or "",
        "quantity": quantity(row["quantity"], decimals),
        "average_cost": unit_price(row["average_cost"], decimals, currency),
        "price": unit_price(row["price"], decimals, currency),
        "value": money(row["value"], currency),
        "unrealized": signed_money(row["unrealized"], currency),
        "unrealized_tone": tone(row["unrealized"]),
        "realized": signed_money(row["realized"], currency),
        "realized_tone": tone(row["realized"]),
        "income": money(row["income"], currency) if row["income"] else "",
        "return": percent(row["return"]),
        "return_tone": tone(row["return"], HALF_PERMILLE),
        "incomplete": not row.get("no_market")
        and (row["missing_quantity"] > 0 or row["unpriced"] > 0),
        "no_market": bool(row.get("no_market")),
        "illiquid": bool(row.get("illiquid")),
        "nft": bool(row.get("nft")),
        "held": row["quantity"] > 0,
        "valued": row["value"] is not None,
        "alerts": alert_presets(row),
        "vs_hold": signed_money(row.get("vs_hold"), currency)
        if row.get("vs_hold") is not None
        else "",
        "vs_hold_tone": tone(row.get("vs_hold")),
        **_farm_note(row, currency),
        **_split_note(row, currency),
    }


def _issue_item(row, detail, effect):
    """Return one affected asset for the issues list.

    :param row: engine's asset result
    :type row: dict
    :param detail: what is wrong with it
    :type detail: str
    :param effect: formatted amount the issue moves, or empty
    :type effect: str
    :return: dict
    """
    return {
        "asset": row["asset"],
        "label": asset_label(row),
        "name": f"LP token {row['asset']}" if row.get("lp") else row.get("name") or "",
        "detail": detail,
        "effect": effect,
    }


def _issue_group(title, note, items):
    """Return a kind of issue with its first `ISSUES_SHOWN` assets.

    :param title: kind of issue
    :type title: str
    :param note: how it affects the figures
    :type note: str
    :param items: affected assets, largest effect first
    :type items: list
    :return: dict
    """
    return {
        "title": title,
        "note": note,
        "total": len(items),
        "items": items[:ISSUES_SHOWN],
        "more": max(len(items) - ISSUES_SHOWN, 0),
    }


def issues(assets, currency):
    """Return the assets behind the coverage notes, grouped by kind of issue.

    Assets that never had a market are left out: they count for nothing anyway.

    :param assets: engine's asset results
    :type assets: list
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var rows: asset results that had a market
    :type rows: list
    :return: list
    """
    rows = [row for row in assets if not row.get("no_market")]
    unvalued = sorted(
        (row for row in rows if row["quantity"] > 0 and row["value"] is None),
        key=lambda row: row["cost"] or 0,
        reverse=True,
    )
    missing = sorted(
        (row for row in rows if row["missing_quantity"] > 0),
        key=lambda row: row.get("missing_proceeds") or 0,
        reverse=True,
    )
    unpriced = sorted(
        (row for row in rows if row["unpriced"] > 0),
        key=lambda row: row["unpriced"],
        reverse=True,
    )
    groups = [
        _issue_group(
            "Holdings without a current price",
            "Left out of value and unrealized; the amount is their cost.",
            [
                _issue_item(
                    row,
                    "LP token without a pool price" if row.get("lp") else "No current price",
                    money(row["cost"], currency),
                )
                for row in unvalued
            ],
        ),
        _issue_group(
            "Sold beyond the known history",
            "Their cost is unknown, so these sales are left out of realized; "
            "the amount is what they fetched.",
            [
                _issue_item(
                    row,
                    f"{quantity(row['missing_quantity'], row.get('decimals'))} units",
                    money(row.get("missing_proceeds"), currency),
                )
                for row in missing
            ],
        ),
        _issue_group(
            "Events without a price",
            "Each counts as zero; open the asset to see which.",
            [
                _issue_item(row, f"{row['unpriced']} event{'s' * (row['unpriced'] > 1)}", "")
                for row in unpriced
            ],
        ),
    ]
    return [group for group in groups if group["total"]]


def _shown(value):
    """Return whether `value` in micro-units is non-zero once rounded to cents.

    :param value: amount in micro-units
    :type value: float or None
    :return: Boolean
    """
    return value is not None and abs(value) >= HALF_CENT


def _farm_note(row, currency):
    """Return the farm yield note's parts; empty when it would read $0.00.

    :param row: engine's asset result
    :type row: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var unpriced: rewards without a price
    :type unpriced: int
    :return: dict
    """
    unpriced = row.get("farm_unpriced") or 0
    if not _shown(row.get("farm_income")) and not unpriced:
        return {"farm_income": "", "farm_unpriced": 0, "farm_assets": []}

    return {
        "farm_income": money(row["farm_income"], currency),
        "farm_unpriced": unpriced,
        "farm_assets": row.get("farm_assets") or [],
    }


def _split_note(row, currency):
    """Return fees and divergence; empty when both would read zero.

    :param row: engine's asset result
    :type row: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :return: dict
    """
    if not (_shown(row.get("fees")) or _shown(row.get("divergence"))):
        return {"fees": "", "divergence": ""}

    return {
        "fees": signed_money(row["fees"], currency),
        "divergence": signed_money(row["divergence"], currency),
    }


def summary(totals, currency):
    """Return the totals formatted for the summary card.

    :param totals: engine's bundle totals
    :type totals: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var invested: cumulative cost of all acquisitions
    :type invested: float
    :var brought_in: value brought in from outside the bundle minus value sent out
    :type brought_in: float
    :return: dict
    """
    invested = totals.get("invested") or 0
    brought_in = (totals.get("inflows") or 0) - (totals.get("outflows") or 0)
    return {
        "total": signed_money(totals.get("total"), currency),
        "total_tone": tone(totals.get("total")),
        "return": percent(totals["total"] / invested if invested else None),
        "brought_in": signed_money(brought_in, currency),
        "return_brought_in": (
            percent(totals["total"] / brought_in) if brought_in > 0 else None
        ),
        "realized": signed_money(totals.get("realized"), currency),
        "unrealized": signed_money(totals.get("unrealized"), currency),
        "income": money(totals.get("income"), currency),
        "expenses": money(totals.get("expenses"), currency),
        "value": money(totals.get("value"), currency),
        "cost": money(totals.get("cost"), currency),
        "unvalued_assets": int(totals.get("unvalued_assets") or 0),
        "assets_missing_history": int(totals.get("assets_missing_history") or 0),
        "unpriced_events": int(totals.get("unpriced_events") or 0),
        "unvalued_cost": money(totals.get("unvalued_cost") or 0, currency),
        "no_market_assets": int(totals.get("no_market_assets") or 0),
        "illiquid_assets": int(totals.get("illiquid_assets") or 0),
        "nft_value": money(totals["nft_value"], currency)
        if totals.get("nft_value")
        else "",
        "mve": totals.get("valuation") == "mve",
        "nfts_out": totals.get("nfts") is False,
    }


def period_summary(period, currency):
    """Return the engine's period figures formatted for the summary card.

    :param period: engine's period P&L
    :type period: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :return: dict
    """
    return {
        "pnl": signed_money(period["pnl"], currency),
        "pnl_tone": tone(period["pnl"]),
        "return": percent(period["return"]),
        "start_value": money(period["start_value"], currency),
        "end_value": money(period["end_value"], currency),
        "net_flows": signed_money(period["net_flows"], currency),
        "unvalued_assets": int(period.get("unvalued_assets") or 0),
    }


def transaction_marker(event_id):
    """Return the explorer marker of an event's id: a transaction id or a group id.

    :param event_id: engine event's id
    :type event_id: str
    :return: str
    """
    entity = "transaction" if TRANSACTION_ID.fullmatch(event_id) else "group"
    return f"{entity}={event_id}"


def event_row(event, decimals, currency, explorer=None):
    """Return an engine event formatted for the drill-down.

    :param event: engine's applied event
    :type event: dict
    :param decimals: asset's decimals
    :type decimals: int
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :param explorer: the reader's explorer key; without it the id is not linked
    :type explorer: str
    :return: dict
    """
    return {
        "date": datetime.fromtimestamp(int(event["date"]), UTC).strftime(
            "%-d %b %Y %H:%M"
        ),
        "kind": EVENT_LABELS.get(event["kind"], event["kind"]),
        "quantity": quantity(event["quantity"], decimals),
        "value": money(event["value"], currency),
        "cost": money(event["cost"], currency),
        "realized": signed_money(event["realized"], currency),
        "realized_tone": tone(event["realized"]),
        "unpriced": event.get("unpriced", event["value"] is None)
        and event["kind"] not in ("position_in", "position_out"),
        "id": event["id"],
        "link": marker_link(explorer, transaction_marker(event["id"]))
        if explorer and event.get("id")
        else "",
        "description": event.get("description") or "",
    }


#: The chart's SVG viewBox: width, height and inner padding.
CHART_WIDTH, CHART_HEIGHT, CHART_PAD = 600, 180, 6


def _extreme(row, currency):
    """Return one asset of the winners or losers list, formatted.

    :param row: engine's asset result
    :type row: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :return: dict
    """
    return {
        "asset": row["asset"],
        "label": asset_label(row),
        "total": signed_money(row["total"], currency),
        "tone": tone(row["total"]),
        "return": percent(row.get("return")),
    }


def winners_and_losers(assets, currency, hidden=()):
    """Return the assets that gained and lost the most in total, or None.

    :param assets: engine's asset results
    :type assets: list
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :param hidden: asset ids the reader hid from the table
    :type hidden: iterable
    :var ranked: assets whose total does not round to zero, largest first
    :type ranked: list
    :return: dict or None
    """
    hidden = set(hidden)
    ranked = sorted(
        (
            row
            for row in assets
            if row["asset"] not in hidden
            and not row.get("no_market")
            and tone(row["total"])
        ),
        key=lambda row: row["total"],
        reverse=True,
    )
    winners = [row for row in ranked if row["total"] > 0][:EXTREMES_SHOWN]
    losers = [row for row in reversed(ranked) if row["total"] < 0][:EXTREMES_SHOWN]
    if not winners and not losers:
        return None

    winners = [_extreme(row, currency) for row in winners]
    losers = [_extreme(row, currency) for row in losers]
    # side by side in the template: one row per rank
    return {
        "winners": winners,
        "losers": losers,
        "pairs": list(zip_longest(winners, losers)),
    }


def concentration(assets, totals, currency):
    """Return the largest holdings and their share of the current value, or None.

    :param assets: engine's asset results
    :type assets: list
    :param totals: engine's bundle totals
    :type totals: dict
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var value: the bundle's current value
    :type value: float
    :var largest: valued holdings, largest first, as many as are listed
    :type largest: list
    :return: dict or None
    """
    value = totals.get("value") or 0
    largest = sorted(
        (row for row in assets if (row.get("value") or 0) > 0),
        key=lambda row: row["value"],
        reverse=True,
    )[:EXTREMES_SHOWN]
    if value <= 0 or not largest:
        return None

    return {
        "share": f"{sum(row['value'] for row in largest) / value * 100:.1f}%",
        "count": len(largest),
        "rows": [
            {
                "asset": row["asset"],
                "label": asset_label(row),
                "value": money(row["value"], currency),
                "share": f"{row['value'] / value * 100:.1f}%",
            }
            for row in largest
        ],
    }


def drawdown(points, currency):
    """Return the chart's largest fall from a peak to a later low, or None.

    :param points: engine's chart points, ascending by date
    :type points: list
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var peak: highest point so far
    :type peak: dict
    :var fall: largest fall so far, its peak and its low
    :type fall: tuple
    :return: dict or None
    """
    peak, fall = points[0], (0.0, None, None)
    for point in points:
        if point["pnl"] > peak["pnl"]:
            peak = point
        if peak["pnl"] - point["pnl"] > fall[0]:
            fall = (peak["pnl"] - point["pnl"], peak, point)

    if fall[0] < HALF_CENT:
        return None

    return {
        "amount": signed_money(-fall[0], currency),
        "start": _chart_date(fall[1]["date"]),
        "end": _chart_date(fall[2]["date"]),
    }


def reprocess_changes(changes, assets, currency):
    """Return what the engine says a reprocess changed, formatted, or None.

    :param changes: engine's `changes`, None when nothing moved
    :type changes: dict or None
    :param assets: engine's asset results, for names and decimals
    :type assets: list
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var known: current asset results keyed by asset
    :type known: dict
    :return: dict or None
    """
    if not changes:
        return None

    known = {row["asset"]: row for row in assets}
    return {
        "since": processed_time(changes["since"]),
        "count": changes["assets_changed"],
        "more": changes["assets_changed"] - len(changes["assets"]),
        **{
            field: signed_money(changes[field], currency)
            for field in ("cost", "realized", "income", "expenses")
        },
        "rows": [
            _change_row(row, known.get(row["asset"]), currency)
            for row in changes["assets"]
        ],
    }


def _change_row(row, current, currency):
    """Return one asset's change after a reprocess, formatted.

    :param row: engine's per-asset change
    :type row: dict
    :param current: the asset's current result, None for an asset no longer held
    :type current: dict or None
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :return: dict
    """
    return {
        "asset": row["asset"],
        "label": asset_label(current) if current else f"#{row['asset']}",
        "quantity": quantity(row["quantity"], current["decimals"]) if current else "",
        **{
            field: signed_money(row[field], currency)
            for field in ("cost", "realized", "income", "expenses")
        },
    }


def processed_time(timestamp):
    """Return when the bundle's rows were processed, empty when unknown.

    :param timestamp: seconds since epoch, or None from an older evaluation
    :type timestamp: int
    :return: str
    """
    if not timestamp:
        return ""

    return datetime.fromtimestamp(int(timestamp), UTC).strftime("%-d %b %Y, %H:%M UTC")


def _chart_date(timestamp):
    """Return `timestamp` as a short date for the chart.

    :param timestamp: seconds since epoch
    :type timestamp: int
    :return: str
    """
    return datetime.fromtimestamp(int(timestamp), UTC).strftime("%-d %b %Y")


def chart(points, currency):
    """Return the engine's cumulative P&L points laid out for an inline SVG.

    :param points: engine's chart points, ascending by date
    :type points: list
    :param currency: "algo", "usd" or another fiat's lower-case code
    :type currency: str
    :var low: lowest P&L, or zero if higher
    :type low: float
    :var high: highest P&L, or zero if lower
    :type high: float
    :return: dict or None
    """
    if not points:
        return None

    values = [point["pnl"] for point in points]
    low, high = min(values + [0.0]), max(values + [0.0])
    if high == low:  # a flat line sits mid-height
        low, high = low - 1.0, high + 1.0
    span = high - low
    first, last = points[0]["date"], points[-1]["date"]
    width = (last - first) or 1

    def x(date):
        return round(CHART_PAD + (date - first) / width * (CHART_WIDTH - 2 * CHART_PAD), 1)

    def y(value):
        return round(
            CHART_PAD + (high - value) / span * (CHART_HEIGHT - 2 * CHART_PAD), 1
        )

    laid = [
        {
            "x": x(point["date"]),
            "y": y(point["pnl"]),
            "title": f"{_chart_date(point['date'])}: "
            f"{signed_money(point['pnl'], currency)}",
        }
        for point in points
    ]
    line = " ".join(f"{point['x']},{point['y']}" for point in laid)
    return {
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
        "line": line,
        "area": f"{laid[0]['x']},{y(0.0)} {line} {laid[-1]['x']},{y(0.0)}",
        "zero_y": y(0.0),
        "points": laid,
        "start": _chart_date(first),
        "end": _chart_date(last),
        "high": signed_money(max(values + [0.0]), currency),
        "low": signed_money(min(values + [0.0]), currency),
        "last": signed_money(values[-1], currency),
        "last_tone": tone(values[-1]),
        "unvalued": max(point.get("unvalued_assets") or 0 for point in points),
        "drawdown": drawdown(points, currency),
    }

