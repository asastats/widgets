"""ASA Stats user widgets websocket routes configuration module."""

import importlib

from .constants import INHOUSE_WIDGETS, THIRDPARTY_WIDGETS

websocket_urlpatterns = [
    urlpattern
    for widget in INHOUSE_WIDGETS
    if importlib.util.find_spec(f"widgets.inhouse.{widget}.routing") is not None
    for urlpattern in getattr(
        importlib.import_module(f"widgets.inhouse.{widget}.routing"),
        "websocket_urlpatterns",
    )
] + [
    urlpattern
    for widget in THIRDPARTY_WIDGETS
    if importlib.util.find_spec(f"widgets.thirdparty.{widget}.routing") is not None
    for urlpattern in getattr(
        importlib.import_module(f"widgets.thirdparty.{widget}.routing"),
        "websocket_urlpatterns",
    )
]
