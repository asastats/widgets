"""Testing module for historic widget's assets module."""

import numpy as np
import pandas as pd
import pytest

from widgets.inhouse.historic.assets import (
    ElementsCreator,
    _base_program_name,
    _base_program_url,
    _create_asa_section,
    _create_nft_section,
    _create_noteval_section,
    _create_total,
    _group_asset_totals_into_sections,
    _group_nfts_by_collection,
    _process_sorted_ledger,
    _sorted_timestamp_data_and_totals_mapping,
    assets_data_from_timestamp_data,
)
from widgets.inhouse.historic.structs import BodyElement, HeaderElement, Total


class TestWidgetsHistoricAssetsElements:
    """Testing class for :py:mod:`widgets.inhouse.historic.assets` elements section."""

    # # ElementsCreator
    @pytest.mark.parametrize("attr", ["ledger_rows", "columns", "carrier"])
    def test_widgets_inhouse_historic_assets_elementscreator_inits_attribute_as_none(
        self, attr
    ):
        assert getattr(ElementsCreator, attr) is None

    # # __init__
    def test_widgets_inhouse_historic_assets_elementscreator_init_initializes_variables(
        self, mocker
    ):
        ledger_rows, columns, carrier = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        elements_creator = ElementsCreator(ledger_rows, columns, carrier)
        assert elements_creator.ledger_rows == ledger_rows
        assert elements_creator.columns == columns
        assert elements_creator.carrier == carrier

    # # _format_amount
    @pytest.mark.parametrize(
        "amount,decimals,result",
        [
            (26872283817, 6, "26,872.2838"),
            (355029, 0, "355,029"),
            (100000010, 4, "10,000.0010"),
            (300000, 5, "3"),
            (51402, 3, "51.402"),
            (300000000, 6, "300"),
            (62500, 2, "625"),
            (20145002578, 8, "201.4500"),
        ],
    )
    def test_widgets_inhouse_historic_assets_elementscreator_format_amount_functionality(
        self, amount, decimals, result, mocker
    ):
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        )
        asset_id = 505
        custom_asa = mocker.MagicMock()
        custom_asa.decimals = decimals
        elements_creator.carrier.asset_info.return_value = custom_asa
        assert elements_creator._format_amount(asset_id, amount) == result

    def test_widgets_inhouse_historic_assets_elementscreator_format_amount_for_error(
        self, mocker
    ):
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        )
        asset_id = 505
        elements_creator.carrier.asset_info.side_effect = TypeError("")
        assert elements_creator._format_amount(asset_id, 1) == ""

    # # _as_currency
    @pytest.mark.parametrize(
        "value,result",
        [
            (26872283817, 26872.283817),
            (355029, 0.355029),
            (10000004874, 10000.004874),
            (3000000, 3.0),
            (5140200, 5.1402),
            (300000000, 300.0),
        ],
    )
    def test_widgets_inhouse_historic_assets_elementscreator_format_currency_funct(
        self, value, result, mocker
    ):
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        )
        assert elements_creator._as_currency(value) == result

    # # _format_lp_token
    def test_widgets_inhouse_historic_assets_elementscreator_format_lp_token_nan(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), carrier
        )
        lp_token_id = pd.NA
        returned = elements_creator._format_lp_token(lp_token_id)
        assert returned is None

    def test_widgets_inhouse_historic_assets_elementscreator_format_lp_token_0(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), carrier
        )
        lp_token_id = 0
        returned = elements_creator._format_lp_token(lp_token_id)
        assert returned is None

    def test_widgets_inhouse_historic_assets_elementscreator_format_lp_token_funct(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), carrier
        )
        lp_token_id = 505
        asset1, asset2, provider, url = "asset1", "asset2", "Provider", "url"
        elements_creator.carrier.ledger_pool_info_for_lp_token.return_value = (
            asset1,
            asset2,
            0,
            provider,
            url,
        )
        asa1, asa2 = mocker.MagicMock(), mocker.MagicMock()
        asa1.unit = "unit1"
        asa2.unit = "unit2"
        mocked_asa = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator.custom_asa",
            side_effect=(asa1, asa2),
        )
        returned = elements_creator._format_lp_token(lp_token_id)
        assert returned == ("Provider LP unit1/unit2", url)
        elements_creator.carrier.ledger_pool_info_for_lp_token.assert_called_once_with(
            lp_token_id, capitalize_provider=True
        )
        calls = [mocker.call(asset1), mocker.call(asset2)]
        mocked_asa.assert_has_calls(calls, any_order=True)
        assert mocked_asa.call_count == 2

    # # _is_valid_asset_row
    @pytest.mark.parametrize(
        "ledger_row",
        [
            (505, 1, 2, 3, 4, 10000),
            (505, 1, 2, 3, 4, 0),
        ],
    )
    def test_widgets_inhouse_historic_assets_elementscreator__is_valid_asset_row_true(
        self, ledger_row, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        asset_id = 505
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        returned = elements_creator._is_valid_asset_row(asset_id, ledger_row)
        assert returned is True

    @pytest.mark.parametrize(
        "ledger_row",
        [
            (504, 1, 2, 3, 4, 10000),
            (505, 1, 2, 0, 4, 10000),
            (505, 1, 2, 3, 4, 1000),
        ],
    )
    def test_widgets_inhouse_historic_assets_elementscreator__is_valid_asset_row_false(
        self, ledger_row, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        asset_id = 505
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        returned = elements_creator._is_valid_asset_row(asset_id, ledger_row)
        assert returned is False

    # # _nft_amount_from_ledger_row
    def test_widgets_inhouse_historic_assets_elementscreator_nft_amount_for_decimals_0(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        carrier = mocker.MagicMock()
        elements_creator = ElementsCreator(mocker.MagicMock(), columns, carrier)
        nft_id, state = 505, 25
        ledger_row = (nft_id, "foo1", "foo2", state, "foo3", 1)
        asa = mocker.MagicMock()
        asa.decimals = 0
        carrier.asset_info.return_value = asa
        returned = elements_creator._nft_amount_from_ledger_row(ledger_row)
        assert returned == state

    def test_widgets_inhouse_historic_assets_elementscreator_nft_amount_for_decimals(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        carrier = mocker.MagicMock()
        elements_creator = ElementsCreator(mocker.MagicMock(), columns, carrier)
        nft_id, state = 505, 2518
        ledger_row = (nft_id, "foo1", "foo2", state, "foo3", 1)
        asa = mocker.MagicMock()
        asa.decimals = 2
        carrier.asset_info.return_value = asa
        returned = elements_creator._nft_amount_from_ledger_row(ledger_row)
        assert returned == 25.18

    # # _nft_item
    def test_widgets_inhouse_historic_assets_elementscreator_nft_item_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "code", "foo2", "state", "value")
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        nft_id, code, state, value = 505, "rga", 102405000, 25002020
        ledger_row = (nft_id, "foo1", code, "foo2", state, value)
        custom_nft1, custom_nft2, custom_nft3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        custom_nft2.id = nft_id
        custom_nfts = [custom_nft1, custom_nft2, custom_nft3]
        custom_asa = mocker.MagicMock()
        custom_asa.decimals = 6
        mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator.custom_asa",
            return_value=custom_asa,
        )
        returned = elements_creator._nft_item(ledger_row, custom_nfts)
        assert returned == BodyElement(
            asset=custom_nft2,
            name="Rand Gallery",
            type="Amount",
            url="https://www.randgallery.com",
            source=None,
            amount="102.4050",
            value=25.00202,
        )

    # # _program_item
    def test_widgets_inhouse_historic_assets_elementscreator_program_item_for_source(
        self, mocker
    ):
        columns = ("asset", "foo1", "code", "foo2", "state", "id", "value")
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        asset_id, code, state, _id, value = 505, "cmst", 102405000, 505050, 25000000
        ledger_row = (asset_id, "foo1", code, "foo2", state, _id, value)
        custom_asa = mocker.MagicMock()
        custom_asa.decimals = 6
        mocked_asa = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator.custom_asa",
            return_value=custom_asa,
        )
        token_name, token_url = "token", "token_url"
        mocked_token = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator._format_lp_token",
            return_value=(token_name, token_url),
        )
        returned = elements_creator._program_item(asset_id, ledger_row)
        assert returned == BodyElement(
            asset=None,
            name="Cometa stake",
            type=None,
            url="https://app.cometa.farm",
            source=(token_name, token_url),
            amount="102.4050",
            value=25.00,
        )
        mocked_asa.assert_called_once_with(asset_id)
        mocked_token.assert_called_once_with(_id)

    def test_widgets_inhouse_historic_assets_elementscreator_program_item_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "code", "foo2", "state", "id", "value")
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        asset_id, code, state, _id, value = 505, "cmst", 102405000, 505050, 25000000
        ledger_row = (asset_id, "foo1", code, "foo2", state, _id, value)
        custom_asa = mocker.MagicMock()
        custom_asa.decimals = 6
        mocked_asa = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator.custom_asa",
            return_value=custom_asa,
        )
        mocked_token = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator._format_lp_token",
            return_value=None,
        )
        returned = elements_creator._program_item(asset_id, ledger_row)
        assert returned == BodyElement(
            asset=None,
            name="Cometa stake",
            type="Staked",
            url="https://app.cometa.farm",
            source=None,
            amount="102.4050",
            value=25.00,
        )
        mocked_asa.assert_called_once_with(asset_id)
        mocked_token.assert_called_once_with(_id)

    # # _row_index
    def test_widgets_inhouse_historic_assets_elementscreator_row_index_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        elements_creator = ElementsCreator(
            mocker.MagicMock(), columns, mocker.MagicMock()
        )
        assert elements_creator._row_index("asset") == 0
        assert elements_creator._row_index("value") == 5

    # # asa_body
    def test_widgets_inhouse_historic_assets_elementscreator_asa_body_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        ledger_rows = [
            (502, 1, 2, 3, 4, 9000),
            (502, 1, 2, 3, 4, 20000),
            (502, 1, 2, 3, 4, 20000),
            (508, 1, 2, 3, 4, 7000),
            (508, 1, 2, 3, 4, 2000),
            (508, 1, 2, 0, 4, 0),
            (508, 1, 2, 3, 4, 0),
            (503, 1, 2, 3, 4, 40000),
            (501, 1, 2, 3, 4, 2000),
            (501, 1, 2, 3, 4, 10000),
            (508, 1, 2, 3, 4, -12200),
        ]
        elements_creator = ElementsCreator(ledger_rows, columns, mocker.MagicMock())
        program1, program2, program3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_program = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator._program_item",
            side_effect=(program1, program2, program3),
        )
        asset_id = 508
        returned = elements_creator.asa_body(asset_id)
        assert returned == [program1, program2, program3]
        calls = [
            mocker.call(asset_id, (508, 1, 2, 3, 4, 7000)),
            mocker.call(asset_id, (508, 1, 2, 3, 4, 0)),
            mocker.call(asset_id, (508, 1, 2, 3, 4, -12200)),
        ]
        mocked_program.assert_has_calls(calls, any_order=True)
        assert mocked_program.call_count == 3

    # # asa_header
    def test_widgets_inhouse_historic_assets_elementscreator_asa_header_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        ledger_rows = [
            (502, 1, 2, 1000, 4, 9000),
            (502, 1, 2, 2000, 4, 2000),
            (508, 1, 2, 3000, 4, 700),
            (502, 1, 2, 4000, 4, 200),
            (508, 1, 2, 5000, 4, 200),
            (503, 1, 2, 6000, 4, 400),
            (501, 1, 2, 7000, 4, 200),
            (501, 1, 2, 8000, 4, 100),
        ]
        elements_creator = ElementsCreator(ledger_rows, columns, mocker.MagicMock())
        asset_id = 502
        icon_path = mocker.MagicMock()
        elements_creator.carrier.asset_icon_path.return_value = icon_path
        custom_asa = mocker.MagicMock()
        custom_asa.unit = "unit"
        custom_asa.decimals = 2
        mocked_asa = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator.custom_asa",
            return_value=custom_asa,
        )
        total = 12789242804
        returned = elements_creator.asa_header(asset_id, total)
        assert returned == HeaderElement(
            icon=icon_path,
            label="unit",
            amount="10",
            total=12789.242804,
        )
        elements_creator.carrier.asset_icon_path.assert_called_once_with(asset_id)
        mocked_asa.assert_called_with(asset_id)

    # # custom_asa
    def test_widgets_inhouse_historic_assets_elementscreator_custom_asa_functionality(
        self, mocker
    ):
        elements_creator = ElementsCreator(
            mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        )
        asset_id = 505
        custom_asa = mocker.MagicMock()
        elements_creator.carrier.asset_info.return_value = custom_asa
        returned = elements_creator.custom_asa(asset_id)
        assert returned == custom_asa
        elements_creator.carrier.asset_info.assert_called_once_with(asset_id)

    # # nft_body
    def test_widgets_inhouse_historic_assets_elementscreator_nft_body_functionality(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        ledger_rows = [
            (502, 1, 2, 3, 4, 900),
            (502, 1, 2, 3, 4, 200),
            (502, 1, 2, 3, 4, 200),
            (508, 1, 2, 3, 4, 700),
            (508, 1, 2, 3, 4, 200),
            (503, 1, 2, 3, 4, 400),
            (501, 1, 2, 3, 4, 200),
            (501, 1, 2, 3, 4, 100),
        ]
        elements_creator = ElementsCreator(ledger_rows, columns, mocker.MagicMock())
        nft_item1, nft_item2, nft_item3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_item = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator._nft_item",
            side_effect=(nft_item1, nft_item2, nft_item3),
        )
        custom_nfts = mocker.MagicMock()
        nfts = {503, 508}
        returned = elements_creator.nft_body(custom_nfts, nfts)
        assert returned == [nft_item1, nft_item2, nft_item3]
        calls = [
            mocker.call((508, 1, 2, 3, 4, 700), custom_nfts),
            mocker.call((508, 1, 2, 3, 4, 200), custom_nfts),
            mocker.call((503, 1, 2, 3, 4, 400), custom_nfts),
        ]
        mocked_item.assert_has_calls(calls, any_order=True)
        assert mocked_item.call_count == 3

    # # nft_header
    def test_widgets_inhouse_historic_assets_elementscreator_nft_header_int_amount(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        ledger_rows = [
            (502, 1, 2, 1, 4, 900),
            (502, 1, 2, 2, 4, 200),
            (508, 1, 2, 3, 4, 700),
            (502, 1, 2, 4, 4, 200),
            (508, 1, 2, 5, 4, 200),
            (503, 1, 2, 6, 4, 400),
            (501, 1, 2, 7, 4, 200),
            (501, 1, 2, 8, 4, 100),
        ]
        carrier = mocker.MagicMock()
        asa1, asa2 = mocker.MagicMock(), mocker.MagicMock()
        asa1.decimals = 0
        asa2.decimals = 0
        carrier.asset_info.side_effect = [asa1, asa1, asa2, asa2]
        elements_creator = ElementsCreator(ledger_rows, columns, carrier)
        collection_name = "collection_name"
        nfts = [501, 508]
        total = 250321800
        returned = elements_creator.nft_header(collection_name, total, nfts)
        assert returned == HeaderElement(
            icon=None,
            label=collection_name,
            amount="23",
            total=250.3218,
        )

    def test_widgets_inhouse_historic_assets_elementscreator_nft_header_float_amount(
        self, mocker
    ):
        columns = ("asset", "foo1", "foo2", "state", "id", "value")
        ledger_rows = [
            (502, 1, 2, 1.1000, 4, 900),
            (502, 1, 2, 2.1247, 4, 200),
            (508, 1, 2, 4518, 4, 700),
            (502, 1, 2, 4.2525, 4, 200),
            (508, 1, 2, 5040, 4, 200),
            (503, 1, 2, 6, 4, 400),
            (501, 1, 2, 7, 4, 200),
            (501, 1, 2, 8, 4, 100),
        ]
        carrier = mocker.MagicMock()
        asa1, asa2 = mocker.MagicMock(), mocker.MagicMock()
        asa1.decimals = 0
        asa2.decimals = 2
        carrier.asset_info.side_effect = [asa1, asa1, asa2, asa1, asa2]
        elements_creator = ElementsCreator(ledger_rows, columns, carrier)
        collection_name = "collection_name"
        nfts = [502, 508]
        total = 250321800
        returned = elements_creator.nft_header(collection_name, total, nfts)
        assert returned == HeaderElement(
            icon=None,
            label=collection_name,
            amount="103.06",
            total=250.3218,
        )


class TestWidgetsHistoricAssetsHelpers:
    """Testing class for :py:mod:`widgets.inhouse.historic.assets` helpers functions."""

    # # _base_program_name
    @pytest.mark.parametrize(
        "url,result",
        [
            ("Alpha Arcade market", "Alpha Arcade market"),
            ("Defactor staking #P{0}", "Defactor staking"),
            ("Cometa farm", "Cometa farm"),
            ("Folks governance #{0}", "Folks governance"),
            ("Lofty {0} order", "Lofty order"),
            ("EXA Swap", "EXA Swap"),
            (None, ""),
            ("", ""),
        ],
    )
    def test_widgets_inhouse_historic_base_program_name_functionality(
        self, url, result
    ):
        assert _base_program_name(url) == result

    @pytest.mark.parametrize(
        "url,result",
        [
            ("https://domain.com/some/path/", "https://domain.com"),
            ("https://domain.com/some/path", "https://domain.com"),
            ("https://domain.com/path/", "https://domain.com"),
            ("https://domain.com/path", "https://domain.com"),
            ("https://domain.com/", "https://domain.com"),
            ("https://domain.com", "https://domain.com"),
            (None, ""),
            ("", ""),
        ],
    )
    def test_widgets_inhouse_historic_base_program_url_functionality(self, url, result):
        assert _base_program_url(url) == result

    # # _group_asset_totals_into_sections
    def test_widgets_inhouse_historic_assets_group_asset_totals_into_sections_funct(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5 = 505, 506, 507, 508, 509
        value1, value2, value3, value4, value5 = 100, 0, 300, 400, 0
        asset_totals = {
            asset_id1: value1,
            asset_id2: value2,
            asset_id3: value3,
            asset_id4: value4,
            asset_id5: value5,
        }
        assets, nfts = mocker.MagicMock(), mocker.MagicMock()
        carrier.filter_nfts_from_assets.return_value = (assets, nfts)
        returned = _group_asset_totals_into_sections(asset_totals, carrier)
        assert returned == (assets, nfts, {asset_id2: value2, asset_id5: value5})
        carrier.filter_nfts_from_assets.assert_called_once_with(
            {asset_id1: value1, asset_id3: value3, asset_id4: value4}
        )

    # # _group_nfts_by_collection
    def test_widgets_inhouse_historic_assets_group_nfts_by_collection_functionality(
        self, mocker
    ):
        carrier = mocker.MagicMock()
        asset_id1, asset_id2, asset_id3, asset_id4, asset_id5 = 505, 506, 507, 508, 509
        value1, value2, value3, value4, value5 = 500, 200, 400, 100, 300
        nft_totals = {
            asset_id1: value1,
            asset_id2: value2,
            asset_id3: value3,
            asset_id4: value4,
            asset_id5: value5,
        }
        custom_nft1, custom_nft2, custom_nft3, custom_nft4, custom_nft5 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        collection1, collection2, collection3 = (
            "collection1",
            "collection2",
            "collection3",
        )
        custom_nft1.collection = collection1
        custom_nft1.id = asset_id1
        custom_nft2.collection = collection2
        custom_nft2.id = asset_id2
        custom_nft3.collection = collection3
        custom_nft3.id = asset_id3
        custom_nft4.collection = collection1
        custom_nft4.id = asset_id4
        custom_nft5.collection = collection3
        custom_nft5.id = asset_id5
        nft_data = {
            asset_id1: custom_nft1,
            asset_id2: custom_nft2,
            asset_id3: custom_nft3,
            asset_id4: custom_nft4,
            asset_id5: custom_nft5,
        }
        carrier.nft_data_for_assets.return_value = nft_data
        returned = _group_nfts_by_collection(nft_totals, carrier)
        assert returned == (
            {
                collection3: [custom_nft3, custom_nft5],
                collection1: [custom_nft1, custom_nft4],
                collection2: [custom_nft2],
            },
            {
                collection1: [asset_id1, asset_id4],
                collection2: [asset_id2],
                collection3: [asset_id3, asset_id5],
            },
            {collection1: 600, collection2: 200, collection3: 700},
        )
        carrier.nft_data_for_assets.assert_called_once_with(nft_totals)

    # # _sorted_timestamp_data_and_totals_mapping
    def test_widgets_inhouse_historic_assets_sorted_timestamp_data_and_totals_mapping_f(
        self,
    ):
        data = {
            "asset": [
                np.int64(501),
                np.int64(508),
                np.int64(502),
                np.int64(508),
                np.int64(501),
                np.int64(503),
                np.int64(502),
                np.int64(502),
            ],
            "foo1": [1] * 8,
            "foo2": [2] * 8,
            "foo3": [3] * 8,
            "foo4": [4] * 8,
            "value": [100, 200, 200, 700, 200, 400, 900, 200],
        }
        timestamp_data = pd.DataFrame(data)
        returned = _sorted_timestamp_data_and_totals_mapping(timestamp_data)
        assert isinstance(returned, tuple)
        assert len(returned) == 2
        assert returned[0].values.tolist() == [
            [np.int64(502), 1, 2, 3, 4, 900],
            [np.int64(502), 1, 2, 3, 4, 200],
            [np.int64(502), 1, 2, 3, 4, 200],
            [np.int64(508), 1, 2, 3, 4, 700],
            [np.int64(508), 1, 2, 3, 4, 200],
            [np.int64(503), 1, 2, 3, 4, 400],
            [np.int64(501), 1, 2, 3, 4, 200],
            [np.int64(501), 1, 2, 3, 4, 100],
        ]
        assert returned[1] == {502: 1300, 508: 900, 503: 400, 501: 300}
        assert next(iter(returned[1])) == 502


class TestWidgetsHistoricAssetsProcess:
    """Testing class for :py:mod:`widgets.inhouse.historic.assets` process functions."""

    # # _create_asa_section
    def test_widgets_inhouse_historic_assets_create_asa_section_functionality(
        self, mocker
    ):
        elements_creator = mocker.MagicMock()
        asa_totals = {502: 1200, 503: 400, 501: 300}
        info1, info2, info3 = mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        header1, header2, header3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        body1, body2, body3 = mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        elements_creator.custom_asa.side_effect = (info1, info2, info3)
        elements_creator.asa_header.side_effect = (header1, header2, header3)
        elements_creator.asa_body.side_effect = (body1, body2, body3)
        returned = _create_asa_section(asa_totals, elements_creator)
        assert returned == [
            {"info": info1, "header": header1, "body": body1},
            {"info": info2, "header": header2, "body": body2},
            {"info": info3, "header": header3, "body": body3},
        ]
        calls = [
            mocker.call(502),
            mocker.call(503),
            mocker.call(501),
        ]
        elements_creator.custom_asa.assert_has_calls(calls, any_order=True)
        assert elements_creator.custom_asa.call_count == 3
        calls = [
            mocker.call(502, 1200),
            mocker.call(503, 400),
            mocker.call(501, 300),
        ]
        elements_creator.asa_header.assert_has_calls(calls, any_order=True)
        assert elements_creator.asa_header.call_count == 3
        calls = [
            mocker.call(502),
            mocker.call(503),
            mocker.call(501),
        ]
        elements_creator.asa_body.assert_has_calls(calls, any_order=True)
        assert elements_creator.asa_body.call_count == 3

    # # _create_nft_section
    def test_widgets_inhouse_historic_assets_create_nft_section_functionality(
        self, mocker
    ):
        nft_totals, elements_creator = mocker.MagicMock(), mocker.MagicMock()
        name1, name2, name3 = "collection_name1", "collection_name2", "collection_name3"
        custom_nfts1, custom_nfts2, custom_nfts3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        nft_collections = {
            name1: custom_nfts1,
            name2: custom_nfts2,
            name3: custom_nfts3,
        }
        nfts1, nfts2, nfts3 = mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        nft_collection_nfts = {name1: nfts1, name2: nfts2, name3: nfts3}
        total1, total2, total3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        nft_collection_totals = {name1: total1, name2: total2, name3: total3}
        mocked_group = mocker.patch(
            "widgets.inhouse.historic.assets._group_nfts_by_collection",
            return_value=(nft_collections, nft_collection_nfts, nft_collection_totals),
        )
        header1, header2, header3 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        body1, body2, body3 = mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
        elements_creator.nft_header.side_effect = (header1, header2, header3)
        elements_creator.nft_body.side_effect = (body1, body2, body3)
        returned = _create_nft_section(nft_totals, elements_creator)
        assert returned == [
            {"info": name1, "header": header1, "body": body1},
            {"info": name2, "header": header2, "body": body2},
            {"info": name3, "header": header3, "body": body3},
        ]
        mocked_group.assert_called_once_with(nft_totals, elements_creator.carrier)
        calls = [
            mocker.call(name1, total1, nfts1),
            mocker.call(name2, total2, nfts2),
            mocker.call(name3, total3, nfts3),
        ]
        elements_creator.nft_header.assert_has_calls(calls, any_order=True)
        assert elements_creator.nft_header.call_count == 3
        calls = [
            mocker.call(custom_nfts1, nfts1),
            mocker.call(custom_nfts2, nfts2),
            mocker.call(custom_nfts3, nfts3),
        ]
        elements_creator.nft_body.assert_has_calls(calls, any_order=True)
        assert elements_creator.nft_body.call_count == 3

    # # _create_noteval_section
    def test_widgets_inhouse_historic_assets_create_noteval_section_functionality(
        self, mocker
    ):
        elements_creator = mocker.MagicMock()
        asa_totals = {502: 0, 503: 0, 501: 0, 504: 0}
        info1, info2, info3, info4 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        info1.name = "name1"
        info2.name = ""
        info3.name = "name3"
        info4.name = "name4"
        body1, body2, body3, body4 = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            [],
            mocker.MagicMock(),
        )
        elements_creator.custom_asa.side_effect = (info1, info2, info3, info4)
        elements_creator.asa_body.side_effect = (body1, body2, body3, body4)
        returned = _create_noteval_section(asa_totals, elements_creator)
        assert returned == [
            {"info": info1, "body": body1},
            {"info": info4, "body": body4},
        ]
        calls = [mocker.call(502), mocker.call(503), mocker.call(501), mocker.call(504)]
        elements_creator.custom_asa.assert_has_calls(calls, any_order=True)
        assert elements_creator.custom_asa.call_count == 4
        calls = [mocker.call(502), mocker.call(503), mocker.call(501), mocker.call(504)]
        elements_creator.asa_body.assert_has_calls(calls, any_order=True)
        assert elements_creator.asa_body.call_count == 4

    # # _create_total
    def test_widgets_inhouse_historic_assets_create_total_for_no_algo(self):
        asa_totals = {502: 1_200_000_000, 503: 400_000_000, 501: 300_000_000}
        nft_totals = {504: 1_000_000_000, 505: 500_000_000}
        usd_price_in_algo = 2.5
        returned = _create_total(asa_totals, nft_totals, usd_price_in_algo)
        assert returned == Total(0, 1900, 1500, 3400, 1360, 2.5, 0.4)

    def test_widgets_inhouse_historic_assets_create_total_functionality(self):
        asa_totals = {
            502: 1_200_000_000,
            503: 400_000_000,
            501: 300_000_000,
            0: 15_000_000,
        }
        nft_totals = {504: 1_000_000_000, 505: 500_000_000}
        usd_price_in_algo = 5.0
        returned = _create_total(asa_totals, nft_totals, usd_price_in_algo)
        assert returned == Total(15, 1900, 1500, 3415, 683, 5, 0.2)

    # # _process_sorted_ledger
    def test_widgets_inhouse_historic_assets_process_sorted_ledger_functionality(
        self, mocker
    ):
        asset_totals, usd_price_in_algo, carrier = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        columns = ["asset", "foo1", "foo2", "foo3", "foo", "value"]
        sorted_ledger = pd.DataFrame(
            [
                [502, 1, 2, 3, 4, 900],
                [502, 1, 2, 3, 4, 200],
                [502, 1, 2, 3, 4, 200],
                [508, 1, 2, 3, 4, 700],
                [508, 1, 2, 3, 4, 200],
                [503, 1, 2, 3, 4, 400],
                [501, 1, 2, 3, 4, 200],
                [501, 1, 2, 3, 4, 100],
            ],
            columns=columns,
        )
        asa_totals, nft_totals, not_eval_totals = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_sections = mocker.patch(
            "widgets.inhouse.historic.assets._group_asset_totals_into_sections",
            return_value=(asa_totals, nft_totals, not_eval_totals),
        )
        elements_creator = mocker.MagicMock()
        mocked_creator = mocker.patch(
            "widgets.inhouse.historic.assets.ElementsCreator",
            return_value=elements_creator,
        )
        total, asa_section, nft_section, not_eval_section = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_total = mocker.patch(
            "widgets.inhouse.historic.assets._create_total",
            return_value=total,
        )
        mocked_asa = mocker.patch(
            "widgets.inhouse.historic.assets._create_asa_section",
            return_value=asa_section,
        )
        mocked_noteval = mocker.patch(
            "widgets.inhouse.historic.assets._create_noteval_section",
            return_value=not_eval_section,
        )
        mocked_nft = mocker.patch(
            "widgets.inhouse.historic.assets._create_nft_section",
            return_value=nft_section,
        )
        returned = _process_sorted_ledger(
            sorted_ledger, asset_totals, usd_price_in_algo, carrier
        )
        assert returned == {
            "total": total,
            "asa": asa_section,
            "nft": nft_section,
            "noteval": not_eval_section,
        }
        mocked_sections.assert_called_once_with(asset_totals, carrier)
        ledger_rows = [
            (502, 1, 2, 3, 4, 900),
            (502, 1, 2, 3, 4, 200),
            (502, 1, 2, 3, 4, 200),
            (508, 1, 2, 3, 4, 700),
            (508, 1, 2, 3, 4, 200),
            (503, 1, 2, 3, 4, 400),
            (501, 1, 2, 3, 4, 200),
            (501, 1, 2, 3, 4, 100),
        ]
        mocked_creator.assert_called_once_with(ledger_rows, columns, carrier)
        mocked_total.assert_called_once_with(asa_totals, nft_totals, usd_price_in_algo)
        mocked_asa.assert_called_once_with(asa_totals, elements_creator)
        mocked_nft.assert_called_once_with(nft_totals, elements_creator)
        mocked_noteval.assert_called_once_with(not_eval_totals, elements_creator)

    # # assets_data_from_timestamp_data
    def test_widgets_inhouse_historic_assets_assets_data_from_timestamp_data_funct(
        self, mocker
    ):
        timestamp, timestamp_data, carrier = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        sorted_ledger, asset_totals_mapping = mocker.MagicMock(), mocker.MagicMock()
        mocked_sorted = mocker.patch(
            "widgets.inhouse.historic.assets._sorted_timestamp_data_and_totals_mapping",
            return_value=(sorted_ledger, asset_totals_mapping),
        )
        usd_price_in_algo = mocker.MagicMock()
        carrier.usd_price_in_algo_for_timestamp.return_value = usd_price_in_algo
        mocked_process = mocker.patch(
            "widgets.inhouse.historic.assets._process_sorted_ledger"
        )
        returned = assets_data_from_timestamp_data(timestamp, timestamp_data, carrier)
        assert returned == mocked_process.return_value
        mocked_sorted.assert_called_once_with(timestamp_data)
        carrier.usd_price_in_algo_for_timestamp.assert_called_once_with(timestamp)
        mocked_process.assert_called_once_with(
            sorted_ledger, asset_totals_mapping, usd_price_in_algo, carrier
        )
