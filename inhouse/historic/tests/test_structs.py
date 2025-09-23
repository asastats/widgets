"""Testing module for historic widget's structs module."""

import inspect
from unittest import mock

import pandas as pd
import pytest

import inhouse.historic.structs
from inhouse.historic.constants import BARS_COUNT
from inhouse.historic.structs import UpdateStatus, ViewStatus


class TestWidgetsHistoricStructsNamedTuples:
    """Testing class for :py:mod:`inhouse.historic.structs` namedtuples."""

    # # HeaderElement
    def test_widgets_inhouse_historic_structs_defines_headerelement_named_tuple(self):
        assert inspect.isclass(inhouse.historic.structs.HeaderElement)
        assert inhouse.historic.structs.HeaderElement.__name__ == "HeaderElement"

    def test_widgets_inhouse_historic_structs_headerelement_fields(self):
        assert inhouse.historic.structs.HeaderElement._fields == (
            "icon",
            "label",
            "amount",
            "total",
        )

    # # BodyElement
    def test_widgets_inhouse_historic_structs_defines_bodyelement_named_tuple(self):
        assert inspect.isclass(inhouse.historic.structs.BodyElement)
        assert inhouse.historic.structs.BodyElement.__name__ == "BodyElement"

    def test_widgets_inhouse_historic_structs_bodyelement_fields(self):
        assert inhouse.historic.structs.BodyElement._fields == (
            "asset",
            "name",
            "type",
            "url",
            "source",
            "amount",
            "value",
        )

    # # Total
    def test_widgets_inhouse_historic_structs_defines_total_named_tuple(self):
        assert inspect.isclass(inhouse.historic.structs.Total)
        assert inhouse.historic.structs.Total.__name__ == "Total"

    def test_widgets_inhouse_historic_structs_total_fields(self):
        assert inhouse.historic.structs.Total._fields == (
            "algo",
            "asa",
            "nft",
            "total",
            "totalusdc",
            "priceusdc",
            "pricealgo",
        )


class TestWidgetsHistoricStructsUpdateStatus:
    """Testing class for :class:`inhouse.historic.structs.UpdateStatus`."""

    # # UpdateStatus
    @pytest.mark.parametrize("attr", ["bundle", "addresses", "timestamp"])
    def test_widgets_inhouse_historic_structs_updatestatus_inits_attribute_as_none(
        self, attr
    ):
        assert getattr(UpdateStatus, attr) is None

    @pytest.mark.parametrize("attr", ["initials", "states"])
    def test_widgets_inhouse_historic_structs_updstatus_inits_attribute_as_empty_dict(
        self, attr
    ):
        assert getattr(UpdateStatus, attr) == {}

    # # __init__
    def test_widgets_inhouse_historic_structs_updatestatus_init_initializes_variables(
        self, mocker
    ):
        mocker.patch("inhouse.historic.structs.UpdateStatus.reset_states")
        message = {"bundle": "bundle", "addresses": "address1 address2"}
        timestamp = 1750000000
        with mock.patch("inhouse.historic.structs.datetime") as mocked_datetime:
            mocked_datetime.now.return_value.timestamp.return_value = timestamp
            status = UpdateStatus(message)
        assert status.bundle == "bundle"
        assert status.addresses == ["address1", "address2"]
        assert status.timestamp == timestamp

    def test_widgets_inhouse_historic_structs_updatestatus_init_calls_reset_status(
        self, mocker
    ):
        mocked_reset = mocker.patch(
            "inhouse.historic.structs.UpdateStatus.reset_states"
        )
        message = {"bundle": "bundle", "addresses": "address1 address2"}
        UpdateStatus(message)
        mocked_reset.assert_called_once_with()

    # # reset_states
    def test_widgets_inhouse_historic_structs_updatestatus_reset_states_functionality(
        self,
    ):
        message = {"bundle": "bundle", "addresses": "address1 address2"}
        status = UpdateStatus(message)
        status.initials = None
        status.states = None
        status.reset_states()
        assert status.initials == {"address1": 0, "address2": 0, "bundle": 0}
        assert status.states == {
            "address1": [None, 0, 0, 0],
            "address2": [None, 0, 0, 0],
            "bundle": [None, 0, 0, 0],
        }

    # # _calculate_phase_value
    def test_widgets_inhouse_historic_structs_updatestatus_calculate_phase_value_0(
        self,
    ):
        message = {"bundle": "bundle", "addresses": "addresses"}
        status = UpdateStatus(message)
        state = 1675400000
        initial = 0
        end_state = 0
        returned = status._calculate_phase_value(state, initial, end_state)
        assert returned == 0

    def test_widgets_inhouse_historic_structs_updatestatus_calculate_phase_value_funct(
        self,
    ):
        message = {"bundle": "bundle", "addresses": "addresses"}
        status = UpdateStatus(message)
        state = 1675400000
        initial = 1670000000
        end_state = 1680000000
        returned = status._calculate_phase_value(state, initial, end_state)
        assert returned == 54

    # # _is_finished_phase
    @pytest.mark.parametrize("phase", [0, 1, 2, 3])
    def test_widgets_inhouse_historic_structs_updstatus_is_finished_phase_returns_false(
        self, phase
    ):
        message = {"bundle": "bundle", "addresses": "addresses"}
        status = UpdateStatus(message)
        assert status._is_finished_phase(phase) is False

    # # _statuses_from_events
    def test_widgets_inhouse_historic_structs_updstatus_statuses_from_events_funct(
        self,
    ):
        events = {
            "bundle": "540A5D8CEC896E073F9170AF0A962503E69147CF",
            "addresses": (
                "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU "
                "VW55KZ3NF4GDOWI7IPWLGZDFWNXWKSRD5PETRLDABZVU5XPKRJJRK3CBSU"
            ),
            "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU": {
                0: {"state": 1638069738, "end": None},
                1: {"state": 1751105247, "end": None},
                2: {"state": 1751105247, "end": None},
                3: {"state": 1751105247, "end": None},
                4: {"state": 0, "end": None},
                5: {"state": 0, "end": None},
                6: {"state": 0, "end": None},
            },
            "VW55KZ3NF4GDOWI7IPWLGZDFWNXWKSRD5PETRLDABZVU5XPKRJJRK3CBSU": {
                0: {"state": 1648401677, "end": None},
                1: {"state": 1758593593, "end": None},
                2: {"state": 1751493593, "end": None},
                3: {"state": 1751493593, "end": None},
            },
            "540A5D8CEC896E073F9170AF0A962503E69147CF": {
                1: {"state": 17496, "end": 17500},
                4: {"state": 0, "end": 17500},
                2: {"state": 171, "end": 171},
                5: {"state": 0, "end": 171},
                3: {"state": 5500, "end": 8409},
            },
        }
        message = {
            "bundle": "540A5D8CEC896E073F9170AF0A962503E69147CF",
            "addresses": (
                "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU "
                "VW55KZ3NF4GDOWI7IPWLGZDFWNXWKSRD5PETRLDABZVU5XPKRJJRK3CBSU"
            ),
        }
        timestamp = 1760000000
        with mock.patch("inhouse.historic.structs.datetime") as mocked_datetime:
            mocked_datetime.now.return_value.timestamp.return_value = timestamp
            status = UpdateStatus(message)
        collection = [
            "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU",
            "VW55KZ3NF4GDOWI7IPWLGZDFWNXWKSRD5PETRLDABZVU5XPKRJJRK3CBSU",
            "540A5D8CEC896E073F9170AF0A962503E69147CF",
        ]
        returned = status._statuses_from_events(collection, events)
        assert returned == [[100, 100, 100], [98, 92, 92], [100, 100, 65]]

    # # check_phase_init
    def test_widgets_inhouse_historic_structs_updatestatus_check_phase_init_for_init(
        self,
    ):
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(
            {
                "bundle": "bundle1",
                "addresses": "address1 address2 address3",
            }
        )
        state = 50
        message = {"phase": 0, "state": state, "address": "address2"}
        assert status.initials["address2"] == 0
        returned = status.check_phase_init(message)
        assert returned is True
        assert status.initials["address2"] == state

    def test_widgets_inhouse_historic_structs_updatestatus_check_phase_init_for_no_init(
        self,
    ):
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(
            {"bundle": "bundle1", "addresses": "address1 address2 address3"}
        )
        message = {"phase": 3, "state": 25, "address": "address2"}
        returned = status.check_phase_init(message)
        assert returned is False
        assert status.initials["address2"] == 0

    # # evaluate
    def test_widgets_inhouse_historic_structs_updatestatus_evaluate_no_address(
        self, mocker
    ):
        mocked_is_finished = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._is_finished_phase"
        )
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(
            {"bundle": "bundle1", "addresses": "address1 address2 address3"}
        )
        message = {"phase": 4, "state": 25, "address": "address4"}
        returned = status.evaluate(message)
        assert returned == (None, None)
        mocked_is_finished.assert_not_called()

    def test_widgets_inhouse_historic_structs_updatestatus_evaluate_for_init(
        self, mocker
    ):
        mocked_calculate = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._calculate_phase_value"
        )
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(
            {"bundle": "bundle1", "addresses": "address1 address2 address3"}
        )
        message = {"phase": 4, "state": 25, "address": "address2"}
        returned = status.evaluate(message)
        assert returned == (1, 100)
        assert status.states["address2"][1] == 100
        mocked_calculate.assert_not_called()

    def test_widgets_inhouse_historic_structs_updstatus_evaluate_for_increased_no_end(
        self, mocker
    ):
        calculated_value = 75
        mocked_calculate = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._calculate_phase_value",
            return_value=calculated_value,
        )
        timestamp = 85
        with mock.patch("inhouse.historic.structs.datetime") as mocked_datetime:
            mocked_datetime.now.return_value.timestamp.return_value = timestamp
            status = UpdateStatus(
                {"bundle": "bundle1", "addresses": "address1 address2 address3"}
            )
        state = 80
        message = {"phase": 2, "state": state, "address": "address3"}
        returned = status.evaluate(message)
        assert returned == (2, 75)
        assert status.states["address3"][2] == 75
        mocked_calculate.assert_called_once_with(state, 0, timestamp)

    def test_widgets_inhouse_historic_structs_updstatus_evaluate_for_increased_with_end(
        self, mocker
    ):
        calculated_value = 75
        mocked_calculate = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._calculate_phase_value",
            return_value=calculated_value,
        )
        timestamp = 85
        with mock.patch("inhouse.historic.structs.datetime") as mocked_datetime:
            mocked_datetime.now.return_value.timestamp.return_value = timestamp
            status = UpdateStatus(
                {"bundle": "bundle1", "addresses": "address1 address2 address3"}
            )
        state = 80
        end = 95
        message = {"phase": 2, "state": state, "address": "address3", "end": end}
        returned = status.evaluate(message)
        assert returned == (2, 75)
        assert status.states["address3"][2] == 75
        mocked_calculate.assert_called_once_with(state, 0, end)

    # # template_context
    def test_widgets_inhouse_historic_structs_updstatus_template_context_for_events(
        self, mocker
    ):
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(message)
        mocked_statuses = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._statuses_from_events"
        )
        events = mocker.MagicMock()
        returned = status.template_context(events=events)
        assert returned == {
            "bundle": "bundle",
            "addresses": ["address1", "address2", "address3", "bundle"],
            "labels": ["Fetch", "Analysis", "Process"],
            "statuses": mocked_statuses.return_value,
        }
        mocked_statuses.assert_called_once_with(
            ["address1", "address2", "address3", "bundle"], events
        )

    def test_widgets_inhouse_historic_structs_updstatus_template_context_functionality(
        self, mocker
    ):
        message = {"bundle": "bundle", "addresses": "address1 address2 address3"}
        status = UpdateStatus(message)
        mocked_statuses = mocker.patch(
            "inhouse.historic.structs.UpdateStatus._statuses_from_events"
        )
        returned = status.template_context()
        assert returned == {
            "bundle": "bundle",
            "addresses": ["address1", "address2", "address3", "bundle"],
            "labels": ["Fetch", "Analysis", "Process"],
            "statuses": [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
        }
        mocked_statuses.assert_not_called()


class TestWidgetsHistoricStructsViewStatus:
    """Testing class for :class:`inhouse.historic.structs.ViewStatus`."""

    # # ViewStatus
    @pytest.mark.parametrize(
        "attr", ["bundle", "carrier", "asset_values", "current_range"]
    )
    def test_widgets_inhouse_historic_structs_viewstatus_inits_attribute_as_none(
        self, attr
    ):
        assert getattr(ViewStatus, attr) is None

    @pytest.mark.parametrize("attr", ["timestamps"])
    def test_widgets_inhouse_historic_structs_viewstatus_inits_attribute_as_empty_list(
        self, attr
    ):
        assert getattr(ViewStatus, attr) == []

    # # __init__
    def test_widgets_inhouse_historic_structs_viewstatus_init_initializes_variables(
        self, mocker
    ):
        bundle, carrier = mocker.MagicMock(), mocker.MagicMock()
        status = ViewStatus(bundle, carrier)
        assert status.bundle == bundle
        assert status.carrier == carrier
        assert isinstance(status.asset_values, pd.DataFrame)
        assert list(status.asset_values.columns) == ["timestamp", "asset", "value"]
        assert status.asset_values.shape[0] == 0

    # # _is_zoom_out
    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_for_candles_true(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = (1672500000000, 1692500000000)
        x_min, x_max = 1671500000000, 1702500000000
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is True

    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_for_candles_false(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = (1672500000000, 1692500000000)
        x_min, x_max = 1673500000000, 1691500000000
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is False

    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_candles_true_range(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = [
            1671500000,
            1673500000,
            1675500000,
            1677500000,
            1679500000,
            1680500000,
        ]
        status.current_range = (1, 4)
        x_min, x_max = 1671500000000, 1702500000000
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is True

    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_candles_false_rng(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = [
            1671500000,
            1673500000,
            1675500000,
            1677500000,
            1679500000,
            1680500000,
        ]
        status.current_range = (1, 4)
        x_min, x_max = 1673500000000, 1678500000000
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is False

    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_for_bars_true(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = (0, 16)
        x_min, x_max = 7, 45
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is True

    def test_widgets_inhouse_historic_structs_viewstatus_is_zoom_out_for_bars_false(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = (0, 16)
        x_min, x_max = 7, 8
        returned = status._is_zoom_out(x_min, x_max)
        assert returned is False

    # # _zoom_out_period_for_range
    def test_widgets_inhouse_historic_structs_viewstatus_zoom_out_period_for_range_b_l(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = (
            [1670000000] * 12
            + [1680000000]
            + [1685000000] * 27
            + [1690000000]
            + [1700000000] * 20
        )
        x_min, x_max = 12, 40
        returned = status._zoom_out_period_for_range(x_min, x_max)
        assert returned == (1610000000, 1770000000)

    def test_widgets_inhouse_historic_structs_viewstatus_zoom_out_period_for_range_b_r(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = (
            [1650000000] * 12
            + [1680000000]
            + [1685000000] * 27
            + [1690000000]
            + [1700000000] * 10
        )
        x_min, x_max = 12, 40
        returned = status._zoom_out_period_for_range(x_min, x_max)
        assert returned == (1610000000, 1770000000)

    def test_widgets_inhouse_historic_structs_viewstatus_zoom_out_period_for_range_c_l(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = (
            [1670000000] * 12
            + [1680000000]
            + [1685000000] * 27
            + [1690000000]
            + [1700000000] * 20
        )
        x_min, x_max = 1678000000000, 1691000000000
        returned = status._zoom_out_period_for_range(x_min, x_max)
        assert returned == (1574000000, 1782000000)

    def test_widgets_inhouse_historic_structs_viewstatus_zoom_out_period_for_range_c_r(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = (
            [1670000000] * 12
            + [1680000000]
            + [1685000000] * 27
            + [1690000000]
            + [1700000000] * 20
        )
        x_min, x_max = 1679500000000, 1695000000000
        returned = status._zoom_out_period_for_range(x_min, x_max)
        assert returned == (1571000000, 1819000000)

    # # asset_values_for_timestamps
    def test_widgets_inhouse_historic_structs_viewstatus_asset_values_for_timestamps_f(
        self, mocker
    ):
        timestamp1, timestamp2, timestamp3, timestamp4 = (
            1652500100,
            1652800100,
            1672500000,
            1692500000,
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
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp1,
                    timestamp2,
                    timestamp1,
                    timestamp4,
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
        timestamps = [timestamp2, timestamp3, timestamp4]
        returned = status.asset_values_for_timestamps(timestamps)
        assert returned.values.tolist() == [
            [timestamp2, asset_id2, value2],
            [timestamp4, asset_id3, value4],
            [timestamp3, asset_id4, value5],
            [timestamp3, asset_id1, value6],
            [timestamp2, asset_id2, value7],
        ]

    # # evaluated_timestamps
    def test_widgets_inhouse_historic_structs_viewstatus_evaluated_timestamps_funct(
        self, mocker
    ):
        timestamp1, timestamp2, timestamp3 = (
            1652500100,
            1652800100,
            1672500000,
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
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.asset_values = pd.DataFrame.from_dict(
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
        assert status.evaluated_timestamps == {timestamp1, timestamp2, timestamp3}

    # # is_range_changed
    def test_widgets_inhouse_historic_structs_viewstatus_is_range_changed_no_current(
        self, mocker
    ):
        x_min, x_max = mocker.MagicMock(), mocker.MagicMock()
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        returned = status.is_range_changed(x_min, x_max)
        assert returned is True

    def test_widgets_inhouse_historic_structs_viewstatus_is_range_changed_same_current(
        self, mocker
    ):
        x_min, x_max = mocker.MagicMock(), mocker.MagicMock()
        current_range = (x_min, x_max)
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = current_range
        returned = status.is_range_changed(x_min, x_max)
        assert returned is False

    def test_widgets_inhouse_historic_structs_viewstatus_is_range_changed_different(
        self, mocker
    ):
        x_min, x_max = mocker.MagicMock(), mocker.MagicMock()
        period = (1715250020, 1725480050)
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.current_range = period
        returned = status.is_range_changed(x_min, x_max)
        assert returned is True

    # # period_for_range
    def test_widgets_inhouse_historic_structs_viewstatus_period_for_range_zoom(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        mocked_is_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._is_zoom_out",
            return_value=True,
        )
        mocked_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._zoom_out_period_for_range"
        )
        x_min, x_max = 10, 30
        returned = status.period_for_range(x_min, x_max)
        assert returned == mocked_zoom.return_value
        assert status.current_range == (x_min, x_max)
        mocked_is_zoom.assert_called_once_with(x_min, x_max)
        mocked_zoom.assert_called_once_with(x_min, x_max)

    def test_widgets_inhouse_historic_structs_viewstatus_period_for_range_bars(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        mocked_is_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._is_zoom_out",
            return_value=False,
        )
        mocked_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._zoom_out_period_for_range"
        )
        x_min, x_max = 1, 4
        status.timestamps = [0, 10, 20, 30, 40, 50, 60, 70, 80]
        returned = status.period_for_range(x_min, x_max)
        assert returned == (10, 40)
        assert status.current_range == (x_min, x_max)
        mocked_is_zoom.assert_called_once_with(x_min, x_max)
        mocked_zoom.assert_not_called()

    def test_widgets_inhouse_historic_structs_viewstatus_period_for_range_candles(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        mocked_is_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._is_zoom_out",
            return_value=False,
        )
        mocked_zoom = mocker.patch(
            "inhouse.historic.structs.ViewStatus._zoom_out_period_for_range"
        )
        x_min, x_max = 1715250021234.567890, 1725480051234.567890
        returned = status.period_for_range(x_min, x_max)
        assert returned == (1715250021, 1725480051)
        assert status.current_range == (x_min, x_max)
        mocked_is_zoom.assert_called_once_with(x_min, x_max)
        mocked_zoom.assert_not_called()

    # # record_asset_values
    def test_widgets_inhouse_historic_structs_viewstatus_record_asset_values_funct(
        self, mocker
    ):
        timestamp1, timestamp2, timestamp3, timestamp4 = (
            1652500100,
            1652800100,
            1672500000,
            1692500000,
        )
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5 = (
            505,
            506,
            507,
            508,
            509,
        )
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
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.asset_values = pd.DataFrame.from_dict(
            {
                "timestamp": [
                    timestamp3,
                    timestamp3,
                    timestamp4,
                    timestamp4,
                ],
                "asset": [
                    asset_id5,
                    asset_id1,
                    asset_id4,
                    asset_id4,
                ],
                "value": [100, 200, 300, 400],
            }
        )
        status.record_asset_values(asset_values)
        assert status.asset_values.values.tolist() == [
            [timestamp1, asset_id1, 1800],
            [timestamp1, asset_id3, 4300],
            [timestamp1, asset_id3, 1500],
            [timestamp1, asset_id4, 4500],
            [timestamp2, asset_id2, 2120],
            [timestamp2, asset_id2, 2100],
            [timestamp3, asset_id1, 200],
            [timestamp3, asset_id5, 100],
            [timestamp4, asset_id4, 300],
            [timestamp4, asset_id4, 400],
        ]

    # # record_timestamps
    def test_widgets_inhouse_historic_structs_viewstatus_record_timestamps_funct(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        timestamps = mocker.MagicMock()
        status.record_timestamps(timestamps)
        assert status.timestamps == timestamps

    # # reset_current_range
    def test_widgets_inhouse_historic_structs_viewstatus_reset_current_range_funct(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.reset_current_range()
        assert status.current_range == (0, BARS_COUNT - 1)

    # # timestamp_for_x
    def test_widgets_inhouse_historic_structs_viewstatus_timestamp_for_x_candles(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        x_val = "1715250021.267890"
        returned = status.timestamp_for_x(x_val)
        assert returned == 1715250021

    def test_widgets_inhouse_historic_structs_viewstatus_timestamp_for_x_bars(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        status.timestamps = [1715250000, 1725250000, 1735250000, 1745250000]
        x_val = "1"
        returned = status.timestamp_for_x(x_val)
        assert returned == 1725250000

    # # x_axis_boundaries
    def test_widgets_inhouse_historic_structs_viewstatus_x_axis_boundaries_candles(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        x_min, x_max = "1715250021234.567890", "1725480051234.567890"
        returned = status.x_axis_boundaries(x_min, x_max)
        assert returned == (1715250021234, 1725480051234)

    def test_widgets_inhouse_historic_structs_viewstatus_x_axis_boundaries_bars_diff(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        x_min, x_max = "1", "4"
        returned = status.x_axis_boundaries(x_min, x_max)
        assert returned == (1, 4)

    def test_widgets_inhouse_historic_structs_viewstatus_x_axis_boundaries_bars_equal_0(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        x_min, x_max = "0", "0"
        returned = status.x_axis_boundaries(x_min, x_max)
        assert returned == (0, 1)

    def test_widgets_inhouse_historic_structs_viewstatus_x_axis_boundaries_bars_equal(
        self, mocker
    ):
        status = ViewStatus(mocker.MagicMock(), mocker.MagicMock())
        x_min, x_max = "8", "8"
        returned = status.x_axis_boundaries(x_min, x_max)
        assert returned == (7, 8)
