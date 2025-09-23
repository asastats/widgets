"""Testing module for historic widget consumers module."""

import json

import pandas as pd
import pytest
from django.contrib.auth import get_user_model

from inhouse.historic.consumers import (
    HistoricConsumer,
    evaluate_bundle_ledger_data_for_period,
    evaluate_bundle_ledger_data_for_timestamp,
)
from .fixtures import TEST_BUNDLE

user_model = get_user_model()

CONSUMER_PATH = "inhouse.historic.consumers.HistoricConsumer"


@pytest.mark.django_db
class HistoricConsumerBaseTest:
    """Base helper class for :class:`HistoricConsumer` testing."""

    # helper methods
    async def _connect_helper(self, mocker, connect=True):
        self.consumer.channel_layer = mocker.AsyncMock()
        self.group_name = "group_name"
        self.channel_name = "channel_name"
        self.consumer.channel_name = self.channel_name
        mocker.patch(
            "inhouse.historic.consumers.group_name_from_bundle",
            return_value=self.group_name,
        )
        mocker.patch(
            f"{CONSUMER_PATH}.historic_process_altogether",
            return_value=self.group_name,
        )
        mocker.patch(f"{CONSUMER_PATH}.accept")
        if connect:
            mocker.patch(f"{CONSUMER_PATH}._load_statuses")
            await self.consumer.connect()

    def _create_consumer(self, bundle):
        self.bundle = bundle
        consumer = HistoricConsumer()
        consumer.scope = {
            "url_route": {"kwargs": {"bundle": bundle}},
            "user": self.user,
        }
        return consumer

    def setup_method(self):
        self.user = user_model.objects.create_user(
            username="historic_widget_user",
            email="historic_widget_user@test.com",
            password="12345o",
        )
        self.consumer = self._create_consumer("ws/historic/{}/".format(TEST_BUNDLE))


class TestWidgetsHistoricConsumerSetup(HistoricConsumerBaseTest):
    """Testing class for :class:`HistoricConsumer` setup methods."""

    # # HistoricConsumer
    @pytest.mark.parametrize("attr", ["bundle_group_name", "update", "view"])
    def test_widgets_historic_historicconsumer_inits_attribute_as_none(self, attr):
        assert getattr(HistoricConsumer, attr) is None

    # # connect
    async def test_widgets_historic_historicconsumer_connect_functionality(
        self, mocker
    ):
        self.consumer.channel_layer = mocker.AsyncMock()
        channel_name, group_name = "channel_name", "group_name"
        self.consumer.channel_name = channel_name
        mocked_group_name = mocker.patch(
            "inhouse.historic.consumers.group_name_from_bundle",
            return_value=group_name,
        )
        mocked_accept = mocker.patch(f"{CONSUMER_PATH}.accept")
        mocked_load = mocker.patch(f"{CONSUMER_PATH}._load_statuses")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}.historic_process_altogether")
        await self.consumer.connect()
        assert self.consumer.bundle_group_name == group_name
        mocked_group_name.assert_called_once_with(self.bundle)
        self.consumer.channel_layer.group_add.assert_called_once_with(
            group_name, channel_name
        )
        mocked_accept.assert_called_once_with()
        mocked_load.assert_called_once_with(self.bundle)
        mocked_process.assert_called_once_with({"message": {"bundle": self.bundle}})

    # # disconnect
    async def test_widgets_historic_historicconsumer_disconnect_functionality(
        self, mocker
    ):
        await self._connect_helper(mocker)
        await self.consumer.disconnect(1001)
        self.consumer.channel_layer.group_discard.assert_called_once_with(
            self.group_name, self.channel_name
        )

    # # receive
    async def test_widgets_historic_historicconsumer_receive_for_no_headers(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        text_data = '{"foo":"bar"}'
        await self.consumer.receive(text_data)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_no_trigger(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        text_data = '{"HEADERS":{"foo":"bar"}}'
        await self.consumer.receive(text_data)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_wrong_trigger(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        text_data = '{"HEADERS":{"HX-Trigger":"foo"}}'
        await self.consumer.receive(text_data)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_update(self, mocker):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-process"}}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_update.assert_called_once_with(message)
        mocked_period.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_wrong_view_type(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-view"}, "type": "foo"}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_change_period(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-view"}, "type": "zoom"}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_period.assert_called_once_with(message)
        mocked_update.assert_not_called()
        mocked_process.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_reset_bars(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-reset-bars"}}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_process.assert_called_once_with(None)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_reset_candles(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-reset-candles"}}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_process.assert_called_once_with(None)
        mocked_update.assert_not_called()
        mocked_period.assert_not_called()
        mocked_timestamp.assert_not_called()

    async def test_widgets_historic_historicconsumer_receive_for_process_timestamp(
        self, mocker
    ):
        await self._connect_helper(mocker)
        mocked_update = mocker.patch(f"{CONSUMER_PATH}._initiate_update")
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        mocked_period = mocker.patch(f"{CONSUMER_PATH}._change_period")
        mocked_timestamp = mocker.patch(f"{CONSUMER_PATH}._process_for_timestamp")
        message = {"HEADERS": {"HX-Trigger": "id-show"}, "type": "show"}
        text_data = json.dumps(message)
        await self.consumer.receive(text_data)
        mocked_timestamp.assert_called_once_with(message)
        mocked_update.assert_not_called()
        mocked_process.assert_not_called()
        mocked_period.assert_not_called()


class TestWidgetsHistoricConsumerProcessing(HistoricConsumerBaseTest):
    """Testing class for :class:`HistoricConsumer` processing methods."""

    # # _change_period
    async def test_widgets_historic_historicconsumer_change_period_for_no_view(
        self, mocker
    ):
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        returned = await self.consumer._change_period(mocker.MagicMock())
        assert returned is True
        mocked_process.assert_not_called()

    async def test_widgets_historic_historicconsumer_change_period_for_no_change(
        self, mocker
    ):
        view = mocker.MagicMock()
        x_min, x_max = mocker.MagicMock(), mocker.MagicMock()
        view.x_axis_boundaries.return_value = (x_min, x_max)
        view.is_range_changed.return_value = False
        self.consumer.view = view
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        message_x_min, message_x_max = mocker.MagicMock(), mocker.MagicMock()
        message = {"x-min": message_x_min, "x-max": message_x_max}
        returned = await self.consumer._change_period(message)
        assert returned is True
        view.x_axis_boundaries.assert_called_once_with(message_x_min, message_x_max)
        view.is_range_changed.assert_called_once_with(x_min, x_max)
        mocked_process.assert_not_called()

    async def test_widgets_historic_historicconsumer_change_period_functionality(
        self, mocker
    ):
        await self._connect_helper(mocker)
        view = mocker.MagicMock()
        x_min, x_max = mocker.MagicMock(), mocker.MagicMock()
        view.x_axis_boundaries.return_value = (x_min, x_max)
        view.is_range_changed.return_value = True
        period = mocker.MagicMock()
        view.period_for_range.return_value = period
        self.consumer.view = view
        mocked_period = mocker.patch(
            "inhouse.historic.consumers.check_chart_period"
        )
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        message_x_min, message_x_max = mocker.MagicMock(), mocker.MagicMock()
        message = {"x-min": message_x_min, "x-max": message_x_max}
        await self.consumer._change_period(message)
        view.x_axis_boundaries.assert_called_once_with(message_x_min, message_x_max)
        view.is_range_changed.assert_called_once_with(x_min, x_max)
        view.period_for_range.assert_called_once_with(x_min, x_max)
        mocked_period.assert_called_once_with(period)
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.group_name,
            {"type": "historic.lock_interaction", "message": {"locked": True}},
        )
        mocked_process.assert_called_once_with(mocked_period.return_value)

    # # _initiate_update
    async def test_widgets_historic_historicconsumer_initiate_update_functionality(
        self, mocker
    ):
        await self._connect_helper(mocker)
        update = mocker.MagicMock()
        mocked_update = mocker.patch(
            "inhouse.historic.consumers.UpdateStatus", return_value=update
        )
        mocked_retrieve = mocker.patch(
            "inhouse.historic.consumers.retrieve_bundle_historic_data"
        )
        message = {"HEADERS": {"HX-Trigger": "id-process"}}
        text_data = json.dumps(message)
        await self.consumer._initiate_update(text_data)
        assert self.consumer.update == update
        mocked_update.assert_called_once_with(text_data)
        mocked_retrieve.assert_called_once_with(text_data)
        update.template_context.assert_called_once_with()
        calls = [
            mocker.call(
                self.group_name,
                {
                    "type": "historic.processing",
                    "message": update.template_context.return_value,
                },
            ),
            mocker.call(
                self.group_name,
                {
                    "type": "historic.lock_interaction",
                    "message": {"locked": True},
                },
            ),
        ]
        self.consumer.channel_layer.group_send.assert_has_calls(calls, any_order=True)
        assert self.consumer.channel_layer.group_send.call_count == 2

    # _load_statuses
    async def test_widgets_historic_historicconsumer_load_statuses_for_no_events(
        self, mocker
    ):
        await self._connect_helper(mocker, connect=False)
        mocked_load = mocker.patch(
            "inhouse.historic.consumers.load_bundle_event_records",
            return_value={},
        )
        mocked_update = mocker.patch("inhouse.historic.consumers.UpdateStatus")
        bundle = mocker.MagicMock()
        await self.consumer._load_statuses(bundle)
        mocked_load.assert_called_with(bundle)
        mocked_update.assert_not_called()

    async def test_widgets_historic_historicconsumer_load_statuses_functionality(
        self, mocker
    ):
        await self._connect_helper(mocker, connect=False)
        events = {"bundle": {-1: {"state": 1}}}
        mocked_load = mocker.patch(
            "inhouse.historic.consumers.load_bundle_event_records",
            return_value=events,
        )
        update = mocker.MagicMock()
        mocked_update = mocker.patch(
            "inhouse.historic.consumers.UpdateStatus", return_value=update
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        bundle = mocker.MagicMock()
        await self.consumer._load_statuses(bundle)
        assert self.consumer.update == update
        mocked_load.assert_called_with(bundle)
        mocked_update.assert_called_once_with(events)
        update.template_context.assert_called_once_with(events=events)
        calls = [
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.processing",
                    "message": update.template_context.return_value,
                },
            ),
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.lock_interaction",
                    "message": {"locked": True},
                },
            ),
        ]
        self.consumer.channel_layer.group_send.assert_has_calls(calls, any_order=True)
        assert self.consumer.channel_layer.group_send.call_count == 2

    async def test_widgets_historic_historicconsumer_load_statuses_for_finished(
        self, mocker
    ):
        await self._connect_helper(mocker, connect=False)
        bundle = mocker.MagicMock()
        events = {bundle: {-1: {"state": "finished"}}}
        mocked_load = mocker.patch(
            "inhouse.historic.consumers.load_bundle_event_records",
            return_value=events,
        )
        update = mocker.MagicMock()
        mocked_update = mocker.patch(
            "inhouse.historic.consumers.UpdateStatus", return_value=update
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        await self.consumer._load_statuses(bundle)
        assert self.consumer.update == update
        mocked_load.assert_called_with(bundle)
        mocked_update.assert_called_once_with(events)
        update.template_context.assert_called_once_with(events=events)
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.consumer.bundle_group_name,
            {
                "type": "historic.processing",
                "message": update.template_context.return_value,
            },
        )
        mocked_send.assert_not_called()

    # # _process_for_period
    async def test_widgets_historic_historicconsumer_process_for_period_no_data(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle, evaluated_timestamps = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.evaluated_timestamps = evaluated_timestamps
        self.consumer.view = view
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        sync_to_async.return_value = (None, None, None, None)
        mocked_charts = mocker.patch(
            (
                "inhouse.historic.consumers"
                ".charts_data_from_asset_values_and_timeline_data"
            )
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        period = mocker.MagicMock()
        await self.consumer._process_for_period(period)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_period, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(
            bundle, evaluated_timestamps, carrier, period=period
        )
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.consumer.bundle_group_name,
            {
                "type": "historic.lock_no_blur",
                "message": {"locked": False},
            },
        )
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "show_update"})
        )
        mocked_charts.assert_not_called()

    async def test_widgets_historic_historicconsumer_process_for_period_empty_computed(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle, evaluated_timestamps, asset_values_for_timestamps = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.evaluated_timestamps = evaluated_timestamps
        view.asset_values_for_timestamps.return_value = asset_values_for_timestamps
        self.consumer.view = view
        timestamps, timeline_data, asset_tags = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        computed_data = pd.DataFrame()
        sync_to_async.return_value = (
            timestamps,
            computed_data,
            timeline_data,
            asset_tags,
        )
        mocked_values = mocker.patch(
            "inhouse.historic.consumers.asset_values_from_computed_data"
        )
        charts_data = {"some": "charts data"}
        extended_timestamps = mocker.MagicMock()
        mocked_charts = mocker.patch(
            (
                "inhouse.historic.consumers"
                ".charts_data_from_asset_values_and_timeline_data"
            ),
            return_value=(charts_data, extended_timestamps),
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        period = mocker.MagicMock()
        await self.consumer._process_for_period(period)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_period, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(
            bundle, evaluated_timestamps, carrier, period=period
        )
        view.asset_values_for_timestamps.assert_called_once_with(timestamps)
        mocked_charts.assert_called_once_with(
            asset_values_for_timestamps, timeline_data, asset_tags
        )
        view.record_timestamps.assert_called_once_with(extended_timestamps)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "update_charts", "data": charts_data})
        )
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.consumer.bundle_group_name,
            {
                "type": "historic.lock_interaction",
                "message": {"locked": False},
            },
        )
        mocked_values.assert_not_called()
        view.record_asset_values.assert_not_called()

    async def test_widgets_historic_historicconsumer_process_for_period_none_period(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle, evaluated_timestamps, asset_values_for_timestamps = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.evaluated_timestamps = evaluated_timestamps
        view.asset_values_for_timestamps.return_value = asset_values_for_timestamps
        self.consumer.view = view
        timestamps, computed_data, timeline_data, asset_tags = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        computed_data.empty = False
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        sync_to_async.return_value = (
            timestamps,
            computed_data,
            timeline_data,
            asset_tags,
        )
        asset_values = mocker.MagicMock()
        mocked_values = mocker.patch(
            "inhouse.historic.consumers.asset_values_from_computed_data",
            return_value=asset_values,
        )
        charts_data = {"some": "charts data"}
        extended_timestamps = mocker.MagicMock()
        mocked_charts = mocker.patch(
            (
                "inhouse.historic.consumers"
                ".charts_data_from_asset_values_and_timeline_data"
            ),
            return_value=(charts_data, extended_timestamps),
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        period = None
        await self.consumer._process_for_period(period)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_period, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(
            bundle, evaluated_timestamps, carrier, period=period
        )
        mocked_values.assert_called_once_with(computed_data)
        view.record_asset_values.assert_called_once_with(asset_values)
        view.asset_values_for_timestamps.assert_called_once_with(timestamps)
        mocked_charts.assert_called_once_with(
            asset_values_for_timestamps, timeline_data, asset_tags
        )
        view.record_timestamps.assert_called_once_with(extended_timestamps)
        view.reset_current_range.assert_called_once_with()
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "update_charts", "data": charts_data})
        )
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.consumer.bundle_group_name,
            {
                "type": "historic.lock_interaction",
                "message": {"locked": False},
            },
        )

    async def test_widgets_historic_historicconsumer_process_for_period_functionality(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle, evaluated_timestamps, asset_values_for_timestamps = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.evaluated_timestamps = evaluated_timestamps
        view.asset_values_for_timestamps.return_value = asset_values_for_timestamps
        self.consumer.view = view
        timestamps, computed_data, timeline_data, asset_tags = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        computed_data.empty = False
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        sync_to_async.return_value = (
            timestamps,
            computed_data,
            timeline_data,
            asset_tags,
        )
        asset_values = mocker.MagicMock()
        mocked_values = mocker.patch(
            "inhouse.historic.consumers.asset_values_from_computed_data",
            return_value=asset_values,
        )
        charts_data = {"some": "charts data"}
        extended_timestamps = mocker.MagicMock()
        mocked_charts = mocker.patch(
            (
                "inhouse.historic.consumers"
                ".charts_data_from_asset_values_and_timeline_data"
            ),
            return_value=(charts_data, extended_timestamps),
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        period = mocker.MagicMock()
        await self.consumer._process_for_period(period)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_period, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(
            bundle, evaluated_timestamps, carrier, period=period
        )
        mocked_values.assert_called_once_with(computed_data)
        view.record_asset_values.assert_called_once_with(asset_values)
        view.asset_values_for_timestamps.assert_called_once_with(timestamps)
        view.reset_current_range.assert_not_called()
        mocked_charts.assert_called_once_with(
            asset_values_for_timestamps, timeline_data, asset_tags
        )
        view.record_timestamps.assert_called_once_with(extended_timestamps)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "update_charts", "data": charts_data})
        )
        self.consumer.channel_layer.group_send.assert_called_once_with(
            self.consumer.bundle_group_name,
            {
                "type": "historic.lock_interaction",
                "message": {"locked": False},
            },
        )

    # # _process_for_timestamp
    async def test_widgets_historic_historicconsumer_process_for_timestamp_no_data(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle, timestamp = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.timestamp_for_x.return_value = timestamp
        self.consumer.view = view
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        sync_to_async.return_value = None
        mocked_data = mocker.patch(
            "inhouse.historic.consumers.assets_data_from_timestamp_data"
        )
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template"
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        x_val, label = mocker.MagicMock(), mocker.MagicMock()
        message = {"x-val": x_val, "label": label}
        await self.consumer._process_for_timestamp(message)
        view.timestamp_for_x.assert_called_once_with(x_val)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_timestamp, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(bundle, timestamp, carrier)
        calls = [
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.lock_no_blur",
                    "message": {"locked": True},
                },
            ),
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.lock_no_blur",
                    "message": {"locked": False},
                },
            ),
        ]
        self.consumer.channel_layer.group_send.assert_has_calls(calls, any_order=True)
        assert self.consumer.channel_layer.group_send.call_count == 2
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "show_update"})
        )
        mocked_data.assert_not_called()
        mocked_template.assert_not_called()

    async def test_widgets_historic_historicconsumer_process_for_timestamp_funct(
        self, mocker
    ):
        await self._connect_helper(mocker)
        carrier, bundle = mocker.MagicMock(), mocker.MagicMock()
        timestamp = 1724500000
        view = mocker.MagicMock()
        view.bundle = bundle
        view.carrier = carrier
        view.timestamp_for_x.return_value = timestamp
        self.consumer.view = view
        sync_to_async = mocker.AsyncMock()
        mocked_sync = mocker.patch(
            "inhouse.historic.consumers.sync_to_async",
            return_value=sync_to_async,
        )
        timestamp_data = mocker.MagicMock()
        sync_to_async.return_value = timestamp_data
        assets_data = mocker.MagicMock()
        mocked_data = mocker.patch(
            "inhouse.historic.consumers.assets_data_from_timestamp_data",
            return_value=assets_data,
        )
        mocked_consolidated = mocker.patch(
            "inhouse.historic.consumers.consolidated_view_charts_from_assets_data",
            return_value={"foo": "bar", "foobar": 1},
        )
        template = mocker.MagicMock()
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template", return_value=template
        )
        html = mocker.MagicMock()
        template.render.return_value = html
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        x_val, label = mocker.MagicMock(), mocker.MagicMock()
        message = {"x-val": x_val, "label": label}
        await self.consumer._process_for_timestamp(message)
        view.timestamp_for_x.assert_called_once_with(x_val)
        mocked_sync.assert_called_once_with(
            evaluate_bundle_ledger_data_for_timestamp, thread_sensitive=True
        )
        sync_to_async.assert_called_once_with(bundle, timestamp, carrier)
        timestamp_data.drop.assert_called_once_with(columns="timestamp")
        mocked_data.assert_called_once_with(
            timestamp, timestamp_data.drop.return_value, view.carrier
        )
        mocked_consolidated.assert_called_once_with(assets_data)
        mocked_template.assert_called_once_with("historic/assets.html")
        template.render.assert_called_once_with(
            context={
                "timestamp": timestamp,
                "date": "24 Aug 2024 13:46:40",
                "data": assets_data,
                "label": label,
                "foo": "bar",
                "foobar": 1,
            }
        )
        calls = [
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.lock_no_blur",
                    "message": {"locked": True},
                },
            ),
            mocker.call(
                self.consumer.bundle_group_name,
                {
                    "type": "historic.lock_no_blur",
                    "message": {"locked": False},
                },
            ),
        ]
        self.consumer.channel_layer.group_send.assert_has_calls(calls, any_order=True)
        assert self.consumer.channel_layer.group_send.call_count == 2
        mocked_send.assert_called_once_with(text_data=html)


class TestWidgetsHistoricConsumerBroadcasting(HistoricConsumerBaseTest):
    """Testing class for :class:`HistoricConsumer` broadcasting methods."""

    # # historic_process_altogether
    async def test_widgets_historic_historicconsumer_historic_process_altogether_funct(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        mocked_initialize = mocker.patch(
            "inhouse.historic.consumers.initialize_storage_carrier",
            return_value=carrier,
        )
        view = mocker.MagicMock()
        mocked_view = mocker.patch(
            "inhouse.historic.consumers.ViewStatus", return_value=view
        )
        mocked_process = mocker.patch(f"{CONSUMER_PATH}._process_for_period")
        bundle = mocker.MagicMock()
        event = {"message": {"bundle": bundle}}
        await self.consumer.historic_process_altogether(event)
        assert self.consumer.view == view
        mocked_initialize.assert_called_once_with()
        mocked_view.assert_called_once_with(bundle, carrier)
        mocked_process.assert_called_once_with(None)

    # # historic_lock_interaction
    async def test_widgets_historic_historicconsumer_historic_lock_interaction_locked(
        self, mocker
    ):
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        event = {"message": {"locked": True}}
        await self.consumer.historic_lock_interaction(event)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "lock_interaction", "locked": True})
        )

    async def test_widgets_historic_historicconsumer_historic_lock_interaction_no_lock(
        self, mocker
    ):
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        event = {"message": {"locked": False}}
        await self.consumer.historic_lock_interaction(event)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "lock_interaction", "locked": False})
        )

    # # historic_lock_no_blur
    async def test_widgets_historic_historicconsumer_historic_lock_no_blur_locked(
        self, mocker
    ):
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        event = {"message": {"locked": True}}
        await self.consumer.historic_lock_no_blur(event)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "lock_no_blur", "locked": True})
        )

    async def test_widgets_historic_historicconsumer_historic_lock_no_blur_no_lock(
        self, mocker
    ):
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        event = {"message": {"locked": False}}
        await self.consumer.historic_lock_no_blur(event)
        mocked_send.assert_called_once_with(
            text_data=json.dumps({"type": "lock_no_blur", "locked": False})
        )

    # # historic_locked
    async def test_widgets_historic_historicconsumer_historic_locked_functionality(
        self, mocker
    ):
        template = mocker.MagicMock()
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template", return_value=template
        )
        html = mocker.MagicMock()
        template.render.return_value = html
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        address = mocker.MagicMock()
        event = {"message": {"address": address}}
        await self.consumer.historic_locked(event)
        mocked_template.assert_called_once_with("historic/address_locked.html")
        template.render.assert_called_once_with(context={"address": address})
        mocked_send.assert_called_once_with(text_data=html)

    # # historic_processing
    async def test_widgets_historic_historicconsumer_historic_processing_functionality(
        self, mocker
    ):
        template = mocker.MagicMock()
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template", return_value=template
        )
        html = mocker.MagicMock()
        template.render.return_value = html
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        message = mocker.MagicMock()
        event = {"message": message}
        await self.consumer.historic_processing(event)
        mocked_template.assert_called_once_with("historic/processing.html")
        template.render.assert_called_once_with(context=message)
        mocked_send.assert_called_once_with(text_data=html)

    # # historic_update
    async def test_widgets_historic_historicconsumer_historic_update_for_update_none(
        self, mocker
    ):
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template"
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        message = mocker.MagicMock()
        event = {"message": message}
        returned = await self.consumer.historic_update(event)
        assert returned is True
        mocked_template.assert_not_called()
        mocked_send.assert_not_called()

    async def test_widgets_historic_historicconsumer_historic_update_for_phase_init(
        self, mocker
    ):
        update = mocker.MagicMock()
        self.consumer.update = update
        update.check_phase_init.return_value = True
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template"
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        message = mocker.MagicMock()
        event = {"message": message}
        returned = await self.consumer.historic_update(event)
        assert returned is True
        update.check_phase_init.assert_called_once_with(message)
        mocked_template.assert_not_called()
        mocked_send.assert_not_called()

    async def test_widgets_historic_historicconsumer_historic_update_for_no_phase(
        self, mocker
    ):
        update = mocker.MagicMock()
        self.consumer.update = update
        update.check_phase_init.return_value = False
        phase, value = None, None
        update.evaluate.return_value = (phase, value)
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template"
        )
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        address = mocker.MagicMock()
        message = {"address": address, "foo": "bar"}
        event = {"message": message}
        returned = await self.consumer.historic_update(event)
        assert returned is True
        update.check_phase_init.assert_called_once_with(message)
        update.evaluate.assert_called_once_with(message)
        mocked_template.assert_not_called()
        mocked_send.assert_not_called()

    async def test_widgets_historic_historicconsumer_historic_update_functionality(
        self, mocker
    ):
        update = mocker.MagicMock()
        self.consumer.update = update
        update.check_phase_init.return_value = False
        phase, value = 1, 90
        update.evaluate.return_value = (phase, value)
        template = mocker.MagicMock()
        mocked_template = mocker.patch(
            "inhouse.historic.consumers.get_template", return_value=template
        )
        html = mocker.MagicMock()
        template.render.return_value = html
        mocked_send = mocker.patch(f"{CONSUMER_PATH}.send")
        address = mocker.MagicMock()
        message = {"address": address, "foo": "bar"}
        event = {"message": message}
        await self.consumer.historic_update(event)
        update.check_phase_init.assert_called_once_with(message)
        update.evaluate.assert_called_once_with(message)
        template.render.assert_called_once_with(
            context={"address": address, "phase": phase, "value": value}
        )
        mocked_template.assert_called_once_with("historic/update_status.html")
        mocked_send.assert_called_once_with(text_data=html)
