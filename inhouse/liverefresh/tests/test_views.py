"""Testing module for the Real-time refresh widget's view."""

import msgpack
from django.http import HttpResponse

from widgets.inhouse.liverefresh.views import (
    PAYLOAD_PREFIX,
    SUBSCRIBED_KEY,
    LiveRefreshView,
)

ADDRESS = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"


def _view(mocker, bundle="HASH", addresses=ADDRESS, session=None):
    view = LiveRefreshView()
    view.bundle = bundle
    view.addresses = addresses
    view.request = mocker.MagicMock(session=session if session is not None else {})
    view.kwargs = {}
    return view


class TestLiveRefreshViewPoll:
    """What the poll does with what the engine published."""

    def test_liverefresh_poll_is_the_heartbeat(self, mocker):
        """**Serving the poll is what keeps the engine re-pricing this page.**

        There is no subscribe and no unsubscribe to keep in step with a reader
        who closed a tab: they stop polling, and the page ages out of the set
        the engine reads. Nothing else writes it, so if this stops the feature
        goes quiet rather than wrong.
        """
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        view.get(view.request)

        key, mapping = client.zadd.call_args.args
        assert key == SUBSCRIBED_KEY
        assert list(mapping) == [ADDRESS]

    def test_liverefresh_poll_heartbeats_even_with_nothing_published(self, mocker):
        """The order matters: a page nobody has re-priced yet is exactly the one
        that needs the engine told about it."""
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        response = view.get(view.request)

        assert client.zadd.called
        assert response.status_code == 204

    def test_liverefresh_poll_reads_the_published_payload(self, mocker):
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 5.0, "values": {1: 2.0}})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        client.get.assert_called_once_with(f"{PAYLOAD_PREFIX}:HASH")
        assert rendered.call_args.args[0]["payload"]["total"] == 5.0

    def test_liverefresh_poll_decodes_integer_asset_keys(self, mocker):
        """msgpack refuses integer map keys unless told otherwise, and the
        values map is keyed by asset id. Without this the payload is a thousand
        readable bytes that nobody can read."""
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 5.0, "values": {31566704: 2.5}}
        )
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert rendered.call_args.args[0]["payload"]["values"] == {31566704: 2.5}

    def test_liverefresh_poll_answers_204_when_the_total_has_not_moved(self, mocker):
        """**Most blocks move nothing for most pages.**

        htmx leaves the page alone on a 204, so an unchanged block costs one
        request and no DOM work - which is the difference between a poll that
        is cheap and one that repaints a page every three seconds for nothing.
        """
        session = {"liverefresh:HASH": 5.0}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 5.0})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        response = view.get(view.request)

        assert response.status_code == 204

    def test_liverefresh_poll_renders_when_the_total_moved(self, mocker):
        session = {"liverefresh:HASH": 5.0}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 7.5})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert rendered.called
        assert session["liverefresh:HASH"] == 7.5

    def test_liverefresh_poll_remembers_per_page_not_per_reader(self, mocker):
        """A reader with two address pages open must not have one silence the
        other, so what was last shown is keyed by the page."""
        session = {"liverefresh:OTHER": 7.5}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 7.5})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert session["liverefresh:HASH"] == 7.5
        assert session["liverefresh:OTHER"] == 7.5


class TestLiveRefreshViewGate:
    """Who may poll at all."""

    def test_liverefresh_gate_uses_the_widget_manifest(self, mocker):
        """**It is a widget, not a condition in a view.**

        A reader selects it and a subscriber pays for it, and a fork of this
        site should be able to host it for its own users on its own bands - so
        the gate is the manifest, exactly as the historic widget's is.
        """
        view = LiveRefreshView()
        view.kwargs = {"value": ADDRESS}
        view.args = ()
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=("HASH", f"{ADDRESS} {ADDRESS}"),
        )
        gate = mocker.patch.object(LiveRefreshView, "manifest_test_func")

        view.test_func()

        gate.assert_called_once_with(2)
