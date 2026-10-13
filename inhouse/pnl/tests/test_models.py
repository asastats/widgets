"""Testing module for :py:mod:`widgets.inhouse.pnl.models` module."""

from widgets.inhouse.pnl.models import PnlBundle


class TestPnlModelsPnlBundle:
    """Testing class for :py:class:`...pnl.models.PnlBundle`."""

    def test_pnl_models_pnl_bundle_str(self):
        assert str(PnlBundle(bundle="B" * 40, address_count=3)) == f"{'B' * 40} (3)"
