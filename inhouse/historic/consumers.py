"""Module containing historic widget's websocket consumers."""

import json

from api.client import engine_request
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import get_template

from .charts import consolidated_view_charts_from_assets_data
from .helpers import check_chart_period, group_name_from_bundle
from .manifest import MANIFEST
from .structs import UpdateStatus, ViewStatus
from .wire import deserialize_assets_data


def _restore_event_phase_keys(events):
    """Restore integer phase keys lost when the events endpoint serialized to JSON.

    The engine builds each address record with integer phase keys, but JSON
    transport stringifies them; this converts them back so ``UpdateStatus`` and
    the finished-state check operate as before. Non-mapping entries (``bundle``,
    ``addresses``) are passed through untouched.

    :param events: events mapping as decoded from the engine JSON response
    :type events: dict
    :return: dict
    """
    return {
        key: (
            {int(phase): values for phase, values in value.items()}
            if isinstance(value, dict)
            else value
        )
        for key, value in events.items()
    }


class HistoricConsumer(AsyncWebsocketConsumer):
    """Websocket consumer for processing bundle/address historic data.

    :var HistoricConsumer.bundle_group_name: historic widget group channel name
    :type HistoricConsumer.bundle_group_name: str
    :var HistoricConsumer.update: custom object carrying update status data and methods
    :type HistoricConsumer.update: :class:`UpdateStatus`
    :var HistoricConsumer.view: custom object carrying view status data and methods
    :type HistoricConsumer.view: :class:`ViewStatus`
    """

    bundle_group_name = None
    update = None
    view = None

    async def connect(self):
        """Add consumer to group defined from bundle argument and accept connections.

        :var bundle: unique identifier of scope's addresses collection
        :type bundle: str
        """
        bundle = self.scope["url_route"]["kwargs"]["bundle"]
        self.bundle_group_name = group_name_from_bundle(bundle)

        await self.channel_layer.group_add(self.bundle_group_name, self.channel_name)
        await self.accept()

        await self._load_statuses(bundle)

        await self.historic_process_altogether({"message": {"bundle": bundle}})

    async def disconnect(self, close_code):
        """Disconnect consumer from bundle group.

        :var close_code: unique code of the event that caused connection closing
        :type close_code: int
        """
        await self.channel_layer.group_discard(
            self.bundle_group_name, self.channel_name
        )

    async def receive(self, text_data):
        """Parse provided `text_data` and call routine related to message type.

        :param text_data: stringified message's data object
        :type text_data: str
        :var message: processing message data sent by htmx
        :type message: dict
        """
        message = json.loads(text_data)
        if (
            message.get("HEADERS")
            and message["HEADERS"].get("HX-Trigger") == "id-process"
        ):
            await self._initiate_update(message)

        elif (
            message.get("HEADERS")
            and message["HEADERS"].get("HX-Trigger") == "id-view"
            and message.get("type") == "zoom"
        ):
            await self._change_period(message)

        elif message.get("HEADERS") and message["HEADERS"].get("HX-Trigger") in (
            "id-reset-bars",
            "id-reset-candles",
        ):
            await self._process_for_period(None)

        elif (
            message.get("HEADERS")
            and message["HEADERS"].get("HX-Trigger") == "id-show"
            and message.get("type") == "show"
        ):
            await self._process_for_timestamp(message)

    # # PROCESSING
    async def _change_period(self, message):
        """Calculate and send new charts data based on range received from browser.

        `check_chart_period` function returns either the original period or
        adjusted one that doesn't exceed the maximum available zoom.

        :param message: chart zoom message data sent by htmx
        :type message: dict
        :var x_min: sender's chart x-axis minimum value
        :type x_min: int
        :var x_max: sender's chart x-axis maximum value
        :type x_max: int
        :var period: current chart's minimum and maximum timestamps
        :type period: two-tuple
        """
        if self.view is None:
            return True

        x_min, x_max = self.view.x_axis_boundaries(
            message.get("x-min"), message.get("x-max")
        )

        if not self.view.is_range_changed(x_min, x_max):
            return True

        period = self.view.period_for_range(x_min, x_max)

        period = check_chart_period(period)

        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_interaction", "message": {"locked": True}},
        )
        await self._process_for_period(period)

    async def _initiate_update(self, message):
        """Start bundle historic data processing configured from provided message.

        :param message: processing message data sent by htmx
        :type message: dict
        """
        self.update = UpdateStatus(message)
        await sync_to_async(engine_request, thread_sensitive=False)(
            "historic:process",
            "POST",
            f"/api/v2/historic/{message['bundle']}/process/",
            MANIFEST.engine_endpoints,
            json=message,
        )
        await self.channel_layer.group_send(
            self.bundle_group_name,
            {
                "type": "historic.processing",
                "message": self.update.template_context(),
            },
        )
        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_interaction", "message": {"locked": True}},
        )

    async def _load_statuses(self, bundle):
        """Load processing statuses from the engine for `bundle` and update UI.

        :param bundle: unique identifier of addresses collection
        :type bundle: str
        :var response: engine events endpoint response
        :type response: :class:`requests.Response`
        :var events: collection of bundle's phases and processing statuses
        :type events: dict
        """
        response = await sync_to_async(engine_request, thread_sensitive=False)(
            "historic:events",
            "GET",
            f"/api/v2/historic/{bundle}/events/",
            MANIFEST.engine_endpoints,
        )
        events = _restore_event_phase_keys(response.json())
        if events:
            self.update = UpdateStatus(events)
            await self.channel_layer.group_send(
                self.bundle_group_name,
                {
                    "type": "historic.processing",
                    "message": self.update.template_context(events=events),
                },
            )
            if events.get(bundle, {}).get(-1, {}).get("state") != "finished":
                await self.channel_layer.group_send(
                    self.bundle_group_name,
                    {"type": "historic.lock_interaction", "message": {"locked": True}},
                )

    async def _process_for_period(self, period):
        """Request charts data for provided `period` from the engine and send it.

        :param period: chart's minimum and maximum timestamps
        :type period: two-tuple
        :var response: engine evaluate endpoint response
        :type response: :class:`requests.Response`
        :var data: render-ready charts payload or a show-update marker
        :type data: dict
        """
        response = await sync_to_async(engine_request, thread_sensitive=False)(
            "historic:evaluate",
            "POST",
            f"/api/v2/historic/{self.view.bundle}/evaluate/",
            MANIFEST.engine_endpoints,
            json={"period": period},
        )
        data = response.json()
        if data.get("type") == "show_update":
            await self.channel_layer.group_send(
                self.bundle_group_name,
                {"type": "historic.lock_no_blur", "message": {"locked": False}},
            )
            return await self.send(text_data=json.dumps({"type": "show_update"}))

        self.view.record_timestamps(data["extended_timestamps"])
        if period is None:
            self.view.reset_current_range()

        await self.send(
            text_data=json.dumps({"type": "update_charts", "data": data["charts_data"]})
        )
        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_interaction", "message": {"locked": False}},
        )

    async def _process_for_timestamp(self, message):
        """Request timestamp evaluation from the engine and send rendered HTML.

        :param message: show timestamp message data sent by htmx
        :type message: dict
        :var timestamp: seconds since epoch point in time to process data for
        :type timestamp: int
        :var response: engine timestamp endpoint response
        :type response: :class:`requests.Response`
        :var data: render-ready assets context or a show-update marker
        :type data: dict
        :var html: rendered html of the assets section
        :type html: str
        """
        timestamp = self.view.timestamp_for_x(message.get("x-val"))

        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_no_blur", "message": {"locked": True}},
        )

        response = await sync_to_async(engine_request, thread_sensitive=False)(
            "historic:timestamp",
            "POST",
            f"/api/v2/historic/{self.view.bundle}/timestamp/",
            MANIFEST.engine_endpoints,
            json={"timestamp": timestamp},
        )
        data = response.json()
        if data.get("type") == "show_update":
            await self.channel_layer.group_send(
                self.bundle_group_name,
                {"type": "historic.lock_no_blur", "message": {"locked": False}},
            )
            return await self.send(text_data=json.dumps({"type": "show_update"}))

        assets_data = deserialize_assets_data(data["data"])
        consolidated = consolidated_view_charts_from_assets_data(assets_data)
        html = get_template("historic/assets.html").render(
            context={
                **data,
                "data": assets_data,
                **consolidated,
                "label": message.get("label"),
            }
        )
        await self.send(text_data=html)
        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_no_blur", "message": {"locked": False}},
        )

    # # BROADCASTING
    async def historic_process_altogether(self, event):
        """Process and emit fully zoomed-out charts data for bundle.

        :param event: processing status message data
        :type event: dict
        :var bundle: unique identifier of scope's addresses collection
        :type bundle: str
        """
        bundle = event["message"]["bundle"]

        self.view = ViewStatus(bundle)

        await self._process_for_period(None)

    async def historic_lock_interaction(self, event):
        """Send "lock_interaction" message to the channel with the locked argument.

        :param event: message holding locked value
        :type event: dict
        """
        await self.send(
            text_data=json.dumps(
                {"type": "lock_interaction", "locked": event["message"]["locked"]}
            )
        )

    async def historic_lock_no_blur(self, event):
        """Send "lock_no_blur" message to the channel with the locked argument.

        :param event: message holding locked value
        :type event: dict
        """
        await self.send(
            text_data=json.dumps(
                {"type": "lock_no_blur", "locked": event["message"]["locked"]}
            )
        )

    async def historic_locked(self, event):
        """Return rendered HTML indicating that address from provided `event` is locked.

        :param event: processing status message data
        :type event: dict
        :var html: rendered html of the status phase's div
        :type html: str
        """
        html = get_template("historic/address_locked.html").render(
            context={"address": event["message"]["address"]}
        )
        await self.send(text_data=html)

    async def historic_processing(self, event):
        """Render and return HTML of the processing status element.

        :param event: processing status message data
        :type event: dict
        :var html: rendered initial html of the status div
        :type html: str
        """
        html = get_template("historic/processing.html").render(context=event["message"])
        await self.send(text_data=html)

    async def historic_update(self, event):
        """Calculate processing phase value/percentage and return related rendered HTML.

        :param event: processing update status message data
        :type event: dict
        :var phase: historic data fetching/processing phase to update
        :type phase: int
        :var value: percentage of the related phase's finished part
        :type value: int
        :var context: data to render related template segment with
        :type context: dict
        :var html: rendered html of the status phase's div
        :type html: str
        """
        if self.update is None or self.update.check_phase_init(event["message"]):
            return True

        phase, value = self.update.evaluate(event["message"])
        if phase is None:
            return True

        context = {
            "address": event["message"]["address"],
            "phase": phase,
            "value": value,
        }
        html = get_template("historic/update_status.html").render(context=context)
        await self.send(text_data=html)
