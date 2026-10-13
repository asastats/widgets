"""Module containing the profit and loss widget's URL configurations."""

from django.urls import re_path

from .views import (
    PnlAlertView,
    PnlAssetView,
    PnlProcessView,
    PnlRemoveView,
    PnlStatusView,
    PnlView,
)

PATH = r"(\w{40}|\w{58})"

urlpatterns = [
    re_path(rf"^{PATH}$", PnlView.as_view(), name="pnl"),
    re_path(rf"^{PATH}/status$", PnlStatusView.as_view(), name="pnl_status"),
    re_path(rf"^{PATH}/process$", PnlProcessView.as_view(), name="pnl_process"),
    re_path(rf"^{PATH}/remove$", PnlRemoveView.as_view(), name="pnl_remove"),
    re_path(rf"^{PATH}/asset/(\w+)$", PnlAssetView.as_view(), name="pnl_asset"),
    re_path(rf"^{PATH}/alert/(\d+)$", PnlAlertView.as_view(), name="pnl_alert"),
]
