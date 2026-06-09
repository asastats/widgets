"""Testing module for :py:mod:`widgets.inhouse.historic.consumers` module."""

import json

from asgiref.sync import async_to_sync

from widgets.inhouse.historic.consumers import (
    HistoricConsumer,
    _restore_event_phase_keys,
)


def _consumer(mocker):
    """Return a consumer with mocked channel layer and send coroutine."""
    consumer = HistoricConsumer()
    consumer.channel_layer = mocker.AsyncMock()
    consumer.channel_name = "channel"
    consumer.bundle_group_name = "historic_BUNDLE"
    consumer.send = mocker.AsyncMock()
    return consumer


class TestHistoricConsumersRestoreEventPhaseKeys:
    """Testing class for :py:func:`...consumers._restore_event_phase_keys`."""

    def test_historic_consumers_restore_event_phase_keys_functionality(self):
        events = {
            "bundle": "B",
            "addresses": "A1",
            "A1": {"-1": {"state": "finished"}, "0": {"state": 1}},
        }
        restored = _restore_event_phase_keys(events)
        assert restored["A1"][-1] == {"state": "finished"}
        assert restored["A1"][0] == {"state": 1}
        assert restored["bundle"] == "B"


class TestHistoricConsumersReceive:
    """Testing class for :py:meth:`...consumers.HistoricConsumer.receive`."""

    def _route(self, mocker, headers, method, extra=None):
        consumer = _consumer(mocker)
        target = mocker.patch.object(HistoricConsumer, method)
        message = {"HEADERS": headers}
        if extra:
            message.update(extra)
        async_to_sync(consumer.receive)(json.dumps(message))
        return target

    def test_historic_consumers_receive_routes_process(self, mocker):
        target = self._route(mocker, {"HX-Trigger": "id-process"}, "_initiate_update")
        assert target.called

    def test_historic_consumers_receive_routes_zoom(self, mocker):
        target = self._route(
            mocker, {"HX-Trigger": "id-view"}, "_change_period", {"type": "zoom"}
        )
        assert target.called

    def test_historic_consumers_receive_routes_reset(self, mocker):
        target = self._route(
            mocker, {"HX-Trigger": "id-reset-bars"}, "_process_for_period"
        )
        target.assert_called_once_with(None)

    def test_historic_consumers_receive_routes_show(self, mocker):
        target = self._route(
            mocker, {"HX-Trigger": "id-show"}, "_process_for_timestamp", {"type": "show"}
        )
        assert target.called


class TestHistoricConsumersProcessForPeriod:
    """Testing class for :py:meth:`...HistoricConsumer._process_for_period`."""

    def test_historic_consumers_process_for_period_show_update(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock(bundle="BUNDLE")
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {"type": "show_update"}
        async_to_sync(consumer._process_for_period)((1, 2))
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "show_update"})
        )

    def test_historic_consumers_process_for_period_sends_charts(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock(bundle="BUNDLE")
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {
            "charts_data": {"bar": 1},
            "extended_timestamps": [1, 2, 3],
        }
        async_to_sync(consumer._process_for_period)((1, 2))
        consumer.view.record_timestamps.assert_called_once_with([1, 2, 3])
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "update_charts", "data": {"bar": 1}})
        )

    def test_historic_consumers_process_for_period_resets_on_initial(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock(bundle="BUNDLE")
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {
            "charts_data": {},
            "extended_timestamps": [],
        }
        async_to_sync(consumer._process_for_period)(None)
        consumer.view.reset_current_range.assert_called_once()


class TestHistoricConsumersProcessForTimestamp:
    """Testing class for :py:meth:`...HistoricConsumer._process_for_timestamp`."""

    def test_historic_consumers_process_for_timestamp_show_update(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock(bundle="BUNDLE")
        consumer.view.timestamp_for_x.return_value = 100
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {"type": "show_update"}
        async_to_sync(consumer._process_for_timestamp)({"x-val": "100"})
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "show_update"})
        )

    def test_historic_consumers_process_for_timestamp_renders_html(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock(bundle="BUNDLE")
        consumer.view.timestamp_for_x.return_value = 100
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {"data": {}, "date": "x"}
        template = mocker.patch(
            "widgets.inhouse.historic.consumers.get_template"
        )
        template.return_value.render.return_value = "<div></div>"
        async_to_sync(consumer._process_for_timestamp)(
            {"x-val": "100", "label": "ALGO"}
        )
        consumer.send.assert_awaited_once_with(text_data="<div></div>")
        assert template.return_value.render.call_args.kwargs["context"]["label"] == "ALGO"


class TestHistoricConsumersBroadcasting:
    """Testing class for the consumer broadcasting handlers."""

    def test_historic_consumers_lock_interaction_sends(self, mocker):
        consumer = _consumer(mocker)
        async_to_sync(consumer.historic_lock_interaction)(
            {"message": {"locked": True}}
        )
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "lock_interaction", "locked": True})
        )

    def test_historic_consumers_lock_no_blur_sends(self, mocker):
        consumer = _consumer(mocker)
        async_to_sync(consumer.historic_lock_no_blur)(
            {"message": {"locked": False}}
        )
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "lock_no_blur", "locked": False})
        )
