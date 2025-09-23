"""Module containing historic widget's charts data creation functions."""

import itertools
from collections import defaultdict
from datetime import datetime, UTC

import numpy as np
import pandas as pd

from utils.charts import (
    prepare_base_charts_from_assets_data,
    prepare_consolidated_charts_from_assets_data,
)
from .constants import (
    DATE_FORMATS_FOR_TIMESTAMPS_INTERVAL,
    DISTINCT_COLORS,
    GROUPS_IN_ASSET_TAGS,
    MAX_NUMBER_OF_ASSETS_IN_CHART,
    MICROALGOS_TO_ALGOS_RATIO,
    OTHERS_GROUP_NAME,
    STORAGE_LEDGER_EXPANSION_MULTIPLIER,
    TOTAL_NUMBER_OF_CANDLES_IN_CHART,
)


# HELPERS
def _append_linechart_to_barchart(chart_data, low_values, high_values):
    """Append line graph's dataset to provided bar chart's dataset.

    :param chart_data: chart labels and datasets collection
    :type chart_data: dict
    :param low_values: collection of minimum values between two adjacent timestamps
    :type low_values: list
    :param high_values: collection of maximum values between two adjacent timestamps
    :type high_values: list
    """
    chart_data["datasets"].extend(
        [
            {
                "label": "Low",
                "data": low_values,
                "borderColor": "#008000",
                "backgroundColor": "#008000",
                "borderDash": [5, 5],
                "type": "line",
                "order": 0,
            },
            {
                "label": "High",
                "data": high_values,
                "borderColor": "#ff0000",
                "backgroundColor": "#ff0000",
                "borderDash": [5, 5],
                "type": "line",
                "order": 0,
            },
        ]
    )


def _bar_chart_config(labels=[], data={}, unit_colors={}):
    """Return stacked bar chart data populated from provided arguments.

    :param labels: collection of chart timestamps
    :type labels: list
    :param data: asset/group values in ALGO collections per timestamp
    :type data: dict
    :param unit_colors: collection of asset units/groups and related chart colors
    :type unit_colors: dict
    :return: dict
    """
    return {
        "labels": labels,
        "datasets": [
            {
                "label": unit,
                "data": data.get(unit, []),
                "backgroundColor": color,
                "borderWidth": 0,
                "hoverOffset": 0,
                "order": 1,
            }
            for unit, color in unit_colors.items()
        ],
    }


def _candlestick_chart_config(data):
    """Return candlestick chart data instance having provided `data`.

    :param data: collection of custom candle objects
    :type data: dict
    :return: dict
    """
    return {"datasets": [{"data": data, "barThickness": "flex"}]}


def _candlestick_chart_timestamps(min_timestamp, max_timestamp, candles_count):
    """Return uniform collection of timestamps for provided boundaries.

    :param min_timestamp: not included left boundary timestamp in collection
    :type min_timestamp: int
    :param max_timestamp: included right boundary timestamp in collection
    :type max_timestamp: int
    :var interval: period between two adjacted timestamps
    :type interval: int
    :return: list
    """
    interval = int((max_timestamp - min_timestamp) / candles_count)
    if interval == 0:
        candles_count = max_timestamp - min_timestamp
        interval = 1

    return list(
        range(
            max_timestamp,
            min_timestamp,
            -interval,
        )
    )[
        :candles_count
    ][::-1]


def _candles_from_interval_values_for_timestamps(interval_values, timestamps):
    """Return collection of candle objects from `interval_values` for `timestamps`.

    [chartjs-chart-financial](https://www.chartjs.org/chartjs-chart-financial/)
    plugin expects collection of objects with epoch in milliseconds under "x" key,
    while the open, high, low, and close values are set under the keys named after
    the related starting letters. We have added additional ot, ht, lt, and ct entries
    for the related timestamps.

    :param interval_values: collection of open, high, low, and close values
    :type interval_values: dict
    :param timestamps: collection of timestamps to render chart for
    :type timestamps: list
    :return: list
    """
    return [
        {
            "x": timestamp * 1000,
            **{
                key[0] if "_" not in key else key[0] + "t": interval_values[key][i]
                for key in interval_values
            },
        }
        for i, timestamp in enumerate(timestamps)
    ]


def _microalgos_to_currency_algo(value):
    """Return provided value in microAlgos as curency-like float value in ALGO.

    :param value: value in microAlgos
    :type value: int`
    :return: float
    """
    return round(100 * int(value) / MICROALGOS_TO_ALGOS_RATIO) / 100


def _timestamps_formatted_to_dates(timestamps):
    """Return provided collection of timestamps converted to appropriate date format.

    :param timestamps: collection of timestamps to render chart for
    :type timestamps: list
    :var date_format: date/time format adjusted to provided timestamps
    :type date_format: str
    :return: list
    """
    if not timestamps:
        return []

    date_format = next(
        date_format
        for interval, date_format in DATE_FORMATS_FOR_TIMESTAMPS_INTERVAL.items()
        if interval <= (timestamps[-1] - timestamps[0]) / len(timestamps)
    )
    return [
        datetime.fromtimestamp(timestamp, UTC).strftime(date_format)
        for timestamp in timestamps
    ]


def _top_assets_chart_layout(top_assets, asset_tags):
    """Return top assets/groups in final chart layout with assigned colors to them.

    :param top_assets: collection of top valued assets in `asset_values` dataframe
    :type top_assets: list
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var group: currently processed group that needs to be moved at the end
    :type group: str
    :var tag: currently processed asset/group
    :type tag: str
    :return: dict
    """
    for group in (*GROUPS_IN_ASSET_TAGS, OTHERS_GROUP_NAME):
        if group in top_assets:
            top_assets.remove(group)
            top_assets.append(group)

    return {
        _unit_or_tag_from_asset_tags(tag, asset_tags): DISTINCT_COLORS[i]
        for i, tag in enumerate(top_assets)
    }


def _unit_or_tag_from_asset_tags(tag, asset_tags):
    """Return asset's tag if provided `asset_or_group` represents an asset.

    :param tag: Algorand Standard Asset identifier or group
    :type tag: object
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :return: str
    """
    return asset_tags.get(tag) if tag in asset_tags else tag


def asset_values_from_computed_data(computed_data):
    """Return asset values data for equally distributed timestamps from provided data.

    :param computed_data: fully evaluated bundle ledger data for zoomed out period
    :type computed_data: :class:`pandas.DataFrame`
    :return: :class:`pandas.DataFrame`
    """
    return (
        computed_data.groupby(["timestamp", "asset"])["value"]
        .sum()
        .reset_index()
        .sort_values(by=["timestamp", "value"], ascending=[True, False])
    )


# # EXTEND
def _apply_extended_timestamps_to_bar_chart(
    bar_chart, timeline_data, left_timestamps, right_timestamps
):
    """Uniformly extend provided bar chart on the left and right side.

    :param bar_chart: bar chart's labels and datasets collection
    :type bar_chart: dict
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param left_timestamps: collection of timestamps to prepend to central timestamps
    :type left_timestamps: list
    :param right_timestamps: collection of timestamps to append to central timestamps
    :type right_timestamps: list
    :var values_on_left: collection of values to prepend to chart under "others"
    :type values_on_left: list
    :var values_on_right: collection of values to append to chart under "others"
    :type values_on_right: list
    :var item: currently processed asset group/unit
    :type item: dict
    """
    values_on_left = (
        [
            _microalgos_to_currency_algo(value)
            for value in _timeline_data_values_for_timestamps(
                left_timestamps, timeline_data
            )
        ]
        if left_timestamps
        else []
    )
    values_on_right = (
        [
            _microalgos_to_currency_algo(value)
            for value in _timeline_data_values_for_timestamps(
                right_timestamps, timeline_data
            )
        ]
        if right_timestamps
        else []
    )

    bar_chart["labels"] = (
        _timestamps_formatted_to_dates(left_timestamps)
        + bar_chart.get("labels", [])
        + _timestamps_formatted_to_dates(right_timestamps)
    )

    for item in bar_chart.get("datasets"):
        if item.get("label") == OTHERS_GROUP_NAME:
            item["data"] = values_on_left + item.get("data", []) + values_on_right

        else:
            item["data"] = (
                [0] * len(values_on_left)
                + item.get("data", [])
                + [0] * len(values_on_right)
            )


def _extend_barchart_on_both_sides(bar_chart, central_timestamps, timeline_data):
    """Extend provided bar chart and return new timestamps and initial column indices.

    :param bar_chart: bar chart's labels and datasets collection
    :type bar_chart: dict
    :param central_timestamps: collection of timestamps to initially render chart for
    :type central_timestamps: list
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :var left_timestamps: collection of timestamps to prepend to central timestamps
    :type left_timestamps: list
    :var right_timestamps: collection of timestamps to append to central timestamps
    :type right_timestamps: list
    :var x_min: index of first initially visible chart's bar
    :type x_min: int
    :var x_max: index of last initially visible chart's bar
    :type x_max: int
    :return: tuple
    """
    left_timestamps, right_timestamps = _extended_timestamps(
        central_timestamps, timeline_data
    )
    if left_timestamps or right_timestamps:
        _apply_extended_timestamps_to_bar_chart(
            bar_chart, timeline_data, left_timestamps, right_timestamps
        )

    x_min = len(left_timestamps)
    x_max = x_min + len(central_timestamps) - 1

    return left_timestamps + central_timestamps + right_timestamps, x_min, x_max


def _extend_candlestick_timestamps_on_both_sides(central_timestamps, timeline_data):
    """Uniformly extend provided timestamps on the left and right side.

    :param central_timestamps: collection of timestamps to initially render chart for
    :type central_timestamps: list
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :var left_timestamps: collection of timestamps to prepend to central timestamps
    :type left_timestamps: list
    :var right_timestamps: collection of timestamps to append to central timestamps
    :type right_timestamps: list
    :return: list
    """
    left_timestamps, right_timestamps = _extended_timestamps(
        central_timestamps, timeline_data
    )
    return [
        timestamp
        for timestamp in (*left_timestamps, *central_timestamps, *right_timestamps)
    ]


def _extended_timestamps(central_timestamps, timeline_data):
    """Return uniformly extended provided timestamps on the left and right side.

    :param central_timestamps: collection of timestamps to initially render chart for
    :type central_timestamps: list
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :var min_timestamp: ledger's minimum timestamp
    :type min_timestamp: int
    :var max_timestamp: ledger's maximum timestamp
    :type max_timestamp: int
    :var interval: diference between adjacent timestamps in collection
    :type interval: int
    :var left_side_timestamps: collection of timestamps to prepend to central timestamps
    :type left_side_timestamps: list
    :var right_side_timestamps: collection of timestamps to append to central timestamps
    :type right_side_timestamps: list
    :return: two tuple
    """
    min_timestamp, max_timestamp = (
        int(timeline_data["timestamp"].min()),
        int(timeline_data["timestamp"].max()),
    )

    interval = (
        int((central_timestamps[-1] - central_timestamps[0]) / len(central_timestamps))
        or 1
    )

    if (
        central_timestamps[0] == min_timestamp
        and central_timestamps[-1] + interval * 1.1 > max_timestamp
    ):
        return [], []

    left_side_timestamps = list(
        _uniformly_spread_timestamps(
            central_timestamps[0] - interval, -interval, min_timestamp
        )
    )[::-1]
    if (
        len(left_side_timestamps)
        and (left_side_timestamps[0] != min_timestamp)
        and (
            len(left_side_timestamps)
            < len(central_timestamps) * STORAGE_LEDGER_EXPANSION_MULTIPLIER
        )
    ):
        left_side_timestamps.insert(0, min_timestamp)

    right_side_timestamps = list(
        _uniformly_spread_timestamps(
            central_timestamps[-1] + interval, interval, max_timestamp
        )
    )
    if (
        len(right_side_timestamps)
        and (right_side_timestamps[-1] != max_timestamp)
        and (
            len(right_side_timestamps)
            < len(central_timestamps) * STORAGE_LEDGER_EXPANSION_MULTIPLIER
        )
    ):
        right_side_timestamps.append(max_timestamp)

    return left_side_timestamps, right_side_timestamps


def _timeline_data_values_for_timestamps(timestamps, timeline_data):
    """Return collection of values from `timeline_data` which relate to `timestamps`.

    TODO: docstrings

    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param timestamps: collection of timestamps to assign values to
    :type timestamps: list
    :return: list
    """
    # Ensure timestamps are sorted and determine direction
    timestamps = np.array(timestamps)
    is_ascending = np.all(np.diff(timestamps) >= 0)

    # If descending, reverse timestamps for processing
    if not is_ascending:
        timestamps = timestamps[::-1]

    # Sort dataframe by timestamp
    timeline_data = timeline_data.sort_values("timestamp").reset_index(drop=True)

    # Initialize result array
    values = np.zeros(len(timestamps), dtype=timeline_data["value"].dtype)

    # Find indices where timestamps would be inserted in df
    indices = np.searchsorted(timeline_data["timestamp"], timestamps, side="right")

    if is_ascending:
        for i in range(len(timestamps)):
            if i < len(timestamps) - 1 and indices[i] < len(timeline_data):
                # Check if the closest greater timestamp is not greater than next
                if timeline_data["timestamp"].iloc[indices[i]] <= timestamps[i + 1]:
                    values[i] = (
                        timeline_data["value"].iloc[indices[i]]
                        if indices[i] < len(timeline_data)
                        else 0
                    )
                else:
                    values[i] = values[i - 1] if i > 0 else 0
            elif indices[i] < len(timeline_data):
                values[i] = timeline_data["value"].iloc[indices[i]]
            else:
                values[i] = 0
    else:
        for i in range(len(timestamps)):
            if i < len(timestamps) - 1 and indices[i] > 0:
                # Check if the closest smaller timestamp is not smaller than next
                if timeline_data["timestamp"].iloc[indices[i] - 1] >= timestamps[i + 1]:
                    values[i] = (
                        timeline_data["value"].iloc[indices[i] - 1]
                        if indices[i] > 0
                        else 0
                    )
                else:
                    values[i] = values[i - 1] if i > 0 else 0
            elif indices[i] > 0:
                values[i] = timeline_data["value"].iloc[indices[i] - 1]
            else:
                values[i] = 0

    # Reverse values if descending
    if not is_ascending:
        values = values[::-1]

    return values.tolist()


def _uniformly_spread_timestamps(
    start,
    delta,
    end,
    max_items=TOTAL_NUMBER_OF_CANDLES_IN_CHART * STORAGE_LEDGER_EXPANSION_MULTIPLIER,
):
    """Return iterator of timestamps equally spread from `start` to `end`

    :param start: starting timestamp
    :type start: int
    :param delta: interval between adjacent timestamps
    :type delta: int
    :var end: ending timestamp
    :type end: int
    :return: iterator
    """

    def condition(x):
        if (delta < 0 and x <= start + delta * max_items) or (
            delta > 0 and x >= start + delta * max_items
        ):
            return False

        return x < end if delta > 0 else x > end

    return itertools.takewhile(
        condition, (start + i * delta for i in itertools.count())
    )


# # PROCESS
def _aggregate_bar_chart_data(asset_values, asset_tags):
    """Prepare and return data for historic widget bar chart from provided arguments`.

    :param asset_values: data with asset values for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var top_assets: collection of top valued assets in `asset_values` dataframe
    :type top_assets: list
    :var grouped_tag_totals: collection of timestamps and related tag/IDs with ALGO values
    :type grouped_tag_totals: dict
    :var dates: timestamps converted to appropriate date format
    :type dates: list
    :var data: collection of asset units and related values in ALGO
    :type data: dict
    :var unit_colors: collection of asset units/groups and related chart colors
    :type unit_colors: dict
    :return: dict
    """
    top_assets = _top_assets_and_groups(asset_values, asset_tags)
    grouped_tag_totals = _tag_totals_by_timestamps(asset_values, top_assets, asset_tags)
    dates = _timestamps_formatted_to_dates(list(grouped_tag_totals.keys()))
    unit_colors = _top_assets_chart_layout(top_assets, asset_tags)

    data = _chart_data_unit_datasets(
        grouped_tag_totals, top_assets, asset_tags, list(unit_colors.keys())
    )

    return _bar_chart_config(
        labels=dates,
        data=data,
        unit_colors=unit_colors,
    )


def _chart_data_unit_datasets(grouped_tag_totals, top_assets, asset_tags, units):
    """Return collection of asset units or groups with related values in ALGO.

    :param grouped_tag_totals: collection of timestamps and related tah/IDs with ALGO values
    :type grouped_tag_totals: dict
    :param top_assets: collection of top valued assets in `asset_values` dataframe
    :type top_assets: list
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var units: collection of all asset units/groups
    :type units: list
    :var data: collection of asset units and related values in ALGO
    :type data: dict
    :var index: currently processed timestamp's index in collection
    :type index: int
    :var values: currently processed timestamp's asset IDs and related values collection
    :type values: dict
    :var tag: currently processed asset or group
    :type tag: object
    :var value: currently processed asset/group value
    :type value: float
    :var unit: currently processed asset0s unit
    :type unit: str
    :return: dict
    """
    data = {unit: [0] * len(grouped_tag_totals) for unit in units}
    for index, (_, values) in enumerate(grouped_tag_totals.items()):
        for tag, value in values.items():
            if tag in top_assets:
                unit = _unit_or_tag_from_asset_tags(tag, asset_tags)

            else:
                unit = OTHERS_GROUP_NAME

            data[unit][index] = _microalgos_to_currency_algo(value)

    return data


def _create_bar_chart(asset_values, timeline_data, asset_tags):
    """Prepare and return data for bar chart from provided arguments.

    https://www.chartjs.org/docs/latest/samples/other-charts/combo-bar-line.html

    :param asset_values: data with asset values for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var bar_chart: bar chart's labels and datasets collection
    :type bar_chart: dict
    :var central_timestamps: collection of timestamps to initially render chart for
    :type central_timestamps: list
    :var timestamps: collection of timestamps to render chart for
    :type timestamps: list
    :var x_min: index of first initially visible chart's bar
    :type x_min: int
    :var x_max: index of last initially visible chart's bar
    :type x_max: int
    :var interval_values: collection of open, high, low, and close values for timestamps
    :type interval_values: dict
    :return: dict
    """
    bar_chart = _aggregate_bar_chart_data(asset_values, asset_tags)

    central_timestamps = [
        int(timestamp) for timestamp in asset_values["timestamp"].unique().tolist()
    ]

    timestamps, x_min, x_max = _extend_barchart_on_both_sides(
        bar_chart, central_timestamps, timeline_data
    )

    interval_values = _timeline_value_boundaries_for_timestamps(
        timeline_data, timestamps
    )
    _append_linechart_to_barchart(
        bar_chart, interval_values["low"], interval_values["high"]
    )

    return {"data": bar_chart, "xmin": x_min, "xmax": x_max}, timestamps


def _create_candlestick_chart(
    asset_values, timeline_data, candles_count=TOTAL_NUMBER_OF_CANDLES_IN_CHART
):
    """Prepare and return data for candlestick chart from provided arguments`.

    TODO: we'd need a custom plugin for changing the x-axis timestamps to
          formatted dates that fit the bar chart x-axis

    :param asset_values: asset values data for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param candles_count: total number of candles in the chart
    :type candles_count: int
    :var central_timestamps: collection of timestamps to initially render chart for
    :type central_timestamps: list
    :var timestamps: collection of timestamps to render chart for
    :type timestamps: list
    :var interval_values: collection of open, high, low, and close values for timestamps
    :type interval_values: dict
    :var data: collection of candle objects for timestamps
    :type data: dict
    :return: dict
    """
    central_timestamps = _candlestick_chart_timestamps(
        int(asset_values["timestamp"].min()),
        int(asset_values["timestamp"].max()),
        candles_count,
    )

    timestamps = _extend_candlestick_timestamps_on_both_sides(
        central_timestamps, timeline_data
    )
    interval_values = _timeline_value_boundaries_for_timestamps(
        timeline_data, timestamps
    )
    data = _candles_from_interval_values_for_timestamps(interval_values, timestamps)

    return {
        "data": _candlestick_chart_config(data=data),
        "xmin": central_timestamps[0] * 1000,
        "xmax": central_timestamps[-1] * 1000,
    }


def _tag_totals_by_timestamps(asset_values, top_assets, asset_tags):
    """Return collection of aggregated asset/group totals grouped by timestamps.

    :param asset_values: data with asset values for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param top_assets: collection of top valued assets in dataframe
    :type top_assets: list
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var result: collection of timestamps with related asset and calulated totals
    :type result: dict
    :var timestamp: currently processed dataframe's timestamp
    :type timestamp: int
    :var rows: currently processed timestamp's dataframe rows
    :type rows: :class:`pandas.DataFrame`
    :var subdict: currently processed timesamp's collection of assets and related totals
    :type subdict: dict
    :var others: currently processed timesamp's total for non-top assets and groups
    :type others: int
    :var row: currently processed timestamp's row
    :type row: :class:`pandas.Series`
    :var asset_id: currently processed row's asset identifier
    :type asset_id: int
    :var value: currently processed row's value in microAlgos
    :type value: int
    :return: dict
    """
    result = {}
    for timestamp, rows in asset_values.groupby("timestamp"):
        subdict = defaultdict(int)
        others = 0
        for _, row in rows.iterrows():
            asset_id = row["asset"]
            value = row["value"]
            if asset_id in top_assets:
                subdict[asset_id] += value

            elif (
                asset_tags.get(asset_id) in GROUPS_IN_ASSET_TAGS
                and asset_tags.get(asset_id) in top_assets
            ):
                subdict[asset_tags.get(asset_id)] += value

            else:
                others += value

        if others > 0:
            subdict[OTHERS_GROUP_NAME] = others

        result[timestamp] = dict(subdict)

    return dict(sorted(result.items()))


def _timeline_value_boundaries_for_timestamps(timeline_data, timestamps):
    """Prepare and return open, high, low, and close values collection for `timestamps`.

    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param timestamps: collection of timestamps to render chart for
    :type timestamps: list
    :var interval_values: collection of open, high, low, and close values for timestamps
    :type interval_values: dict
    :var start: starting timestamp in currently processed interval
    :type start: int
    :var end: ending timestamp in currently processed interval
    :type end: int
    :var filtered_data: timeline data filtered for currently processed interval
    :type filtered_data: :class:`pandas.DataFrame`
    :return: dict
    """
    interval_values = {
        "open": [0] * len(timestamps),
        "open_t": [0] * len(timestamps),
        "high": [0] * len(timestamps),
        "high_t": [0] * len(timestamps),
        "low": [0] * len(timestamps),
        "low_t": [0] * len(timestamps),
        "close": [0] * len(timestamps),
        "close_t": [0] * len(timestamps),
    }

    for index in range(len(timestamps)):
        start = timestamps[index]
        end = timestamps[index + 1] if index + 1 < len(timestamps) else None

        if end is None:
            filtered_data = timeline_data[timeline_data["timestamp"] >= start]

        else:
            filtered_data = timeline_data[
                (timeline_data["timestamp"] > start)
                & (timeline_data["timestamp"] <= end)
            ]

        if not filtered_data.empty:
            interval_values["open"][index] = _microalgos_to_currency_algo(
                filtered_data.iloc[0]["value"]
            )

            interval_values["open_t"][index] = int(filtered_data.iloc[0]["timestamp"])

            interval_values["high"][index] = _microalgos_to_currency_algo(
                filtered_data["value"].max()
            )

            timestamp = filtered_data.loc[filtered_data["value"].idxmax(), "timestamp"]
            if isinstance(timestamp, pd.Series):
                timestamp = timestamp.iloc[0]

            interval_values["high_t"][index] = int(timestamp)

            interval_values["low"][index] = _microalgos_to_currency_algo(
                filtered_data["value"].min()
            )

            timestamp = filtered_data.loc[filtered_data["value"].idxmin(), "timestamp"]
            if isinstance(timestamp, pd.Series):
                timestamp = timestamp.iloc[0]

            interval_values["low_t"][index] = int(timestamp)

            interval_values["close"][index] = _microalgos_to_currency_algo(
                filtered_data.iloc[-1]["value"]
            )

            interval_values["close_t"][index] = int(filtered_data.iloc[-1]["timestamp"])

    return interval_values


def _top_assets_and_groups(asset_values, asset_tags):
    """Return top valued assets/groups from provided `asset_values` dataframe.

    :param asset_values: data with asset values for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var totals: assets and groups collection with aggregated related totals
    :type totals: :class:`pandas.DataFrame`
    :var group_name: name of the currently processed group (NFT or LOFTY)
    :type group_name: str
    :var group_assets: asset IDs belonging to the currently processed group
    :type group_assets: set
    :var group_value: currently processed group's total value
    :type group_value: float
    :var top_assets: collection of assets/groups sorted by their related totals
    :type top_assets: list
    :return: list
    """
    totals = asset_values.groupby("asset")["value"].sum().reset_index()
    for group_name in GROUPS_IN_ASSET_TAGS:
        group_assets = {
            asset_id
            for asset_id in asset_tags
            if asset_tags.get(asset_id) == group_name
        }
        group_value = totals[totals["asset"].isin(group_assets)]["value"].sum()
        totals = totals[~totals["asset"].isin(group_assets)]
        totals = pd.concat(
            [totals, pd.DataFrame([{"asset": group_name, "value": group_value}])],
            ignore_index=True,
        )

    top_assets = (
        totals.sort_values("value", ascending=False)
        .head(MAX_NUMBER_OF_ASSETS_IN_CHART)["asset"]
        .tolist()
    )
    return top_assets + [OTHERS_GROUP_NAME]


def charts_data_from_asset_values_and_timeline_data(
    asset_values, timeline_data, asset_tags
):
    """Return bar and candlestick chart data instances created from provided arguments.

    :param asset_values: asset values data for equally distributed timestamps
    :type asset_values: :class:`pandas.DataFrame`
    :param timeline_data: evaluated timestamps across the chart's timeline
    :type timeline_data: :class:`pandas.DataFrame`
    :param asset_tags: collection of assets and related units or associated groups
    :type asset_tags: dict
    :var bar_chart: bar chart labels and datasets collection
    :type bar_chart: dict
    :var extended_timestamps: chart's extended timestamps collection
    :type extended_timestamps: list
    :var candlestick_chart: candlestick chart labels and datasets collection
    :type candlestick_chart: dict
    :return: two-tuple
    """
    bar_chart, extended_timestamps = _create_bar_chart(
        asset_values, timeline_data, asset_tags
    )
    candlestick_chart = _create_candlestick_chart(asset_values, timeline_data)

    # import json
    # path = "/home/ipaleka/Downloads/540_bar_chart.json"
    # with open(path, "w") as json_file:
    #     json.dump(bar_chart, json_file)
    # path = "/home/ipaleka/Downloads/540_candlestick_chart.json"
    # with open(path, "w") as json_file:
    #     json.dump(candlestick_chart, json_file)

    return {"bars": bar_chart, "candles": candlestick_chart}, extended_timestamps


def consolidated_view_charts_from_assets_data(assets_data):
    """Create consolidated view's charts from provided `assets_data` collection.

    :param assets_data: processed asset section data ready for rendering
    :type assets_data: dict
    :var asachart: data for ASA chart rendering
    :type asachart: dict
    :var nftchart: data for NFT chart rendering
    :type nftchart: dict
    :var colors: collection of asset ids and related colors
    :type colors: dict
    :var nft_colors: collection of NFT ids and related colors
    :type nft_colors: dict
    :var distchart: data for rendering top ASA distribution chart
    :type distchart: dict
    :var ratiochart: data for rendering ALGO/ASA/NFT chart
    :type ratiochart: dict
    :var nftfloorchart: data for rendering NFT floors chart
    :type nftfloorchart: dict
    :var consolidated: consolidated view totals
    :type consolidated: :class:`utils.structs.Consolidated`
    :return: dict
    """
    asachart, nftchart, colors, nft_colors = prepare_base_charts_from_assets_data(
        assets_data
    )
    distchart, ratiochart, consolidated = prepare_consolidated_charts_from_assets_data(
        assets_data
    )
    return {
        "asachart": asachart,
        "nftchart": nftchart,
        "colors": colors,
        "nft_colors": nft_colors,
        "distchart": distchart,
        "ratiochart": ratiochart,
        "consolidated": consolidated,
    }
