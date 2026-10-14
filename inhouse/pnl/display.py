"""Turn the engine's P&L figures into what the table shows.

Engine values are micro-USD or microALGO; quantities are base units and prices
are per base unit.
"""

from datetime import UTC, datetime
from decimal import Decimal

MICRO = 1_000_000
#: Magnitudes below these display as zero: half a cent, a twentieth of a percent.
HALF_CENT = MICRO / 200
HALF_PERMILLE = 0.0005

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
    :param currency: "usd" or "algo"
    :type currency: str
    :var amount: amount in whole units
    :type amount: float
    :return: str
    """
    if value is None:
        return "—"

    amount = round(value / MICRO, 2)
    sign = "-" if amount < 0 else ""
    if currency == "usd":
        return f"{sign}${abs(amount):,.2f}"

    return f"{sign}{abs(amount):,.2f} ALGO"


def signed_money(value, currency):
    """Return `value` like :func:`money` with an explicit plus for gains.

    :param value: amount in micro-USD or microALGO
    :type value: float or None
    :param currency: "usd" or "algo"
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
    :param currency: "usd" or "algo"
    :type currency: str
    :var amount: price of one whole unit in whole currency units
    :type amount: float
    :return: str
    """
    if value is None:
        return "—"

    amount = value * 10 ** (decimals or 0) / MICRO
    places = 2 if amount >= 1 else 6
    if currency == "usd":
        return f"${amount:,.{places}f}"

    return f"{amount:,.{places}f} ALGO"


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
        return f"LP {row['asset']}"

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
    :param currency: "usd" or "algo"
    :type currency: str
    :var decimals: asset's decimals
    :type decimals: int
    :return: dict
    """
    decimals = row.get("decimals") or 0
    return {
        "asset": row["asset"],
        "label": asset_label(row),
        "name": row.get("name") or "",
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
        "held": row["quantity"] > 0,
        "alerts": alert_presets(row),
        "vs_hold": signed_money(row.get("vs_hold"), currency)
        if row.get("vs_hold") is not None
        else "",
        "vs_hold_tone": tone(row.get("vs_hold")),
        "fees": signed_money(row["fees"], currency)
        if row.get("fees") is not None
        else "",
        "divergence": signed_money(row.get("divergence"), currency)
        if row.get("fees") is not None
        else "",
    }


def summary(totals, currency):
    """Return the totals formatted for the summary card.

    :param totals: engine's bundle totals
    :type totals: dict
    :param currency: "usd" or "algo"
    :type currency: str
    :var invested: cumulative cost of all acquisitions
    :type invested: float
    :return: dict
    """
    invested = totals.get("invested") or 0
    return {
        "total": signed_money(totals.get("total"), currency),
        "total_tone": tone(totals.get("total")),
        "return": percent(totals["total"] / invested if invested else None),
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
        "mve": totals.get("valuation") == "mve",
    }


def period_summary(period, currency):
    """Return the engine's period figures formatted for the summary card.

    :param period: engine's period P&L
    :type period: dict
    :param currency: "usd" or "algo"
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


def event_row(event, decimals, currency):
    """Return an engine event formatted for the drill-down.

    :param event: engine's applied event
    :type event: dict
    :param decimals: asset's decimals
    :type decimals: int
    :param currency: "usd" or "algo"
    :type currency: str
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
        "unpriced": event["value"] is None
        and event["kind"] not in ("position_in", "position_out"),
        "id": event["id"],
        "description": event.get("description") or "",
    }


#: The chart's SVG viewBox: width, height and inner padding.
CHART_WIDTH, CHART_HEIGHT, CHART_PAD = 600, 180, 6


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
    :param currency: "usd" or "algo"
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
    }

