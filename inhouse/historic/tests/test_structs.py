"""Testing module for :py:mod:`widgets.inhouse.historic.structs` module."""

from widgets.inhouse.historic.structs import UpdateStatus, ViewStatus


class TestHistoricStructsViewStatus:
    """Testing class for :py:class:`...historic.structs.ViewStatus`."""

    def test_historic_structs_view_status_init_sets_bundle(self):
        assert ViewStatus("BUNDLE").bundle == "BUNDLE"

    def test_historic_structs_view_status_record_timestamps(self):
        view = ViewStatus("B")
        view.record_timestamps([1, 2, 3])
        assert view.timestamps == [1, 2, 3]

    def test_historic_structs_view_status_reset_current_range(self):
        view = ViewStatus("B")
        view.reset_current_range()
        assert view.current_range == (0, 15)

    def test_historic_structs_view_status_timestamp_for_x_absolute(self):
        assert ViewStatus("B").timestamp_for_x("2000") == 2000

    def test_historic_structs_view_status_timestamp_for_x_index(self):
        view = ViewStatus("B")
        view.record_timestamps([10, 20, 30])
        assert view.timestamp_for_x("1") == 20

    def test_historic_structs_view_status_x_axis_boundaries_zero(self):
        assert ViewStatus("B").x_axis_boundaries("0", "0") == (0, 1)

    def test_historic_structs_view_status_x_axis_boundaries_equal(self):
        assert ViewStatus("B").x_axis_boundaries("5", "5") == (4, 5)

    def test_historic_structs_view_status_x_axis_boundaries_range(self):
        assert ViewStatus("B").x_axis_boundaries("3", "8") == (3, 8)

    def test_historic_structs_view_status_is_range_changed(self):
        view = ViewStatus("B")
        view.current_range = (1, 2)
        assert view.is_range_changed(1, 2) is False
        assert view.is_range_changed(1, 3) is True

    def test_historic_structs_view_status_period_for_range_index(self):
        view = ViewStatus("B")
        view.record_timestamps([n * 100 for n in range(21)])
        view.reset_current_range()
        assert view.period_for_range(2, 5) == (200, 500)
        assert view.current_range == (2, 5)

    def test_historic_structs_view_status_period_for_range_absolute(self):
        view = ViewStatus("B")
        view.current_range = (2_000_000, 5_000_000)
        assert view.period_for_range(2_000_000, 2_500_000) == (2000, 2500)

    def test_historic_structs_view_status_period_for_range_zoom_out(self):
        view = ViewStatus("B")
        view.record_timestamps([n * 100 for n in range(21)])
        view.reset_current_range()
        returned = view.period_for_range(0, 20)
        assert returned == (int(2000 - 8 * 2000), int(2000 + 8 * 2000))
        assert view.current_range == (0, 20)


class TestHistoricStructsUpdateStatus:
    """Testing class for :py:class:`...historic.structs.UpdateStatus`."""

    def _status(self):
        return UpdateStatus({"bundle": "B", "addresses": "A1 A2"})

    def test_historic_structs_update_status_init(self):
        status = self._status()
        assert status.bundle == "B"
        assert status.addresses == ["A1", "A2"]
        assert set(status.initials) == {"A1", "A2", "B"}

    def test_historic_structs_update_status_check_phase_init_true(self):
        status = self._status()
        assert status.check_phase_init({"phase": 0, "address": "A1", "state": 7})
        assert status.initials["A1"] == 7

    def test_historic_structs_update_status_check_phase_init_false(self):
        assert self._status().check_phase_init({"phase": 3, "address": "A1"}) is False

    def test_historic_structs_update_status_evaluate_unknown_address(self):
        assert self._status().evaluate({"address": "X", "phase": 1}) == (None, None)

    def test_historic_structs_update_status_evaluate_finished_phase(self):
        status = self._status()
        phase, value = status.evaluate({"address": "A1", "phase": 4})
        assert (phase, value) == (1, 100)

    def test_historic_structs_update_status_template_context_initial(self):
        context = self._status().template_context()
        assert context["bundle"] == "B"
        assert context["statuses"] == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
