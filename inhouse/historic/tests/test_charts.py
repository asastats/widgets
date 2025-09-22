"""Testing module for historic widget's charts module."""

from unittest import mock

import numpy as np
import pandas as pd

import widgets.inhouse.historic.charts
from widgets.inhouse.historic.charts import (
    _aggregate_bar_chart_data,
    _append_linechart_to_barchart,
    _apply_extended_timestamps_to_bar_chart,
    _bar_chart_config,
    _candles_from_interval_values_for_timestamps,
    _candlestick_chart_config,
    _candlestick_chart_timestamps,
    _chart_data_unit_datasets,
    _create_bar_chart,
    _extend_barchart_on_both_sides,
    _create_candlestick_chart,
    _extend_candlestick_timestamps_on_both_sides,
    _extended_timestamps,
    _microalgos_to_currency_algo,
    _tag_totals_by_timestamps,
    _timeline_data_values_for_timestamps,
    _timeline_value_boundaries_for_timestamps,
    _timestamps_formatted_to_dates,
    _top_assets_and_groups,
    _top_assets_chart_layout,
    _uniformly_spread_timestamps,
    _unit_or_tag_from_asset_tags,
    asset_values_from_computed_data,
    charts_data_from_asset_values_and_timeline_data,
    consolidated_view_charts_from_assets_data,
)
from widgets.inhouse.historic.constants import (
    DISTINCT_COLORS,
    GROUPS_IN_ASSET_TAGS,
    OTHERS_GROUP_NAME,
    TOTAL_NUMBER_OF_CANDLES_IN_CHART,
)


class TestWidgetsHistoricChartsHelpers:
    """Testing class for :py:mod:`widgets.inhouse.historic.charts` helpers functions."""

    # # _append_linechart_to_barchart
    def test_widgets_inhouse_historic_charts_append_linechart_to_barchart_functionality(
        self, mocker
    ):
        low_values, high_values = mocker.MagicMock(), mocker.MagicMock()
        chart_data = {
            "labels": [1, 2, 3],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }
        _append_linechart_to_barchart(chart_data, low_values, high_values)
        assert chart_data == {
            "labels": [1, 2, 3],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
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
            ],
        }

    # # _bar_chart_config
    def test_widgets_inhouse_historic_charts_bar_chart_config_for_empty_arguments(self):
        returned = _bar_chart_config()
        assert returned == {"labels": [], "datasets": []}

    def test_widgets_inhouse_historic_chart_bar_chart_config_functionality(
        self, mocker
    ):
        labels = [mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()]
        color1, color2, color3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        unit_colors = {"ALGO": color1, "ASASTATS": color2, "USDC": color3}
        data = {
            "ALGO": [100, 200, 300],
            "ASASTATS": [0, 800, 0],
        }
        returned = _bar_chart_config(labels=labels, data=data, unit_colors=unit_colors)
        assert returned == {
            "labels": labels,
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": color1,
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": color2,
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "USDC",
                    "data": [],
                    "backgroundColor": color3,
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }

    # # _candlestick_chart_config
    def test_widgets_inhouse_historic_charts_candlestick_chart_config_functionality(
        self, mocker
    ):
        data = mocker.MagicMock()
        returned = _candlestick_chart_config(data)
        assert returned == {"datasets": [{"data": data, "barThickness": "flex"}]}

    # # _candlestick_chart_timestamps
    def test_widgets_inhouse_historic_charts_candlestick_chart_timestamps_interval_0(
        self,
    ):
        diff = 10
        min_timestamp, max_timestamp, candles_count = 1659850000, 1659850000 + diff, 48
        returned = _candlestick_chart_timestamps(
            min_timestamp, max_timestamp, candles_count
        )
        assert isinstance(returned, list)
        assert len(returned) == diff
        assert returned == [
            1659850001,
            1659850002,
            1659850003,
            1659850004,
            1659850005,
            1659850006,
            1659850007,
            1659850008,
            1659850009,
            1659850010,
        ]

    def test_widgets_inhouse_historic_charts_candlestick_chart_timestamps_functionality(
        self,
    ):
        min_timestamp, max_timestamp, candles_count = 1659850000, 1659898000, 48
        returned = _candlestick_chart_timestamps(
            min_timestamp, max_timestamp, candles_count
        )
        assert isinstance(returned, list)
        assert len(returned) == 48
        assert returned[:5] == [
            1659851000,
            1659852000,
            1659853000,
            1659854000,
            1659855000,
        ]
        assert returned[-5:] == [
            1659894000,
            1659895000,
            1659896000,
            1659897000,
            1659898000,
        ]

    # # _candles_from_interval_values_for_timestamps
    def test_widgets_inhouse_historic_candles_from_interval_values_for_timestamps_funct(
        self,
    ):
        open1, open2, open3, open4 = 100, 200, 300, 400
        opent1, opent2, opent3, opent4 = 1679850000, 1679850001, 1679850002, 1679850003
        high1, high2, high3, high4 = 600, 700, 800, 900
        hight1, hight2, hight3, hight4 = 1689850001, 1689850002, 1689850003, 1689850004
        low1, low2, low3, low4 = 50, 60, 70, 80
        lowt1, lowt2, lowt3, lowt4 = 1699850001, 1699850002, 1699850003, 1699850004
        close1, close2, close3, close4 = 200, 300, 400, 500
        closet1, closet2, closet3, closet4 = (
            1709850001,
            1709850002,
            1709850003,
            1709850004,
        )
        interval_values = {
            "open": [open1, open2, open3, open4],
            "open_t": [opent1, opent2, opent3, opent4],
            "high": [high1, high2, high3, high4],
            "high_t": [hight1, hight2, hight3, hight4],
            "low": [low1, low2, low3, low4],
            "low_t": [lowt1, lowt2, lowt3, lowt4],
            "close": [close1, close2, close3, close4],
            "close_t": [closet1, closet2, closet3, closet4],
        }
        timestamp1, timestamp2, timestamp3, timestamp4 = (
            1679850000,
            1689850000,
            1699850000,
            1709850000,
        )
        returned = _candles_from_interval_values_for_timestamps(
            interval_values, [timestamp1, timestamp2, timestamp3, timestamp4]
        )
        assert returned == [
            {
                "x": timestamp1 * 1000,
                "o": open1,
                "h": high1,
                "l": low1,
                "c": close1,
                "ot": opent1,
                "ht": hight1,
                "lt": lowt1,
                "ct": closet1,
            },
            {
                "x": timestamp2 * 1000,
                "o": open2,
                "h": high2,
                "l": low2,
                "c": close2,
                "ot": opent2,
                "ht": hight2,
                "lt": lowt2,
                "ct": closet2,
            },
            {
                "x": timestamp3 * 1000,
                "o": open3,
                "h": high3,
                "l": low3,
                "c": close3,
                "ot": opent3,
                "ht": hight3,
                "lt": lowt3,
                "ct": closet3,
            },
            {
                "x": timestamp4 * 1000,
                "o": open4,
                "h": high4,
                "l": low4,
                "c": close4,
                "ot": opent4,
                "ht": hight4,
                "lt": lowt4,
                "ct": closet4,
            },
        ]

    # # _microalgos_to_currency_algo
    def test_widgets_inhouse_historic_charts_microalgos_to_currency_algo_rounded(self):
        value = np.int64(123456789)
        returned = _microalgos_to_currency_algo(value)
        assert returned == 123.46

    def test_widgets_inhouse_historic_charts_microalgos_to_currency_algo_truncated(
        self,
    ):
        value = 5000000
        returned = _microalgos_to_currency_algo(value)
        assert returned == 5.0

    # # _timestamps_formatted_to_dates
    def test_widgets_inhouse_historic_charts_timestamps_formatted_no_timestamps(self):
        timestamps = []
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == []

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_months(
        self,
    ):
        first = 1659850000
        last = 1745250010
        timestamps = [
            timestamp for timestamp in range(first, last + 1, (last - first) // 4)
        ]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == ["Aug 2022", "Apr 2023", "Dec 2023", "Aug 2024", "Apr 2025"]

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_days(
        self,
    ):
        first = 1659850000
        last = 1670930002
        timestamps = [
            timestamp for timestamp in range(first, last + 1, (last - first) // 4)
        ]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == [
            "8/7/2022",
            "9/8/2022",
            "10/10/2022",
            "11/11/2022",
            "12/13/2022",
        ]

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_hours(
        self,
    ):
        first = 1745250010
        last = 1745450010
        timestamps = [
            timestamp for timestamp in range(first, last + 1, (last - first) // 4)
        ]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == [
            "4/21/25 15:40",
            "4/22/25 05:33",
            "4/22/25 19:26",
            "4/23/25 09:20",
            "4/23/25 23:13",
        ]

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_minutes(
        self,
    ):
        first = 1745250010
        last = 1745260010
        timestamps = [
            timestamp for timestamp in range(first, last + 1, (last - first) // 4)
        ]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == [
            "4/21 15:40:10",
            "4/21 16:21:50",
            "4/21 17:03:30",
            "4/21 17:45:10",
            "4/21 18:26:50",
        ]

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_seconds(
        self,
    ):
        first = 1745250010
        last = 1745250110
        timestamps = [
            timestamp for timestamp in range(first, last + 1, (last - first) // 4)
        ]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == [
            "4/21 15:40:10",
            "4/21 15:40:35",
            "4/21 15:41:00",
            "4/21 15:41:25",
            "4/21 15:41:50",
        ]

    def test_widgets_inhouse_historic_charts_timestamps_formatted_to_dates_for_equal(
        self,
    ):
        timestamps = [1745250010, 1745250010, 1745250010, 1745250010, 1745250010]
        returned = _timestamps_formatted_to_dates(timestamps)
        assert returned == [
            "4/21 15:40:10",
            "4/21 15:40:10",
            "4/21 15:40:10",
            "4/21 15:40:10",
            "4/21 15:40:10",
        ]

    # # _top_assets_chart_layout
    def test_widgets_inhouse_historic_charts_top_assets_chart_layout_no_groups(
        self,
    ):
        asset_id1, asset_id2, asset_id3 = 505, 506, 507
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        top_assets = [asset_id1, asset_id2, asset_id3]
        asset_tags = {asset_id1: unit1, asset_id2: unit2, asset_id3: unit3}
        returned = _top_assets_chart_layout(top_assets, asset_tags)
        assert returned == {
            unit1: DISTINCT_COLORS[0],
            unit2: DISTINCT_COLORS[1],
            unit3: DISTINCT_COLORS[2],
        }

    def test_widgets_inhouse_historic_charts_top_assets_chart_layout_functionality(
        self,
    ):
        asset_id1, asset_id2, asset_id3 = 505, 506, 507
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        top_assets = [
            OTHERS_GROUP_NAME,
            asset_id1,
            GROUPS_IN_ASSET_TAGS[0],
            GROUPS_IN_ASSET_TAGS[1],
            asset_id2,
            asset_id3,
        ]
        asset_tags = {asset_id1: unit1, asset_id2: unit2, asset_id3: unit3}
        returned = _top_assets_chart_layout(top_assets, asset_tags)
        assert returned == {
            unit1: DISTINCT_COLORS[0],
            unit2: DISTINCT_COLORS[1],
            unit3: DISTINCT_COLORS[2],
            GROUPS_IN_ASSET_TAGS[0]: DISTINCT_COLORS[3],
            GROUPS_IN_ASSET_TAGS[1]: DISTINCT_COLORS[4],
            OTHERS_GROUP_NAME: DISTINCT_COLORS[5],
        }

    # _unit_or_tag_from_asset_tags
    def test_widgets_inhouse_historic_charts_unit_or_tag_from_asset_tags_for_asset(
        self,
    ):
        asset_id1, asset_id2, asset_id3 = 505, 506, 507
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        asset_tags = {asset_id1: unit1, asset_id2: unit2, asset_id3: unit3}
        returned = _unit_or_tag_from_asset_tags(asset_id2, asset_tags)
        assert returned == unit2

    def test_widgets_inhouse_historic_charts_unit_or_tag_from_asset_tags_for_tag(
        self,
    ):
        asset_id1, asset_id2, asset_id3 = 505, 506, 507
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        asset_tags = {asset_id1: unit1, asset_id2: unit2, asset_id3: unit3}
        tag = "NFT"
        returned = _unit_or_tag_from_asset_tags(tag, asset_tags)
        assert returned == tag

    # # asset_values_from_computed_data
    def test_widgets_inhouse_historic_charts_asset_values_from_computed_data_empty(
        self,
    ):
        computed_data = pd.DataFrame.from_dict(
            {
                "timestamp": [],
                "asset": [],
                "foobar": [],
                "value": [],
            }
        )
        returned = asset_values_from_computed_data(computed_data)
        assert isinstance(returned, pd.DataFrame)
        assert returned.shape == (0, 3)

    def test_widgets_inhouse_historic_charts_asset_values_from_computed_data_funct(
        self, mocker
    ):
        timestamp1, timestamp2, timestamp3 = 1652500100, 1652800100, 1672500000
        asset_id1, asset_id2, asset_id3, asset_id4 = 505, 506, 507, 508
        value1, value2, value3, value4, value5, value6, value7, value8 = (
            1500,
            2100,
            1800,
            4300,
            2000,
            1805,
            2120,
            4500,
        )
        computed_data = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp3,
                    timestamp2,
                    timestamp1,
                ],
                "asset": [
                    asset_id3,
                    asset_id3,
                    asset_id1,
                    asset_id2,
                    asset_id2,
                    asset_id1,
                    asset_id2,
                    asset_id4,
                ],
                "foobar": [
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                ],
                "value": [
                    value1,
                    value2,
                    value3,
                    value4,
                    value5,
                    value6,
                    value7,
                    value8,
                ],
            }
        )
        returned = asset_values_from_computed_data(computed_data)
        assert isinstance(returned, pd.DataFrame)
        assert list(returned.columns) == [
            "timestamp",
            "asset",
            "value",
        ]
        assert list(returned.timestamp) == [
            timestamp1,
            timestamp1,
            timestamp1,
            timestamp1,
            timestamp2,
            timestamp2,
            timestamp3,
            timestamp3,
        ]
        assert list(returned.asset) == [
            asset_id4,
            asset_id2,
            asset_id1,
            asset_id3,
            asset_id2,
            asset_id3,
            asset_id2,
            asset_id1,
        ]
        assert list(returned.value) == [
            value8,
            value4,
            value3,
            value1,
            value7,
            value2,
            value5,
            value6,
        ]


class TestWidgetsHistoricChartsExtend:
    """Testing class for :py:mod:`widgets.inhouse.historic.charts` extend functions."""

    # # _apply_extended_timestamps_to_bar_chart
    def test_widgets_inhouse_historic_apply_extended_timestamps_to_bar_chart_no_extend(
        self, mocker
    ):
        timeline_data = mocker.MagicMock()
        left_timestamps, right_timestamps = [], []
        bar_chart = {
            "labels": ["label1", "label2", "label3", "label4", "label5"],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "USDC",
                    "data": [],
                    "backgroundColor": "color3",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }
        mocked_values = mocker.patch(
            "widgets.inhouse.historic.charts._timeline_data_values_for_timestamps"
        )
        mocked_microalgos = mocker.patch(
            "widgets.inhouse.historic.charts._microalgos_to_currency_algo"
        )
        _apply_extended_timestamps_to_bar_chart(
            bar_chart, timeline_data, left_timestamps, right_timestamps
        )
        assert bar_chart == {
            "labels": ["label1", "label2", "label3", "label4", "label5"],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "USDC",
                    "data": [],
                    "backgroundColor": "color3",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }
        mocked_values.assert_not_called()
        mocked_microalgos.assert_not_called()

    def test_widgets_inhouse_historic_apply_extended_timestamps_to_bar_chart_funct(
        self, mocker
    ):
        timeline_data = mocker.MagicMock()
        left_timestamps = [1677050015, 1677150015, 1677250015]
        right_timestamps = [1682050015, 1687150015]
        bar_chart = {
            "labels": ["label1", "label2", "label3", "label4", "label5"],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [100, 200, 300],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 800, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "others",
                    "data": [],
                    "backgroundColor": "color3",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }
        value1, value2, value3, value4, value5 = (
            1_000_000,
            2_000_000,
            3_000_000,
            4_000_000,
            5_000_000,
        )
        mocked_values = mocker.patch(
            "widgets.inhouse.historic.charts._timeline_data_values_for_timestamps",
            side_effect=[(value1, value2, value3), (value4, value5)],
        )
        _apply_extended_timestamps_to_bar_chart(
            bar_chart, timeline_data, left_timestamps, right_timestamps
        )
        assert bar_chart == {
            "labels": [
                "2/22/23 07:13",
                "2/23/23 11:00",
                "2/24/23 14:46",
                "label1",
                "label2",
                "label3",
                "label4",
                "label5",
                "4/21/2023",
                "6/19/2023",
            ],
            "datasets": [
                {
                    "label": "ALGO",
                    "data": [0, 0, 0, 100, 200, 300, 0, 0],
                    "backgroundColor": "color1",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "ASASTATS",
                    "data": [0, 0, 0, 0, 800, 0, 0, 0],
                    "backgroundColor": "color2",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
                {
                    "label": "others",
                    "data": [1.0, 2.0, 3.0, 4.0, 5.0],
                    "backgroundColor": "color3",
                    "borderWidth": 0,
                    "hoverOffset": 0,
                    "order": 1,
                },
            ],
        }
        calls = [
            mocker.call(left_timestamps, timeline_data),
            mocker.call(right_timestamps, timeline_data),
        ]
        mocked_values.assert_has_calls(calls, any_order=True)
        assert mocked_values.call_count == 2

    # # _extend_barchart_on_both_sides
    def test_widgets_inhouse_historic_charts_extend_barchart_on_both_sides_no_extend(
        self, mocker
    ):
        bar_chart, timeline_data = mocker.MagicMock(), mocker.MagicMock()
        central_timestamps = [1677050015, 1677150015, 1677250015]
        left_timestamps = []
        right_timestamps = []
        mocked_extended = mocker.patch(
            "widgets.inhouse.historic.charts._extended_timestamps",
            return_value=(left_timestamps, right_timestamps),
        )
        mocked_apply = mocker.patch(
            "widgets.inhouse.historic.charts._apply_extended_timestamps_to_bar_chart"
        )
        returned = _extend_barchart_on_both_sides(
            bar_chart, central_timestamps, timeline_data
        )
        assert returned == (central_timestamps, 0, 2)
        mocked_extended.assert_called_once_with(central_timestamps, timeline_data)
        mocked_apply.assert_not_called()

    def test_widgets_inhouse_historic_charts_extend_barchart_on_both_sides_funct(
        self, mocker
    ):
        bar_chart, timeline_data = mocker.MagicMock(), mocker.MagicMock()
        central_timestamps = [1677050015, 1677150015, 1677250015]
        left_timestamps = [1639850000, 1649850000, 1659850000]
        right_timestamps = [1682850000, 1689850000, 1690850000, 1700850000]
        mocked_extended = mocker.patch(
            "widgets.inhouse.historic.charts._extended_timestamps",
            return_value=(left_timestamps, right_timestamps),
        )
        mocked_apply = mocker.patch(
            "widgets.inhouse.historic.charts._apply_extended_timestamps_to_bar_chart"
        )
        returned = _extend_barchart_on_both_sides(
            bar_chart, central_timestamps, timeline_data
        )
        assert returned == (
            [
                1639850000,
                1649850000,
                1659850000,
                1677050015,
                1677150015,
                1677250015,
                1682850000,
                1689850000,
                1690850000,
                1700850000,
            ],
            3,
            5,
        )
        mocked_extended.assert_called_once_with(central_timestamps, timeline_data)
        mocked_apply.assert_called_once_with(
            bar_chart, timeline_data, left_timestamps, right_timestamps
        )

    # # _extend_candlestick_timestamps_on_both_sides
    def test_widgets_inhouse_historic_charts_extend_candlestick_timestamps_funct(
        self, mocker
    ):
        timeline_data = mocker.MagicMock()
        central_timestamps = [
            1677050015,
            1677150015,
            1677250015,
        ]
        left_timestamps = [
            1639850000,
            1649850000,
            1659850000,
        ]
        right_timestamps = [
            1682850000,
            1689850000,
            1690850000,
            1700850000,
        ]
        mocked_extended = mocker.patch(
            "widgets.inhouse.historic.charts._extended_timestamps",
            return_value=(left_timestamps, right_timestamps),
        )
        returned = _extend_candlestick_timestamps_on_both_sides(
            central_timestamps, timeline_data
        )
        assert returned == [
            1639850000,
            1649850000,
            1659850000,
            1677050015,
            1677150015,
            1677250015,
            1682850000,
            1689850000,
            1690850000,
            1700850000,
        ]
        mocked_extended.assert_called_once_with(central_timestamps, timeline_data)

    # # _extended_timestamps
    def test_widgets_inhouse_historic_charts_extended_timestamps_for_initial_period(
        self,
    ):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1691950020,
                    1715420051,
                    1725420051,
                    1729420051,
                    1734420051,
                    1745420051,
                ],
                "value": [
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                    200,
                    300,
                    400,
                    500,
                    800,
                ],
            }
        )
        central_timestamps = [
            1669850000,
            1685420051,
            1705420051,
            1725420051,
            1745420051,
        ]
        returned = _extended_timestamps(central_timestamps, timeline_data)
        assert returned == ([], [])

    def test_widgets_inhouse_historic_charts_extended_timestamps_for_prepend_and_append(
        self,
    ):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1711950020,
                ],
                "value": [
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                ],
            }
        )
        central_timestamps = [1672050015, 1679650015, 1687250015]
        returned = _extended_timestamps(central_timestamps, timeline_data)
        assert returned[0][0] == 1659850000
        assert returned[1][-1] == 1711950020

    def test_widgets_inhouse_historic_charts_extended_timestamps_interval_0(self):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1628450000,
                    1638450000,
                    1648450000,
                    1659250000,
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1691950020,
                    1715420051,
                    1725420051,
                    1729420051,
                    1734420051,
                    1745420051,
                ],
                "value": [
                    800,
                    750,
                    800,
                    2000,
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                    200,
                    300,
                    400,
                    500,
                    800,
                ],
            }
        )
        central_timestamps = [1672050015, 1672050015, 1672050016]
        returned = _extended_timestamps(central_timestamps, timeline_data)
        assert len(returned[0]) == 96
        assert len(returned[1]) == 96
        assert returned[0][:5] == [
            1672049919,
            1672049920,
            1672049921,
            1672049922,
            1672049923,
        ]
        assert returned[0][-5:] == [
            1672050010,
            1672050011,
            1672050012,
            1672050013,
            1672050014,
        ]
        assert returned[1][:5] == [
            1672050017,
            1672050018,
            1672050019,
            1672050020,
            1672050021,
        ]
        assert returned[1][-5:] == [
            1672050108,
            1672050109,
            1672050110,
            1672050111,
            1672050112,
        ]

    def test_widgets_inhouse_historic_charts_extended_timestamps_functionality(self):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1628450000,
                    1638450000,
                    1648450000,
                    1659250000,
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1691950020,
                    1715420051,
                    1725420051,
                    1729420051,
                    1734420051,
                    1745420051,
                ],
                "value": [
                    800,
                    750,
                    800,
                    2000,
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                    200,
                    300,
                    400,
                    500,
                    800,
                ],
            }
        )
        central_timestamps = [1672050015, 1679650015, 1687250015, 1694850015]
        returned = _extended_timestamps(central_timestamps, timeline_data)
        assert returned == (
            [
                1628450000,
                1632150015,
                1637850015,
                1643550015,
                1649250015,
                1654950015,
                1660650015,
                1666350015,
            ],
            [
                1700550015,
                1706250015,
                1711950015,
                1717650015,
                1723350015,
                1729050015,
                1734750015,
                1740450015,
            ],
        )

    # # _timeline_data_values_for_timestamps
    def test_widgets_inhouse_historic_charts_timeline_data_values_for_timestamps_1(
        self,
    ):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1691950020,
                    1715420051,
                    1725420051,
                    1729420051,
                    1734420051,
                    1745420051,
                ],
                "value": [
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                    200,
                    300,
                    400,
                    500,
                    800,
                ],
            }
        )
        timestamps = [1676950015, 1677050015, 1677150015, 1677250015, 1677350015]
        returned = _timeline_data_values_for_timestamps(timestamps, timeline_data)
        assert list(returned) == [700, 700, 700, 400, 300]

    def test_widgets_inhouse_historic_charts_timeline_data_values_for_timestamps_2(
        self,
    ):
        timeline_data = pd.DataFrame(
            {
                "timestamp": [
                    1659850000,
                    1659950000,
                    1661250000,
                    1672850000,
                    1675850000,
                    1676950010,
                    1677040020,
                    1677250020,
                    1677950020,
                    1691950020,
                    1715420051,
                    1725420051,
                    1729420051,
                    1734420051,
                    1745420051,
                ],
                "value": [
                    2000,
                    800,
                    2000,
                    1100,
                    100,
                    500,
                    700,
                    400,
                    300,
                    2300,
                    200,
                    300,
                    400,
                    500,
                    800,
                ],
            }
        )
        timestamps = [1676950015, 1677050015, 1677150015, 1677250015, 1677350015]
        returned = _timeline_data_values_for_timestamps(timestamps, timeline_data)
        assert list(returned) == [700, 700, 700, 400, 300]

    # # _uniformly_spread_timestamps
    def test_widgets_inhouse_historic_charts_uniformly_spread_timestamps_increasing(
        self,
    ):
        assert list(_uniformly_spread_timestamps(0, 3, 10)) == [0, 3, 6, 9]

    def test_widgets_inhouse_historic_charts_uniformly_spread_timestamps_decreasing(
        self,
    ):
        assert list(_uniformly_spread_timestamps(2, -0.5, 0)) == [2.0, 1.5, 1.0, 0.5]

    def test_widgets_inhouse_historic_charts_uniformly_spread_max_items_increasing(
        self,
    ):
        returned = list(_uniformly_spread_timestamps(200, 0.01, 1000))
        assert len(returned) == 96
        assert returned[:5] == [200.0, 200.01, 200.02, 200.03, 200.04]
        assert returned[-5:] == [200.91, 200.92, 200.93, 200.94, 200.95]

    def test_widgets_inhouse_historic_charts_uniformly_spread_max_items_decreasing(
        self,
    ):
        returned = list(_uniformly_spread_timestamps(200, -0.01, 10))
        assert len(returned) == 96
        assert returned[:5] == [200.0, 199.99, 199.98, 199.97, 199.96]
        assert returned[-5:] == [199.09, 199.08, 199.07, 199.06, 199.05]


class TestWidgetsHistoricChartsProcess:
    """Testing class for :py:mod:`widgets.inhouse.historic.charts` process functions."""

    # # _aggregate_bar_chart_data
    def test_widgets_inhouse_historic_charts_aggregate_bar_chart_data_functionality(
        self, mocker
    ):
        asset_values, asset_tags = (mocker.MagicMock(), mocker.MagicMock())
        mocked_top = mocker.patch(
            "widgets.inhouse.historic.charts._top_assets_and_groups"
        )
        grouped_data = {
            "key1": mocker.MagicMock(),
            "key2": mocker.MagicMock(),
            "key3": mocker.MagicMock(),
        }
        mocked_tags = mocker.patch(
            "widgets.inhouse.historic.charts._tag_totals_by_timestamps",
            return_value=grouped_data,
        )
        mocked_dates = mocker.patch(
            "widgets.inhouse.historic.charts._timestamps_formatted_to_dates"
        )
        mocked_data = mocker.patch(
            "widgets.inhouse.historic.charts._chart_data_unit_datasets"
        )
        unit_colors = {
            "unit1": mocker.MagicMock(),
            "unit2": mocker.MagicMock(),
            "unit3": mocker.MagicMock(),
        }
        mocked_colors = mocker.patch(
            "widgets.inhouse.historic.charts._top_assets_chart_layout",
            return_value=unit_colors,
        )
        mocked_chart = mocker.patch("widgets.inhouse.historic.charts._bar_chart_config")
        returned = _aggregate_bar_chart_data(asset_values, asset_tags)
        assert returned == mocked_chart.return_value
        mocked_top.assert_called_once_with(asset_values, asset_tags)
        mocked_tags.assert_called_once_with(
            asset_values, mocked_top.return_value, asset_tags
        )
        mocked_data.assert_called_once_with(
            mocked_tags.return_value,
            mocked_top.return_value,
            asset_tags,
            ["unit1", "unit2", "unit3"],
        )
        mocked_dates.assert_called_once_with(["key1", "key2", "key3"])
        mocked_colors.assert_called_once_with(mocked_top.return_value, asset_tags)
        mocked_chart.assert_called_once_with(
            labels=mocked_dates.return_value,
            data=mocked_data.return_value,
            unit_colors=mocked_colors.return_value,
        )

    # # _chart_data_unit_datasets
    def test_widgets_inhouse_historic_charts_chart_data_unit_datasets_functionality(
        self,
    ):
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5 = 505, 506, 507, 508, 509
        unit1, unit2, unit3, unit4, unit5 = "unit1", "unit2", "unit3", "unit4", "unit5"
        asset_tags = {
            asset_id1: unit1,
            asset_id2: unit2,
            asset_id3: unit3,
            asset_id4: unit4,
            asset_id5: unit5,
        }
        value1, value2, value3, value4, value5, value6, value7, value8 = (
            105850000,
            24852854,
            37895421,
            70000000,
            456700,
            45000000,
            5500000,
            1000000,
        )
        top_assets = [asset_id4, asset_id5, GROUPS_IN_ASSET_TAGS[1], asset_id2]
        grouped_tag_totals = {
            "key1": {asset_id3: value1, GROUPS_IN_ASSET_TAGS[1]: value2},
            "key2": {
                asset_id2: value3,
                GROUPS_IN_ASSET_TAGS[1]: value4,
                asset_id1: value5,
                "LOFTY": value6,
            },
            "key3": {asset_id4: value7},
            "key4": {asset_id3: value8},
        }
        units = [GROUPS_IN_ASSET_TAGS[1], unit2, OTHERS_GROUP_NAME, unit4]
        returned = _chart_data_unit_datasets(
            grouped_tag_totals, top_assets, asset_tags, units
        )
        assert returned == {
            GROUPS_IN_ASSET_TAGS[1]: [24.85, 70.0, 0, 0],
            unit2: [0, 37.9, 0, 0],
            OTHERS_GROUP_NAME: [105.85, 45.0, 0, 1.0],
            unit4: [0, 0, 5.5, 0],
        }

    # # _create_bar_chart
    def test_widgets_inhouse_historic_charts_create_bar_chart_functionality(
        self, mocker
    ):
        timeline_data, asset_tags = mocker.MagicMock(), mocker.MagicMock()
        timestamp1, timestamp2, timestamp3 = (
            np.int64(1652500100),
            np.int64(1652800100),
            np.int64(1672500000),
        )
        asset_id1, asset_id2, asset_id3, asset_id4 = 505, 506, 507, 508
        value1, value2, value3, value4, value5, value6, value7, value8 = (
            1500,
            2100,
            1800,
            4300,
            2000,
            1805,
            2120,
            4500,
        )
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp3,
                    timestamp2,
                    timestamp1,
                ],
                "asset": [
                    asset_id3,
                    asset_id3,
                    asset_id1,
                    asset_id2,
                    asset_id2,
                    asset_id1,
                    asset_id2,
                    asset_id4,
                ],
                "value": [
                    value1,
                    value2,
                    value3,
                    value4,
                    value5,
                    value6,
                    value7,
                    value8,
                ],
            }
        )
        bar_chart = mocker.MagicMock()
        mocked_chart = mocker.patch(
            "widgets.inhouse.historic.charts._aggregate_bar_chart_data",
            return_value=bar_chart,
        )
        timestamps, x_min, x_max = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_extend = mocker.patch(
            "widgets.inhouse.historic.charts._extend_barchart_on_both_sides",
            return_value=(timestamps, x_min, x_max),
        )
        interval_values = {
            "open": mocker.MagicMock(),
            "high": mocker.MagicMock(),
            "low": mocker.MagicMock(),
            "close": mocker.MagicMock(),
        }
        mocked_interval = mocker.patch(
            "widgets.inhouse.historic.charts._timeline_value_boundaries_for_timestamps",
            return_value=interval_values,
        )
        mocked_append = mocker.patch(
            "widgets.inhouse.historic.charts._append_linechart_to_barchart"
        )
        returned = _create_bar_chart(asset_values, timeline_data, asset_tags)
        assert returned == (
            {"data": bar_chart, "xmin": x_min, "xmax": x_max},
            timestamps,
        )
        mocked_chart.assert_called_once()
        assert len(mocked_chart.call_args_list[0].args) == 2
        assert len(mocked_chart.call_args_list[0].kwargs) == 0
        assert list(mocked_chart.call_args_list[0].args[0].columns) == [
            "timestamp",
            "asset",
            "value",
        ]
        assert list(mocked_chart.call_args_list[0].args[0].timestamp) == [
            timestamp1,
            timestamp2,
            timestamp1,
            timestamp1,
            timestamp3,
            timestamp3,
            timestamp2,
            timestamp1,
        ]
        assert list(mocked_chart.call_args_list[0].args[0].asset) == [
            asset_id3,
            asset_id3,
            asset_id1,
            asset_id2,
            asset_id2,
            asset_id1,
            asset_id2,
            asset_id4,
        ]
        assert list(mocked_chart.call_args_list[0].args[0].value) == [
            value1,
            value2,
            value3,
            value4,
            value5,
            value6,
            value7,
            value8,
        ]
        assert mocked_chart.call_args_list[0].args[1] == asset_tags
        mocked_extend.assert_called_once_with(
            bar_chart, [timestamp1, timestamp2, timestamp3], timeline_data
        )
        mocked_interval.assert_called_once_with(timeline_data, timestamps)
        mocked_append.assert_called_once_with(
            bar_chart, interval_values["low"], interval_values["high"]
        )

    # # _create_candlestick_chart
    def test_widgets_inhouse_historic_charts_create_candlestick_chart_for_candles_count(
        self, mocker
    ):
        timeline_data = mocker.MagicMock()
        timestamp1, timestamp2, timestamp3, timestamp4, timestamp5 = (
            np.int64(1652500100),
            np.int64(1652800100),
            np.int64(1672500000),
            np.int64(1712500000),
            np.int64(1722500000),
        )
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp4,
                    timestamp2,
                    timestamp1,
                ],
                "foobar": [
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                ],
            }
        )
        central_timestamps = [timestamp1, timestamp3, timestamp5]
        mocked_central = mocker.patch(
            "widgets.inhouse.historic.charts._candlestick_chart_timestamps",
            return_value=central_timestamps,
        )
        timestamps = mocker.MagicMock()
        mocked_timestamps = mocker.patch(
            "widgets.inhouse.historic.charts._extend_candlestick_timestamps_on_both_sides",
            return_value=timestamps,
        )
        interval_values = mocker.MagicMock()
        mocked_interval = mocker.patch(
            "widgets.inhouse.historic.charts._timeline_value_boundaries_for_timestamps",
            return_value=interval_values,
        )
        mocked_data = mocker.patch(
            "widgets.inhouse.historic.charts._candles_from_interval_values_for_timestamps"
        )
        mocked_chart = mocker.patch(
            "widgets.inhouse.historic.charts._candlestick_chart_config"
        )
        candles_count = 10
        returned = _create_candlestick_chart(
            asset_values, timeline_data, candles_count=candles_count
        )
        assert returned == {
            "data": mocked_chart.return_value,
            "xmin": timestamp1 * 1000,
            "xmax": timestamp5 * 1000,
        }
        mocked_central.assert_called_once_with(timestamp1, timestamp4, candles_count)
        mocked_timestamps.assert_called_once_with(central_timestamps, timeline_data)
        mocked_interval.assert_called_once_with(timeline_data, timestamps)
        mocked_data.assert_called_once_with(interval_values, timestamps)
        mocked_chart.assert_called_once_with(data=mocked_data.return_value)

    def test_widgets_inhouse_historic_charts_create_candlestick_chart_functionality(
        self, mocker
    ):
        timeline_data = mocker.MagicMock()
        timestamp1, timestamp2, timestamp3, timestamp4, timestamp5 = (
            1652500100,
            1652800100,
            1672500000,
            1712500000,
            1722500000,
        )
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp4,
                    timestamp2,
                    timestamp1,
                ],
                "foobar": [
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                    mocker.MagicMock(),
                ],
            }
        )
        central_timestamps = [timestamp1, timestamp3, timestamp5]
        mocked_central = mocker.patch(
            "widgets.inhouse.historic.charts._candlestick_chart_timestamps",
            return_value=central_timestamps,
        )
        timestamps = mocker.MagicMock()
        mocked_timestamps = mocker.patch(
            "widgets.inhouse.historic.charts._extend_candlestick_timestamps_on_both_sides",
            return_value=timestamps,
        )
        interval_values = mocker.MagicMock()
        mocked_interval = mocker.patch(
            "widgets.inhouse.historic.charts._timeline_value_boundaries_for_timestamps",
            return_value=interval_values,
        )
        mocked_data = mocker.patch(
            "widgets.inhouse.historic.charts._candles_from_interval_values_for_timestamps"
        )
        mocked_chart = mocker.patch(
            "widgets.inhouse.historic.charts._candlestick_chart_config"
        )
        returned = _create_candlestick_chart(asset_values, timeline_data)
        assert returned == {
            "data": mocked_chart.return_value,
            "xmin": timestamp1 * 1000,
            "xmax": timestamp5 * 1000,
        }
        mocked_central.assert_called_once_with(
            timestamp1, timestamp4, TOTAL_NUMBER_OF_CANDLES_IN_CHART
        )
        mocked_timestamps.assert_called_once_with(central_timestamps, timeline_data)
        mocked_interval.assert_called_once_with(timeline_data, timestamps)
        mocked_data.assert_called_once_with(interval_values, timestamps)
        mocked_chart.assert_called_once_with(data=mocked_data.return_value)

    # # _tag_totals_by_timestamps
    def test_widgets_inhouse_historic_charts_tag_totals_by_timestamps_functionality(
        self,
    ):
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        timestamp1, timestamp2, timestamp3 = 1652500100, 1652800100, 1672500000
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5 = 505, 506, 507, 508, 509
        value1, value2, value3, value4, value5, value6, value7, value8 = (
            1500,
            2100,
            1800,
            4300,
            2000,
            1805,
            2120,
            4500,
        )
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp3,
                    timestamp2,
                    timestamp1,
                ],
                "asset": [
                    asset_id3,
                    asset_id2,
                    asset_id1,
                    asset_id3,
                    asset_id4,
                    asset_id1,
                    asset_id2,
                    asset_id4,
                ],
                "value": [
                    value1,
                    value2,
                    value3,
                    value4,
                    value5,
                    value6,
                    value7,
                    value8,
                ],
            }
        )
        top_assets = [asset_id3, GROUPS_IN_ASSET_TAGS[1], asset_id2]
        asset_tags = {
            asset_id1: unit1,
            asset_id2: GROUPS_IN_ASSET_TAGS[0],
            asset_id3: unit2,
            asset_id4: GROUPS_IN_ASSET_TAGS[1],
            asset_id5: unit3,
        }
        returned = _tag_totals_by_timestamps(asset_values, top_assets, asset_tags)
        assert returned == {
            timestamp1: {
                asset_id3: value1 + value4,
                GROUPS_IN_ASSET_TAGS[1]: value8,
                OTHERS_GROUP_NAME: value3,
            },
            timestamp2: {asset_id2: value2 + value7},
            timestamp3: {
                GROUPS_IN_ASSET_TAGS[1]: value5,
                OTHERS_GROUP_NAME: value6,
            },
        }

    # # _top_assets_and_groups
    def test_widgets_inhouse_historic_charts_top_assets_and_groups_for_a_few_assets(
        self,
    ):
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        timestamp1, timestamp2, timestamp3 = 1652500100, 1652800100, 1672500000
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5, asset_id6, asset_id7 = (
            505,
            506,
            507,
            508,
            509,
            510,
            511,
        )
        (
            value1,
            value2,
            value3,
            value4,
            value5,
            value6,
            value7,
            value8,
            value9,
            value10,
        ) = (1500, 2100, 1800, 4300, 2000, 1805, 2120, 4500, 1200, 1000)
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp3,
                    timestamp2,
                    timestamp1,
                    timestamp2,
                    timestamp1,
                ],
                "asset": [
                    asset_id3,
                    asset_id7,
                    asset_id1,
                    asset_id3,
                    asset_id4,
                    asset_id1,
                    asset_id2,
                    asset_id4,
                    asset_id5,
                    asset_id6,
                ],
                "value": [
                    value1,
                    value2,
                    value3,
                    value4,
                    value5,
                    value6,
                    value7,
                    value8,
                    value9,
                    value10,
                ],
            }
        )
        asset_tags = {
            asset_id1: unit1,
            asset_id2: GROUPS_IN_ASSET_TAGS[0],
            asset_id3: unit2,
            asset_id4: GROUPS_IN_ASSET_TAGS[1],
            asset_id5: GROUPS_IN_ASSET_TAGS[1],
            asset_id6: unit3,
            asset_id7: GROUPS_IN_ASSET_TAGS[1],
        }
        returned = _top_assets_and_groups(asset_values, asset_tags)
        assert returned == [
            GROUPS_IN_ASSET_TAGS[1],  # 2000+4500+1200+2100
            asset_id3,  # 1500+4300
            asset_id1,  # 1800+1805
            GROUPS_IN_ASSET_TAGS[0],  # 2120
            asset_id6,  # 1000
            OTHERS_GROUP_NAME,
        ]

    def test_widgets_inhouse_historic_charts_top_assets_and_groups_functionality(
        self,
    ):
        unit1, unit2, unit3 = "unit1", "unit2", "unit3"
        timestamp1, timestamp2, timestamp3 = 1652500100, 1652800100, 1672500000
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5, asset_id6, asset_id7 = (
            505,
            506,
            507,
            508,
            509,
            510,
            511,
        )
        (
            value1,
            value2,
            value3,
            value4,
            value5,
            value6,
            value7,
            value8,
            value9,
            value10,
        ) = (1500, 2100, 1800, 4300, 2000, 1805, 2120, 4500, 1200, 1000)
        asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp1,
                    timestamp3,
                    timestamp3,
                    timestamp2,
                    timestamp1,
                    timestamp2,
                    timestamp1,
                ],
                "asset": [
                    asset_id3,
                    asset_id7,
                    asset_id1,
                    asset_id3,
                    asset_id4,
                    asset_id1,
                    asset_id2,
                    asset_id4,
                    asset_id5,
                    asset_id6,
                ],
                "value": [
                    value1,
                    value2,
                    value3,
                    value4,
                    value5,
                    value6,
                    value7,
                    value8,
                    value9,
                    value10,
                ],
            }
        )
        asset_tags = {
            asset_id1: unit1,
            asset_id2: GROUPS_IN_ASSET_TAGS[0],
            asset_id3: unit2,
            asset_id4: GROUPS_IN_ASSET_TAGS[1],
            asset_id5: GROUPS_IN_ASSET_TAGS[1],
            asset_id6: unit3,
            asset_id7: GROUPS_IN_ASSET_TAGS[1],
        }
        with mock.patch.object(
            widgets.inhouse.historic.charts, "MAX_NUMBER_OF_ASSETS_IN_CHART", 3
        ):
            returned = _top_assets_and_groups(asset_values, asset_tags)
            assert returned == [
                GROUPS_IN_ASSET_TAGS[1],
                asset_id3,
                asset_id1,
                OTHERS_GROUP_NAME,
            ]

    # # _timeline_value_boundaries_for_timestamps
    def test_widgets_inhouse_historic_charts_timeline_value_boundaries_missing_data(
        self,
    ):
        timeline_data = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    1659850000,
                    1659872000,
                    1659884000,
                    1659894000,
                    1659950000,
                    1662850020,
                    1663950020,
                    1710250020,
                    1715250020,
                ],
                "value": [
                    10000000,
                    12000000,
                    9000000,
                    18000000,
                    17000000,
                    15000000,
                    12000000,
                    8000000,
                    10000000,
                ],
            }
        )
        timestamps = [1659850000, 1659895000, 1675950090, 1705950050, 1715250010]
        returned = _timeline_value_boundaries_for_timestamps(timeline_data, timestamps)
        assert returned == {
            "open": [12.0, 17.0, 0, 8.0, 10.0],
            "open_t": [1659872000, 1659950000, 0, 1710250020, 1715250020],
            "high": [18.0, 17.0, 0, 8.0, 10.0],
            "high_t": [1659894000, 1659950000, 0, 1710250020, 1715250020],
            "low": [9.00, 12.00, 0, 8.00, 10.00],
            "low_t": [1659884000, 1663950020, 0, 1710250020, 1715250020],
            "close": [18.0, 12.0, 0, 8.0, 10.0],
            "close_t": [1659894000, 1663950020, 0, 1710250020, 1715250020],
        }

    def test_widgets_inhouse_historic_charts_timeline_value_boundaries_functionality(
        self,
    ):
        timeline_data = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    1659850000,
                    1659872000,
                    1659884000,
                    1659894000,
                    1659950000,
                    1662850020,
                    1663950020,
                    1672950020,
                    1675950020,
                    1695950020,
                    1701950020,
                    1702950020,
                    1705950020,
                    1709950020,
                    1710250020,
                    1715250020,
                ],
                "value": [
                    10000000,
                    12000000,
                    9000000,
                    18000000,
                    17000000,
                    15000000,
                    12000000,
                    14000000,
                    12500000,
                    20000000,
                    12000000,
                    14000000,
                    11000000,
                    10000000,
                    8000000,
                    10000000,
                ],
            }
        )
        timestamps = [1659850000, 1659895000, 1675950090, 1705950050, 1715250010]
        returned = _timeline_value_boundaries_for_timestamps(timeline_data, timestamps)
        assert returned == {
            "open": [12.00, 17.00, 20.0, 10.0, 10.00],
            "open_t": [1659872000, 1659950000, 1695950020, 1709950020, 1715250020],
            "high": [18.00, 17.00, 20.00, 10.00, 10.00],
            "high_t": [1659894000, 1659950000, 1695950020, 1709950020, 1715250020],
            "low": [9.00, 12.00, 11.00, 8.00, 10.00],
            "low_t": [1659884000, 1663950020, 1705950020, 1710250020, 1715250020],
            "close": [18.00, 12.5, 11.0, 8.0, 10.00],
            "close_t": [1659894000, 1675950020, 1705950020, 1710250020, 1715250020],
        }

    # # charts_data_from_asset_values_and_timeline_data
    def test_widgets_inhouse_historic_charts_data_from_asset_values_and_timeline_data(
        self, mocker
    ):
        asset_values, timeline_data, asset_tags = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        bar_chart, extended_timestamps = mocker.MagicMock(), mocker.MagicMock()
        mocked_bar = mocker.patch(
            "widgets.inhouse.historic.charts._create_bar_chart",
            return_value=(bar_chart, extended_timestamps),
        )
        mocked_candlestick = mocker.patch(
            "widgets.inhouse.historic.charts._create_candlestick_chart"
        )
        returned = charts_data_from_asset_values_and_timeline_data(
            asset_values, timeline_data, asset_tags
        )
        assert returned == (
            {
                "bars": bar_chart,
                "candles": mocked_candlestick.return_value,
            },
            extended_timestamps,
        )
        mocked_bar.assert_called_once_with(asset_values, timeline_data, asset_tags)
        mocked_candlestick.assert_called_once_with(asset_values, timeline_data)

    # # consolidated_view_charts_from_assets_data
    def test_widgets_inhouse_historic_consolidated_view_charts_from_assets_data(
        self, mocker
    ):
        assets_data = mocker.MagicMock()
        asachart, nftchart, colors, nft_colors = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_base = mocker.patch(
            "widgets.inhouse.historic.charts.prepare_base_charts_from_assets_data",
            return_value=(asachart, nftchart, colors, nft_colors),
        )
        distchart, ratiochart, consolidated = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_consolidated = mocker.patch(
            "widgets.inhouse.historic.charts.prepare_consolidated_charts_from_assets_data",
            return_value=(distchart, ratiochart, consolidated),
        )
        returned = consolidated_view_charts_from_assets_data(assets_data)
        assert returned == {
            "asachart": asachart,
            "nftchart": nftchart,
            "colors": colors,
            "nft_colors": nft_colors,
            "distchart": distchart,
            "ratiochart": ratiochart,
            "consolidated": consolidated,
        }
        mocked_base.assert_called_once_with(assets_data)
        mocked_consolidated.assert_called_once_with(assets_data)
