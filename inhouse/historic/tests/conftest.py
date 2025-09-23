"""Configuration module for historic widget unit tests package."""

import sys
import types
from collections import namedtuple

import django
from django.conf import settings

AsaProgram = namedtuple(
    "AsaProgram",
    ["type", "name", "provider", "url", "code"],
    defaults=[None, None, None, None, None],
)
Provider = namedtuple("Provider", ["name", "info"], defaults=["Unknown", None])

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
        ],
        AUTH_USER_MODEL="auth.User",  # default user model
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
    )

django.setup()


def make_fake_module(name, attrs=None, is_package=True):
    mod = types.ModuleType(name)
    if is_package:
        mod.__path__ = []  # make it a package
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Create all fake modules and attributes your submodule imports
make_fake_module(
    "api.data",
    attrs={
        "ASA_PROGRAMS": {
            "ba": AsaProgram(type="Balance"),
            "cmst": AsaProgram(
                type="Staked",
                name="Cometa stake",
                provider=Provider("Cometa"),
                url="https://app.cometa.farm/stake",
            ),
            "rga": AsaProgram(
                type="Amount",
                name="Rand Gallery",
                provider=Provider("RandGallery"),
                url="https://www.randgallery.com",
            ),
        },
    },
)
make_fake_module(
    "api.widgets", attrs={"bundle_and_addresses_from_path": lambda *a, **kw: None}
)
make_fake_module(
    "utils.charts",
    attrs={
        "prepare_base_charts_from_assets_data": lambda *a, **kw: None,
        "prepare_consolidated_charts_from_assets_data": lambda *a, **kw: None,
    },
)
make_fake_module("utils.constants.charts", attrs={"DISTINCT_COLORS": []})
make_fake_module(
    "utils.constants.storage",
    attrs={"STORAGE_LEDGER_EXPANSION_MULTIPLIER": 1},
)
make_fake_module(
    "storage.helpers",
    attrs={
        "check_chart_period": lambda *a, **kw: None,
        "group_name_from_bundle": lambda *a, **kw: None,
        "load_bundle_event_records": lambda *a, **kw: None,
    },
)
make_fake_module(
    "storage.main",
    attrs={
        "initialize_storage_carrier": lambda *a, **kw: None,
        "reset_bundle_historic_data": lambda *a, **kw: None,
        "retrieve_bundle_historic_data": lambda *a, **kw: None,
    },
)
make_fake_module(
    "storage.ledger",
    attrs={
        "evaluate_bundle_ledger_data_for_period": lambda *a, **kw: None,
        "evaluate_bundle_ledger_data_for_timestamp": lambda *a, **kw: None,
        "reset_bundle_historic_data": lambda *a, **kw: None,
    },
)
