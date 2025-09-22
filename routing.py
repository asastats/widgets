"""ASA Stats user widgets websocket routes configuration module."""

import importlib

from django.conf import settings

websocket_urlpatterns = [
    urlpattern
    for widget in settings.INHOUSE_WIDGETS
    if importlib.util.find_spec(f"widgets.inhouse.{widget}.routing") is not None
    for urlpattern in getattr(
        importlib.import_module(f"widgets.inhouse.{widget}.routing"),
        "websocket_urlpatterns",
    )
] + [
    urlpattern
    for widget in settings.THIRDPARTY_WIDGETS
    if importlib.util.find_spec(f"widgets.thirdparty.{widget}.routing") is not None
    for urlpattern in getattr(
        importlib.import_module(f"widgets.thirdparty.{widget}.routing"),
        "websocket_urlpatterns",
    )
]
