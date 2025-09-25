"""Historic user widget websocket routes configuration module."""

from django.urls import re_path

from .consumers import HistoricConsumer

websocket_urlpatterns = [
    re_path(
        r"widgets/historic/(?P<bundle>\w{40}|\w{58})/$",
        HistoricConsumer.as_asgi(),
    ),
]
