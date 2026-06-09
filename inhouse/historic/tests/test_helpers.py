"""Testing module for :py:mod:`widgets.inhouse.historic.helpers` module."""

from widgets.inhouse.historic.helpers import check_chart_period, group_name_from_bundle


class TestHistoricHelpersGroupNameFromBundle:
    """Testing class for :py:func:`...historic.helpers.group_name_from_bundle`."""

    def test_historic_helpers_group_name_from_bundle_functionality(self):
        assert group_name_from_bundle("ABC") == "historic_ABC"

    def test_historic_helpers_group_name_from_bundle_for_prefix(self):
        assert group_name_from_bundle("ABC", prefix="other") == "other_ABC"


class TestHistoricHelpersCheckChartPeriod:
    """Testing class for :py:func:`...historic.helpers.check_chart_period`."""

    def test_historic_helpers_check_chart_period_returns_wide_period(self):
        assert check_chart_period((0, 1000)) == (0, 1000)

    def test_historic_helpers_check_chart_period_clamps_narrow_period(self):
        returned = check_chart_period((100, 110))
        assert returned[0] == 100
        assert returned[1] == int(100 + 4 * 0.72 * 16)
