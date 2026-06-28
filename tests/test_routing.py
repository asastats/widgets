"""Testing module for :py:mod:`widgets.routing` module."""

import importlib
from types import SimpleNamespace

from django.urls import URLPattern

from widgets import routing


class TestWidgetsRouting:
    """Testing class for :py:mod:`widgets.routing` module."""

    def test_widgets_routing_websocket_urlpatterns(self):
        patterns = routing.websocket_urlpatterns
        assert len(patterns) == 1
        assert isinstance(patterns[0], URLPattern)
        assert (
            patterns[0].lookup_str
            == "widgets.inhouse.historic.consumers.HistoricConsumer"
        )

    def test_widgets_routing_falls_back_to_bare_imports(self, mocker):
        def fake_find_spec(name):
            if name.startswith("widgets."):
                raise ModuleNotFoundError(name)
            return object()

        mocker.patch("importlib.util.find_spec", side_effect=fake_find_spec)
        mocker.patch(
            "importlib.import_module",
            side_effect=lambda name: SimpleNamespace(websocket_urlpatterns=[(name,)]),
        )
        try:
            importlib.reload(routing)
            assert routing.websocket_urlpatterns == [
                ("inhouse.historic.routing",),
                ("inhouse.folks.routing",),
                ("inhouse.haystack.routing",),
                ("inhouse.swapcore.routing",),
            ]
        finally:
            mocker.stopall()
            importlib.reload(routing)
