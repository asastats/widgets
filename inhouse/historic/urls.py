"""Module containing historic data widget's URL configurations."""

from django.urls import re_path

from .views import HistoricView, HistoricResetView

urlpatterns = [
    re_path(r"^(\w{40}|\w{58})$", HistoricView.as_view(), name="historic"),
    re_path(r"^(\w{40})/reset$", HistoricResetView.as_view(), name="historic_reset"),
]
