"""Module containing historic widget's constants."""

from enum import IntEnum


class ProcessPhase(IntEnum):
    INIT = 0
    FETCH = 1
    CHECK = 2
    PROCESS = 3
    FETCHED = 4
    CHECKED = 5
    PROCESSED = 6


MICROALGOS_TO_ALGOS_RATIO = 1000000

STORAGE_LEDGER_EXPANSION_MULTIPLIER = 2

DISTINCT_COLORS = (
    "#e6194B",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#42d4f4",
    "#f032e6",
    "#fabed4",
    "#469990",
    "#dcbeff",
    "#9A6324",
    "#fffac8",
    "#800000",
    "#aaffc3",
    "#000075",
    "#a9a9a9",
    "#ffffff",
    "#000000",
)

BARS_COUNT = 16
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
