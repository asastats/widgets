"""Module containing Folks smart router widget's URL configurations."""

from django.urls import re_path

from .views import FolksSwapView

urlpatterns = [
    # Same address-or-bundle pattern as historic. Page context may be a bundle;
    # an executable swap is gated to the single linked + active address.
    re_path(r"^(\w{40}|\w{58})$", FolksSwapView.as_view(), name="folks"),
]
