"""Turn the engine's P&L figures into what the table shows.

Engine values are micro-USD or microALGO; quantities are base units and prices
are per base unit.
"""

from datetime import UTC, datetime

MICRO = 1_000_000

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

    amount = value / MICRO
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
    return f"+{text}" if value is not None and value > 0 else text


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

    return f"{value * 100:+.1f}%"


def tone(value):
    """Return the CSS tone for a gain, a loss or nothing.

    :param value: signed amount
    :type value: float or None
    :return: str
    """
    if not value:
        return ""

    return "pnl-gain" if value > 0 else "pnl-loss"


def asset_label(row):
    """Return the asset's display name.

    :param row: engine's asset result
    :type row: dict
    :return: str
    """
    if row.get("lp"):
        return f"LP {row['asset'][2:]}"

    return row.get("unit") or row.get("name") or f"#{row['asset']}"


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
        "return_tone": tone(row["return"]),
        "incomplete": not row.get("no_market")
        and (row["missing_quantity"] > 0 or row["unpriced"] > 0),
        "no_market": bool(row.get("no_market")),
        "held": row["quantity"] > 0,
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
        "no_market_assets": int(totals.get("no_market_assets") or 0),
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
    }
