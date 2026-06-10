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
            mocker,
            {"HX-Trigger": "id-show"},
            "_process_for_timestamp",
            {"type": "show"},
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
        consolidated = mocker.patch(
            "widgets.inhouse.historic.consumers."
            "consolidated_view_charts_from_assets_data",
            return_value={"asachart": {}},
        )
        template = mocker.patch("widgets.inhouse.historic.consumers.get_template")
        template.return_value.render.return_value = "<div></div>"
        async_to_sync(consumer._process_for_timestamp)(
            {"x-val": "100", "label": "ALGO"}
        )
        consolidated.assert_called_once_with({})
        context = template.return_value.render.call_args.kwargs["context"]
        assert context["label"] == "ALGO"
        assert context["asachart"] == {}
        consumer.send.assert_awaited_once_with(text_data="<div></div>")


class TestHistoricConsumersBroadcasting:
    """Testing class for the consumer broadcasting handlers."""

    def test_historic_consumers_lock_interaction_sends(self, mocker):
        consumer = _consumer(mocker)
        async_to_sync(consumer.historic_lock_interaction)({"message": {"locked": True}})
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "lock_interaction", "locked": True})
        )

    def test_historic_consumers_lock_no_blur_sends(self, mocker):
        consumer = _consumer(mocker)
        async_to_sync(consumer.historic_lock_no_blur)({"message": {"locked": False}})
        consumer.send.assert_awaited_once_with(
            text_data=json.dumps({"type": "lock_no_blur", "locked": False})
        )


class TestHistoricConsumersConnect:
    """Testing class for :py:meth:`...HistoricConsumer.connect`."""

    def test_historic_consumers_connect_functionality(self, mocker):
        consumer = _consumer(mocker)
        consumer.scope = {"url_route": {"kwargs": {"bundle": "BUNDLE"}}}
        consumer.accept = mocker.AsyncMock()
        mocker.patch(
            "widgets.inhouse.historic.consumers.group_name_from_bundle",
            return_value="historic_BUNDLE",
        )
        load = mocker.patch.object(HistoricConsumer, "_load_statuses")
        altogether = mocker.patch.object(
            HistoricConsumer, "historic_process_altogether"
        )
        async_to_sync(consumer.connect)()
        consumer.channel_layer.group_add.assert_awaited_once_with(
            "historic_BUNDLE", "channel"
        )
        consumer.accept.assert_awaited_once()
        load.assert_awaited_once_with("BUNDLE")
        altogether.assert_awaited_once_with({"message": {"bundle": "BUNDLE"}})


class TestHistoricConsumersDisconnect:
    """Testing class for :py:meth:`...HistoricConsumer.disconnect`."""

    def test_historic_consumers_disconnect_functionality(self, mocker):
        consumer = _consumer(mocker)
        async_to_sync(consumer.disconnect)(1000)
        consumer.channel_layer.group_discard.assert_awaited_once_with(
            "historic_BUNDLE", "channel"
        )


class TestHistoricConsumersChangePeriod:
    """Testing class for :py:meth:`...HistoricConsumer._change_period`."""

    def test_historic_consumers_change_period_without_view(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = None
        assert async_to_sync(consumer._change_period)({}) is True

    def test_historic_consumers_change_period_unchanged_range(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock()
        consumer.view.x_axis_boundaries.return_value = (1, 2)
        consumer.view.is_range_changed.return_value = False
        message = {"x-min": "1", "x-max": "2"}
        assert async_to_sync(consumer._change_period)(message) is True

    def test_historic_consumers_change_period_processes(self, mocker):
        consumer = _consumer(mocker)
        consumer.view = mocker.MagicMock()
        consumer.view.x_axis_boundaries.return_value = (0, 20)
        consumer.view.is_range_changed.return_value = True
        consumer.view.period_for_range.return_value = (1, 2)
        mocker.patch(
            "widgets.inhouse.historic.consumers.check_chart_period",
            return_value=(1, 2),
        )
        process = mocker.patch.object(HistoricConsumer, "_process_for_period")
        async_to_sync(consumer._change_period)({"x-min": "0", "x-max": "20"})
        assert consumer.channel_layer.group_send.await_count == 1
        process.assert_awaited_once_with((1, 2))


class TestHistoricConsumersInitiateUpdate:
    """Testing class for :py:meth:`...HistoricConsumer._initiate_update`."""

    def test_historic_consumers_initiate_update_functionality(self, mocker):
        consumer = _consumer(mocker)
        update_cls = mocker.patch("widgets.inhouse.historic.consumers.UpdateStatus")
        update_cls.return_value.template_context.return_value = {"ctx": 1}
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        message = {"bundle": "BUNDLE", "addresses": "A1"}
        async_to_sync(consumer._initiate_update)(message)
        update_cls.assert_called_once_with(message)
        engine.assert_called_once_with(
            "historic:process",
            "POST",
            "/api/v2/historic/BUNDLE/process/",
            mocker.ANY,
            json=message,
        )
        assert consumer.channel_layer.group_send.await_count == 2


class TestHistoricConsumersLoadStatuses:
    """Testing class for :py:meth:`...HistoricConsumer._load_statuses`."""

    def test_historic_consumers_load_statuses_without_events(self, mocker):
        consumer = _consumer(mocker)
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {}
        async_to_sync(consumer._load_statuses)("BUNDLE")
        consumer.channel_layer.group_send.assert_not_awaited()

    def test_historic_consumers_load_statuses_finished(self, mocker):
        consumer = _consumer(mocker)
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {
            "bundle": "BUNDLE",
            "BUNDLE": {"-1": {"state": "finished"}},
        }
        mocker.patch("widgets.inhouse.historic.consumers.UpdateStatus")
        async_to_sync(consumer._load_statuses)("BUNDLE")
        assert consumer.channel_layer.group_send.await_count == 1

    def test_historic_consumers_load_statuses_not_finished(self, mocker):
        consumer = _consumer(mocker)
        engine = mocker.patch("widgets.inhouse.historic.consumers.engine_request")
        engine.return_value.json.return_value = {
            "bundle": "BUNDLE",
            "BUNDLE": {"0": {"state": 1}},
        }
        mocker.patch("widgets.inhouse.historic.consumers.UpdateStatus")
        async_to_sync(consumer._load_statuses)("BUNDLE")
        assert consumer.channel_layer.group_send.await_count == 2


class TestHistoricConsumersProcessAltogether:
    """Testing class for :py:meth:`...HistoricConsumer.historic_process_altogether`."""

    def test_historic_consumers_process_altogether_functionality(self, mocker):
        consumer = _consumer(mocker)
        view_cls = mocker.patch("widgets.inhouse.historic.consumers.ViewStatus")
        process = mocker.patch.object(HistoricConsumer, "_process_for_period")
        async_to_sync(consumer.historic_process_altogether)(
            {"message": {"bundle": "BUNDLE"}}
        )
        view_cls.assert_called_once_with("BUNDLE")
        process.assert_awaited_once_with(None)


class TestHistoricConsumersRenderingHandlers:
    """Testing class for the consumer's template-rendering broadcast handlers."""

    def test_historic_consumers_locked_renders(self, mocker):
        consumer = _consumer(mocker)
        template = mocker.patch("widgets.inhouse.historic.consumers.get_template")
        template.return_value.render.return_value = "<div></div>"
        async_to_sync(consumer.historic_locked)({"message": {"address": "A1"}})
        assert template.return_value.render.call_args.kwargs["context"] == {
            "address": "A1"
        }
        consumer.send.assert_awaited_once_with(text_data="<div></div>")

    def test_historic_consumers_processing_renders(self, mocker):
        consumer = _consumer(mocker)
        template = mocker.patch("widgets.inhouse.historic.consumers.get_template")
        template.return_value.render.return_value = "<div></div>"
        async_to_sync(consumer.historic_processing)({"message": {"bundle": "B"}})
        consumer.send.assert_awaited_once_with(text_data="<div></div>")

    def test_historic_consumers_update_without_update(self, mocker):
        consumer = _consumer(mocker)
        consumer.update = None
        assert async_to_sync(consumer.historic_update)({"message": {}}) is True

    def test_historic_consumers_update_on_phase_init(self, mocker):
        consumer = _consumer(mocker)
        consumer.update = mocker.MagicMock()
        consumer.update.check_phase_init.return_value = True
        assert async_to_sync(consumer.historic_update)({"message": {"x": 1}}) is True

    def test_historic_consumers_update_without_phase(self, mocker):
        consumer = _consumer(mocker)
        consumer.update = mocker.MagicMock()
        consumer.update.check_phase_init.return_value = False
        consumer.update.evaluate.return_value = (None, None)
        assert async_to_sync(consumer.historic_update)({"message": {"x": 1}}) is True

    def test_historic_consumers_update_renders(self, mocker):
        consumer = _consumer(mocker)
        consumer.update = mocker.MagicMock()
        consumer.update.check_phase_init.return_value = False
        consumer.update.evaluate.return_value = (2, 50)
        template = mocker.patch("widgets.inhouse.historic.consumers.get_template")
        template.return_value.render.return_value = "<div></div>"
        async_to_sync(consumer.historic_update)({"message": {"address": "A1"}})
        context = template.return_value.render.call_args.kwargs["context"]
        assert context == {"address": "A1", "phase": 2, "value": 50}
        consumer.send.assert_awaited_once_with(text_data="<div></div>")
