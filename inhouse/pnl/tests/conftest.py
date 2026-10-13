"""Keep P&L tests that create price alerts off the Redis the engine reads."""

from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _population_writes_nowhere(mocker):
    mocker.patch(
        "widgets.inhouse.alerts.population.redis_instance",
        return_value=mock.MagicMock(),
    )
