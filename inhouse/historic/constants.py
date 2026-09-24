"""Module containing historic widget's constants."""

from enum import IntEnum

#: How many bars a progress readout draws.
BARS_COUNT = 16


class ProcessPhase(IntEnum):
    """Processing phases reported by the engine over the progress bus."""

    INIT = 0
    FETCH = 1
    CHECK = 2
    PROCESS = 3
    FETCHED = 4
    CHECKED = 5
    PROCESSED = 6
