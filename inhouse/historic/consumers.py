"""Module containing historic widget's websocket consumers."""

import json
from datetime import datetime, UTC

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import get_template

from storage.helpers import (
    check_chart_period,
    group_name_from_bundle,
    load_bundle_event_records,
)
from storage.ledger import (
    evaluate_bundle_ledger_data_for_period,
    evaluate_bundle_ledger_data_for_timestamp,
)
from storage.main import (
    initialize_storage_carrier,
    retrieve_bundle_historic_data,
)

from .assets import assets_data_from_timestamp_data
from .charts import (
    asset_values_from_computed_data,
    charts_data_from_asset_values_and_timeline_data,
    consolidated_view_charts_from_assets_data,
)
from .structs import UpdateStatus, ViewStatus


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
        :var events: collection of bundle's phases and processing statuses
        :type events: dict
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
            events = load_bundle_event_records(message.get("bundle"))
            if not events:
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

        print(f"Range received: {message.get('x-min')} - {message.get('x-max')}")
        x_min, x_max = self.view.x_axis_boundaries(
            message.get("x-min"), message.get("x-max")
        )

        if not self.view.is_range_changed(x_min, x_max):
            return True

        period = self.view.period_for_range(x_min, x_max)
        print(f"Range processed: {x_min} - {x_max}")

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
        retrieve_bundle_historic_data(message)
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
        """Load processing statuses from disk for `bundle` and update UI if they exist.

        :param bundle: unique identifier of addresses collection
        :type bundle: str
        :var events: collection of bundle's phases and processing statuses
        :type events: dict
        """
        events = load_bundle_event_records(bundle)
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
        """Calculate charts data for provided `period` and send it to client.

        :param period: chart's minimum and maximum timestamps
        :type period: two-tuple
        :var timestamps: chart's central/visible area timestamps collection
        :type timestamps: list
        :var computed_data: fully evaluated bundle ledger data for zoomed out period
        :type computed_data: :class:`pandas.DataFrame`
        :var timeline_data: evaluated timestamps across the whole timeline
        :type timeline_data: :class:`pandas.DataFrame`
        :var asset_tags: collection of assets and related unit or associated group
        :type asset_tags: dict
        :var asset_values: asset values data for equally distributed timestamps
        :type asset_values: :class:`pandas.DataFrame`
        :var charts_data: bar and candlestick chart labels and datasets collection
        :type charts_data: dict
        :var extended_timestamps: chart's extended timestamps collection
        :type extended_timestamps: list
        """
        print("period", period)

        timestamps, computed_data, timeline_data, asset_tags = await sync_to_async(
            evaluate_bundle_ledger_data_for_period, thread_sensitive=True
        )(
            self.view.bundle,
            self.view.evaluated_timestamps,
            self.view.carrier,
            period=period,
        )
        if timestamps is None:
            await self.channel_layer.group_send(
                self.bundle_group_name,
                {"type": "historic.lock_no_blur", "message": {"locked": False}},
            )
            return await self.send(text_data=json.dumps({"type": "show_update"}))

        if not computed_data.empty:
            asset_values = asset_values_from_computed_data(computed_data)
            self.view.record_asset_values(asset_values)

        charts_data, extended_timestamps = (
            charts_data_from_asset_values_and_timeline_data(
                self.view.asset_values_for_timestamps(timestamps),
                timeline_data,
                asset_tags,
            )
        )
        self.view.record_timestamps(extended_timestamps)
        if period is None:
            self.view.reset_current_range()

        await self.send(
            text_data=json.dumps({"type": "update_charts", "data": charts_data})
        )
        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_interaction", "message": {"locked": False}},
        )

    async def _process_for_timestamp(self, message):
        """Evaluate bundle for provided `timestamp` and send rendered HTML to client.

        :param message: show timestamp message data sent by htmx
        :type message: dict
        :var timestamp: seconds since epoch point in time to process data for
        :type timestamp: int
        :var timestamp_data: fully evaluated bundle ledger data for single timestamp
        :type timestamp_data: :class:`pandas.DataFrame`
        :var assets_data: processed asset section data ready for rendering
        :type assets_data: dict
        :var label: unit whose section is about to be revealed
        :type label: str
        :var html: rendered html of the status phase's div
        :type html: str
        """
        print("x-val", message.get("x-val"))
        timestamp = self.view.timestamp_for_x(message.get("x-val"))
        print("timestamp", timestamp)

        await self.channel_layer.group_send(
            self.bundle_group_name,
            {"type": "historic.lock_no_blur", "message": {"locked": True}},
        )

        timestamp_data = await sync_to_async(
            evaluate_bundle_ledger_data_for_timestamp, thread_sensitive=True
        )(
            self.view.bundle,
            timestamp,
            self.view.carrier,
        )
        if timestamp_data is None:
            await self.channel_layer.group_send(
                self.bundle_group_name,
                {"type": "historic.lock_no_blur", "message": {"locked": False}},
            )
            return await self.send(text_data=json.dumps({"type": "show_update"}))

        assets_data = assets_data_from_timestamp_data(
            timestamp, timestamp_data.drop(columns="timestamp"), self.view.carrier
        )
        label = message.get("label")
        print("label", label)

        # path = f"/home/ipaleka/Downloads/{timestamp}-assets-data.json"
        # with open(path, "w") as assets_data_file:
        #     json.dump(assets_data, assets_data_file)
        # timestamp_data.to_csv(
        #     f"/home/ipaleka/Downloads/{timestamp}-timestamp-data.csv",
        #     sep=";",
        #     index=False,
        # )

        html = get_template("historic/assets.html").render(
            context={
                "timestamp": timestamp,
                "date": datetime.fromtimestamp(timestamp, UTC).strftime(
                    "%-d %b %Y %H:%M:%S"
                ),
                "data": assets_data,
                "label": label,
                **consolidated_view_charts_from_assets_data(assets_data),
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
        :var carrier: instance with storage related methods and variables
        :type carrier: :class:`storage.main.StorageCarrier`
        """
        bundle = event["message"]["bundle"]
        carrier = initialize_storage_carrier()

        self.view = ViewStatus(bundle, carrier)

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
