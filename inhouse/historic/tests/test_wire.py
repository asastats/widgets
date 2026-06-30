"""Testing module for :py:mod:`widgets.inhouse.historic.wire`."""

import json
from pathlib import Path

from widgets.inhouse.historic.wire import deserialize_assets_data

FIXTURE = Path(__file__).parent / "fixtures" / "assets_data_wire.json"


class TestInhouseHistoricWireDeserializeAssetsData:
    """Testing class for the historic assets-data rehydrate seam."""

    def _payload(self):
        return json.loads(FIXTURE.read_text())

    def test_inhouse_historic_wire_asa_header_is_rebuilt(self):
        first = deserialize_assets_data(self._payload())["asa"][0]
        assert first["header"].total == 16.529823
        assert first["header"].label == "ASASTATS"

    def test_inhouse_historic_wire_asa_info_is_rebuilt(self):
        first = deserialize_assets_data(self._payload())["asa"][0]
        assert first["info"].unit == "ASASTATS"
        assert first["info"].id == 393537671

    def test_inhouse_historic_wire_total_tolerates_missing_noteval(self):
        total = deserialize_assets_data(self._payload())["total"]
        assert total.total == 23.33
        assert total.noteval is None  # engine omits it; default fills None
