"""Testing module for historic widget's asynchronous routing module."""

from django.urls import URLPattern

from widgets.inhouse.historic import routing


class TestWidgetsHistoricRouting:
    """Testing class for :py:mod:`widgets.inhouse.historic.routing` module."""

    def test_widgets_inhouse_historic_routing_websocket_urlpatterns(self):
        url = routing.websocket_urlpatterns
        assert len(url) == 1
        assert isinstance(url[0], URLPattern)
        assert url[0].lookup_str == "widgets.inhouse.historic.consumers.HistoricConsumer"
        assert str(url[0].pattern) == "widgets/historic/(?P<bundle>\w{40}|\w{58})/$"
