"""Module containing historic widget's data structures."""

from datetime import datetime, timezone

from .constants import BARS_COUNT, ProcessPhase


class UpdateStatus:
    """Class for calculation and presentation of update statuses in historic widget.

    :var UpdateStatus.bundle: unique hash identifier made from public Algorand addresses
    :type UpdateStatus.bundle: str
    :var UpdateStatus.addresses: space-separated collection of public Algorand addresses
    :type UpdateStatus.addresses: str
    :var UpdateStatus.timestamp: current timestamp
    :type UpdateStatus.timestamp: int
    :var UpdateStatus.initials: collection of all elements' initial states
    :type UpdateStatus.initials: dict
    :var UpdateStatus.states: collection of all elements' current states
    :type UpdateStatus.states: dict
    """

    bundle = None
    addresses = None
    timestamp = None
    initials = {}
    states = {}

    def __init__(self, message):
        """Set class variables to initial values based on provided `message° object.

        :param message: procesing message data instance
        :type message: dict
        """
        self.bundle = message.get("bundle")
        self.addresses = message.get("addresses").split(" ")
        self.timestamp = int(datetime.now(timezone.utc).timestamp())

        self.reset_states()

    # RESET
    def reset_states(self):
        """Set `initials` and `states` class variables to initial values."""
        collection = [*self.addresses, self.bundle]
        self.initials = {key: 0 for key in collection}
        self.states = {key: [None, 0, 0, 0] for key in collection}

    # HELPERS
    def _calculate_phase_value(self, state, initial, end_state):
        """Calculate and return element's progress percentage based on provided arguments.

        :param state: current state
        :type state: int
        :param initial: starting/initial state
        :type initial: int
        :param end_state: final/maximum state
        :type end_state: int
        :return: int
        """
        value = (state - initial) / (end_state - initial) if end_state - initial else 0
        return int(value * 100)

    def _is_finished_phase(self, phase):
        """Retun phase's integer representation if provided `phase` represents an ended state.

        :param phase: phase identifier
        :type phase: int
        :return: int
        """
        if phase == int(ProcessPhase.FETCHED):
            return int(ProcessPhase.FETCH)

        elif phase == int(ProcessPhase.CHECKED):
            return int(ProcessPhase.CHECK)

        elif phase == int(ProcessPhase.PROCESSED):
            return int(ProcessPhase.PROCESS)

        return False

    def _statuses_from_events(self, collection, events):
        """Return UI segment's statuses for `collection` parsed from provided `events`.

        :param collection: collection of bundle addresses and bundle itself
        :type collection: list
        :param events: collection of bundle's phases and processing statuses
        :type events: dict
        :return: list
        """
        statuses = []
        for address in collection:
            current = []
            for phase in range(1, 4):
                if events.get(address, {}).get(phase + 3) is not None:
                    current.append(100)
                    continue

                phase_item = events.get(address, {}).get(phase, {})
                if phase_item:
                    initial = events.get(address).get(0, {}).get("state", 0)
                    end_state = phase_item.get("end") or self.timestamp
                    current.append(
                        self._calculate_phase_value(
                            phase_item.get("state"), initial, end_state
                        )
                    )

                else:
                    current.append(0)

            statuses.append(current)

        return statuses

    # PUBLIC
    def check_phase_init(self, message):
        """Set initial phase for message's address to message's state if phase is init.

        :param message: procesing message data instance
        :type message: dict
        :return: Boolean
        """
        if message["phase"] == int(ProcessPhase.INIT):
            self.initials[message["address"]] = message["state"]
            return True

        return False

    def evaluate(self, message):
        """Calculate and set message's phase value.

        :param message: procesing message data instance
        :type message: dict
        :var address: element's address or bundle
        :type address: str
        :var phase: element's phase identifier
        :type phase: int
        :var value: element's progress percentage/value
        :type value: int
        :return: two-tuple
        """
        address = message["address"]

        if address not in self.initials:
            return None, None

        phase = self._is_finished_phase(message["phase"])
        if phase:
            value = 100

        else:
            phase = int(message["phase"])
            value = max(
                self._calculate_phase_value(
                    message["state"],
                    self.initials[address],
                    message.get("end") or self.timestamp,
                ),
                self.states[address][phase],
            )

        self.states[address][phase] = value

        return phase, value

    def template_context(self, events=None):
        """Return initial UI segment's template context values.

        :param events: collection of bundle's phases and processing statuses
        :type events: dict
        :var collection: collection of bundle addresses and bundle itself
        :type collection: list
        :return: dict
        """
        collection = [*self.addresses, self.bundle]
        return {
            "bundle": self.bundle,
            "addresses": collection,
            "labels": ["Fetch", "Analysis", "Process"],
            "statuses": (
                [[0, 0, 0] for _ in collection]
                if events is None
                else self._statuses_from_events(collection, events)
            ),
        }


class ViewStatus:
    """Class for keeping chart x-axis range state and calculating zoom periods.

    The evaluated asset values and the storage carrier live engine-side now; this
    class keeps only the range/zoom math driven by the browser's x-axis values.

    :var ViewStatus.bundle: unique hash identifier made from public Algorand addresses
    :type ViewStatus.bundle: str
    :var ViewStatus.timestamps: collection of timestamps to reuse on zoom-out
    :type ViewStatus.timestamps: list
    :var ViewStatus.current_range: currently processed view's x-axis min and max
    :type ViewStatus.current_range: two-tuple
    """

    bundle = None
    timestamps = []
    current_range = None

    def __init__(self, bundle):
        """Set class variables to initial values based on provided argument.

        :param bundle: unique hash identifier made from public Algorand addresses
        :type bundle: str
        """
        self.bundle = bundle

    def _is_zoom_out(self, x_min, x_max):
        """Return True if provided x-axis boundaries is zoom-out from previous state.

        :param x_min: sender's chart x-axis minimum value
        :type x_min: int
        :param x_max: sender's chart x-axis maximum value
        :type x_max: int
        :return: Boolean
        """
        if x_min > 1000:
            return (
                self.current_range[1] - self.current_range[0] < x_max - x_min
                if self.current_range[0] > 1000
                else (
                    self.timestamps[self.current_range[1]]
                    - self.timestamps[self.current_range[0]]
                )
                < (x_max - x_min) / 1000
            )

        return x_max - x_min > BARS_COUNT

    def _zoom_out_period_for_range(self, x_min, x_max):
        """Set provided boundaries as central x-axis points and return extended period.

        :param x_min: sender's chart x-axis minimum value
        :type x_min: int
        :param x_max: sender's chart x-axis maximum value
        :type x_max: int
        :var start_time: sender's chart x-axis minimum timestamp
        :type start_time: int
        :var end_time: sender's chart x-axis maximum timestamp
        :type end_time: int
        :var interval: duration in seconds between two adjacted x-axis points
        :type interval: int
        :var central_time: bar chart's center timestamp
        :type central_time: int
        :return: two-tuple
        """
        start_time, end_time = (
            (int(x_min / 1000), int(x_max / 1000))
            if x_min > 1000
            else (self.timestamps[x_min], self.timestamps[x_max])
        )
        interval = end_time - start_time
        central_time = (
            start_time
            if start_time - self.timestamps[0] < self.timestamps[-1] - end_time
            else end_time
        )
        return (
            int(central_time - BARS_COUNT / 2 * interval),
            int(central_time + BARS_COUNT / 2 * interval),
        )

    def is_range_changed(self, x_min, x_max):
        """Return True if provided range boundaries represent a new period.

        :param x_min: sender's chart x-axis minimum value
        :type x_min: int
        :param x_max: sender's chart x-axis maximum value
        :type x_max: int
        :return: Boolean
        """
        return self.current_range != (x_min, x_max)

    def period_for_range(self, x_min, x_max):
        """Set current range from proviuded boundaries and return related period.

        :param x_min: sender's chart x-axis minimum value
        :type x_min: int
        :param x_max: sender's chart x-axis maximum value
        :type x_max: int
        :return: two-tuple
        """
        if self._is_zoom_out(x_min, x_max):
            self.current_range = (x_min, x_max)
            return self._zoom_out_period_for_range(x_min, x_max)

        self.current_range = (x_min, x_max)

        if x_min > 1000:
            return (int(float(x_min) / 1000), int(float(x_max) / 1000))

        return (self.timestamps[x_min], self.timestamps[x_max])

    def record_timestamps(self, timestamps):
        """Save provided timestamps collection to class variable.

        :param timestamps: chart's timestamps
        :type timestamps: list
        """
        self.timestamps = timestamps

    def reset_current_range(self):
        """Set current range class variable to initial value."""
        self.current_range = (0, BARS_COUNT - 1)

    def timestamp_for_x(self, x_val):
        """Return timestamp for provided chart's value on x-axis.

        :param x_val: sender's chart x-axis value
        :type x_val: str
        :return: int
        """
        if float(x_val) > 1000:
            return int(float(x_val))

        return self.timestamps[int(x_val)]

    def x_axis_boundaries(self, x_min, x_max):
        """Convert provided range boundaries to either chart indices or timestamps.

        :param x_min: sender's chart x-axis minimum value
        :type x_min: str
        :param x_max: sender's chart x-axis maximum value
        :type x_max: str
        :param _x_min: sender's chart x-axis minimum value as number
        :type _x_min: int
        :param _x_max: sender's chart x-axis maximum value as number
        :type _x_max: int
        :return: two-tuple
        """
        _x_min, _x_max = int(float(x_min)), int(float(x_max))
        if _x_min < 1000 and _x_min == _x_max:
            _x_min, _x_max = (0, 1) if _x_min == 0 else (_x_max - 1, _x_max)

        return (_x_min, _x_max)
