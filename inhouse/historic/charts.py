"""Historic widget consolidated-view charts built from engine assets data.

The engine returns the interpreted assets_data dict; this builds the
consolidated view charts from it using the host's shared chart helpers, so
no proprietary interpretation lives here.
"""

from utils.charts import (
    prepare_base_charts_from_assets_data,
    prepare_consolidated_charts_from_assets_data,
)


def consolidated_view_charts_from_assets_data(assets_data):
    """Create consolidated view's charts from provided `assets_data` collection.

    :param assets_data: processed asset section data ready for rendering
    :type assets_data: dict
    :var asachart: data for ASA chart rendering
    :type asachart: dict
    :var nftchart: data for NFT chart rendering
    :type nftchart: dict
    :var colors: collection of asset ids and related colors
    :type colors: dict
    :var nft_colors: collection of NFT ids and related colors
    :type nft_colors: dict
    :var distchart: data for rendering top ASA distribution chart
    :type distchart: dict
    :var ratiochart: data for rendering ALGO/ASA/NFT chart
    :type ratiochart: dict
    :var nftfloorchart: data for rendering NFT floors chart
    :type nftfloorchart: dict
    :var consolidated: consolidated view totals
    :type consolidated: :class:`utils.structs.Consolidated`
    :return: dict
    """
    asachart, nftchart, colors, nft_colors = prepare_base_charts_from_assets_data(
        assets_data
    )
    distchart, ratiochart, consolidated = prepare_consolidated_charts_from_assets_data(
        assets_data
    )
    return {
        "asachart": asachart,
        "nftchart": nftchart,
        "colors": colors,
        "nft_colors": nft_colors,
        "distchart": distchart,
        "ratiochart": ratiochart,
        "consolidated": consolidated,
    }
