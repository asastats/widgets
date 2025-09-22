"""Module containing historic widget's constants."""

from django.conf import settings

from utils.constants.charts import DISTINCT_COLORS
from utils.constants.storage import STORAGE_LEDGER_EXPANSION_MULTIPLIER

BARS_COUNT = settings.HISTORIC_WIDGET_BARS_COUNT
TOTAL_NUMBER_OF_CANDLES_IN_CHART = 48

MAX_NUMBER_OF_ASSETS_IN_CHART = 15
GROUPS_IN_ASSET_TAGS = ("LOFTY", "NFT")
OTHERS_GROUP_NAME = "others"
DATE_FORMATS_FOR_TIMESTAMPS_INTERVAL = {
    3942000: "%b %Y",
    1478250: "%-m/%-d/%Y",
    108000: "%-m/%-d/%y %H:00",
    5400: "%-m/%-d/%y %H:%M",
    0: "%-m/%-d %H:%M:%S",
}

DUST_LIMIT = 5000  # microAlgos