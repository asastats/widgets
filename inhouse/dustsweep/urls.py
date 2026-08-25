"""Module containing Dust Sweep widget's URL configurations."""

from django.urls import re_path

from .views import DustSweepPlanView, DustSweepView

urlpatterns = [
    # The one JSON endpoint. Must come before the address/bundle pattern below,
    # which would otherwise swallow it.
    re_path(r"^plan$", DustSweepPlanView.as_view(), name="dustsweep_plan"),
    # Sweep shell for an address or bundle page.
    re_path(r"^(\w{40}|\w{58})$", DustSweepView.as_view(), name="dustsweep"),
]
