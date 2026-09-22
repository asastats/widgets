"""Configuration module for historic widget unit tests package."""

import importlib
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

# **Standalone-mode bootstrap, and unreachable from this suite by
# construction.** Run through the frontend - which is how the widget suite runs
# here and in CI - settings are already configured, so the body never executes
# and cannot be covered without running the widgets repo on its own. It is kept
# because the repo ships separately and needs to stand up without the host.
if not settings.configured:  # pragma: no cover
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
    """Stand `name` up as a stub module, unless the host really provides it.

    **The guard is the whole point, and it was missing.** These stubs exist for
    the standalone widgets repo, where there is no host to import from - the
    same reason as the `settings.configured` check above. Installed
    unconditionally they also replace the *real* modules when the suite runs
    inside the frontend, and `sys.modules` is process-wide: every later test in
    that run sees the stub.

    The failure that produced this is worth recording, because nothing about it
    points here. A stub has no `__file__`, so an import of a name it does not
    carry fails with ``cannot import name … (unknown location)`` - and
    `utils.charts` and `utils.constants.charts` are both pulled in by
    `core/views.py` and `core_extras`, which is to say by *any* test in any
    widget that reverses a URL or renders a template. Those tests pass alone and
    fail in a whole-suite run, with an ImportError naming a module the widget
    under test never heard of.

    Import rather than `find_spec`: a host module may exist and still not load,
    and a stub is the right answer in both cases.

    :param name: the dotted module path to provide
    :type name: str
    :param attrs: what the stub should carry
    :type attrs: dict
    :param is_package: whether submodules may be imported from it
    :type is_package: bool
    :return: the real module when the host has one, else the stub
    """
    try:
        return importlib.import_module(name)
    except ImportError:
        pass

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
