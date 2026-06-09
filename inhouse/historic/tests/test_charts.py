"""Testing module for historic widget's charts module."""

from widgets.inhouse.historic.charts import consolidated_view_charts_from_assets_data


class TestWidgetsHistoricCharts:
    """Testing class for :py:mod:`widgets.inhouse.historic.charts` functions."""

    # # consolidated_view_charts_from_assets_data
    def test_widgets_inhouse_historic_consolidated_view_charts_from_assets_data(
        self, mocker
    ):
        assets_data = mocker.MagicMock()
        asachart, nftchart, colors, nft_colors = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_base = mocker.patch(
            "widgets.inhouse.historic.charts.prepare_base_charts_from_assets_data",
            return_value=(asachart, nftchart, colors, nft_colors),
        )
        distchart, ratiochart, consolidated = (
            mocker.MagicMock(),
            mocker.MagicMock(),
            mocker.MagicMock(),
        )
        mocked_consolidated = mocker.patch(
            "widgets.inhouse.historic.charts.prepare_consolidated_charts_from_assets_data",
            return_value=(distchart, ratiochart, consolidated),
        )
        returned = consolidated_view_charts_from_assets_data(assets_data)
        assert returned == {
            "asachart": asachart,
            "nftchart": nftchart,
            "colors": colors,
            "nft_colors": nft_colors,
            "distchart": distchart,
            "ratiochart": ratiochart,
            "consolidated": consolidated,
        }
        mocked_base.assert_called_once_with(assets_data)
        mocked_consolidated.assert_called_once_with(assets_data)
