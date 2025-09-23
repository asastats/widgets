"""Testing module for historic widget permissions module."""

import pytest

from inhouse.historic.permissions import can_access


class TestWidgetsHistoricPermissions:
    """Testing class for :py:mod:`inhouse.historic.permissions` functions`."""

    @pytest.mark.parametrize(
        "permission,size",
        [
            (3_236_067_977_900, 12),
            (3_236_067_977_500, 11),
            (500, 11),
            (258_885_438_800, 9),
            (258_885_438_200, 7),
            (500, 8),
            (23_299_689_999, 4),
            (23_299_689_500, 2),
            (23_299_689_438, 3),
            (23_299_689_437, 1),
            (500, 1),
        ],
    )
    def test_widgets_historic_permissions_can_access_functionality_for_false(
        self, permission, size, mocker
    ):
        profile = mocker.MagicMock()
        profile.permission = permission
        assert can_access(profile, size) is False

    @pytest.mark.parametrize(
        "permission,size",
        [
            (3_236_067_977_900, 10),
            (3_236_067_977_500, 9),
            (3_236_067_977_900, 4),
            (3_236_067_977_500, 1),
            (258_885_438_800, 5),
            (258_885_438_200, 4),
            (258_885_438_800, 1),
            (23_299_689_500, 1),
        ],
    )
    def test_widgets_historic_permissions_can_access_functionality_for_true(
        self, permission, size, mocker
    ):
        profile = mocker.MagicMock()
        profile.permission = permission
        assert can_access(profile, size) is True
