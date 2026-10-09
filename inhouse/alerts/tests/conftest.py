"""Keep the alert unit tests off the Redis the engine reads.

Saving a rule publishes it to `lvr`, the set the engine's live pass fetches
every block. Without this, a test that saves a rule against a placeholder
address writes that placeholder into the engine's watch set, where it fails on
every block until someone removes it by hand. The integration suite is not
affected: it uses the real set on purpose and does not load this file.
"""

from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _population_writes_nowhere(mocker):
    mocker.patch(
        "widgets.inhouse.alerts.population.redis_instance",
        return_value=mock.MagicMock(),
    )
