"""Testing module for :mod:`widgets.inhouse.liverefresh.warmset`.

**Against a real Redis, not a mock.** Every other test in this widget hands the
view a `MagicMock` client, which is right there because the client is a
collaborator. Here the sorted-set semantics *are* the logic under test - scored
ranges, rank-ordered eviction, what `zremrangebyscore` counts as stale - so a
stub would agree with whatever this module happens to do, which is precisely the
trap that produced a passing suite over a buggy `_program_entries` once already.

Keys are namespaced per run and deleted afterwards, and the whole module skips
when no Redis answers, so a checkout without one is not a failure.
"""

import uuid

import pytest

from widgets.inhouse.liverefresh import warmset

ADDR_A = "A" * 58
ADDR_B = "B" * 58
ADDR_C = "C" * 58
ADDR_D = "D" * 58
ADDR_E = "E" * 58

NOW = 1_700_000_000.0

#: The manifest's own shape, so a change to the real bands shows up here.
BANDS = [
    {"max_addresses": 1, "permission": 0},
    {"max_addresses": 1, "permission": 23299689438},
    {"max_addresses": 5, "permission": 258885438200},
    {"max_addresses": 20, "permission": 3236067977500},
]


@pytest.fixture
def client():
    """Return a real Redis client, skipping the test when none answers."""
    from utils.clients import redis_instance

    try:
        instance = redis_instance()
        instance.ping()
    except Exception as error:  # noqa: BLE001 - any failure is "no Redis here"
        pytest.skip(f"no Redis to test against: {error}")
    yield instance


@pytest.fixture
def reader(client):
    """Return a user pk nothing else is using, and clean up after the test.

    A pk rather than a key, because `warmset` owns the key shape and a test
    that built the key itself would stop noticing if that shape changed.
    """
    pk = f"test-{uuid.uuid4().hex}"
    yield pk
    client.delete(warmset.key_for(pk))


@pytest.fixture
def other(client):
    """Return a second isolated reader, for the separation test."""
    pk = f"test-{uuid.uuid4().hex}"
    yield pk
    client.delete(warmset.key_for(pk))


class TestCapFor:
    """Testing class for :func:`warmset.cap_for`."""

    @pytest.mark.parametrize(
        "permission,expected",
        [
            (0, 1),
            (23299689438, 1),
            (258885438200, 5),
            (3236067977500, 20),
            (3236067977500 * 2, 20),
        ],
    )
    def test_cap_for_returns_widest_band_the_reader_clears(self, permission, expected):
        """The cap is the reverse of the manifest's own question."""
        assert warmset.cap_for(permission, BANDS) == expected

    def test_cap_for_returns_none_for_an_unbanded_manifest(self):
        """A plain integer permission is not banded and has no cap."""
        assert warmset.cap_for(0, 0) is None

    def test_cap_for_returns_zero_when_no_band_is_cleared(self):
        """A reader below every band keeps nothing warm."""
        assert warmset.cap_for(-1, [{"max_addresses": 5, "permission": 10}]) == 0


class TestTouch:
    """Testing class for :func:`warmset.touch`."""

    def test_touch_admits_within_the_cap(self, client, reader):
        """The ordinary case: room for everything asked for."""
        admitted, evicted = warmset.touch(reader, [ADDR_A, ADDR_B], 5, client, NOW)

        assert sorted(admitted) == sorted([ADDR_A, ADDR_B])
        assert evicted == []
        assert warmset.count(reader, client, NOW) == 2

    def test_touch_counts_the_union_and_not_the_sum(self, client, reader):
        """**The reason members are addresses rather than pages.**

        A reader watching `{A, B, C}` in a browser whose API call asks for
        `{C, D}` costs four, not five. Billing 3 + 2 would charge twice for the
        address they are most likely to ask about on both surfaces.
        """
        warmset.touch(reader, [ADDR_A, ADDR_B, ADDR_C], 5, client, NOW)
        warmset.touch(reader, [ADDR_C, ADDR_D], 5, client, NOW + 1)

        assert warmset.count(reader, client, NOW + 1) == 4

    def test_touch_evicts_an_idle_address_to_make_room(self, client, reader):
        """A tab the reader has stopped polling gives up its slot."""
        warmset.touch(reader, [ADDR_A], 2, client, NOW)
        warmset.touch(reader, [ADDR_B], 2, client, NOW + 1)

        later = NOW + warmset.IDLE_SECONDS + 1
        admitted, evicted = warmset.touch(reader, [ADDR_C], 2, client, later)

        assert admitted == [ADDR_C]
        assert evicted == [ADDR_A]
        assert sorted(warmset.members(reader, client, later)) == sorted([ADDR_B, ADDR_C])

    def test_touch_does_not_evict_a_tab_that_is_still_polling(self, client, reader):
        """**The ping-pong this design was nearly shipped with.**

        An evicted tab is never told it was evicted: it polls again three
        seconds later, re-claims the budget and evicts the other in turn. Two
        tabs over the cap would alternate for ever, each updating at half rate,
        and the cap would bound nothing. So a page still being polled keeps
        what it holds and the newcomer goes static instead.
        """
        warmset.touch(reader, [ADDR_A], 1, client, NOW)

        admitted, evicted = warmset.touch(reader, [ADDR_B], 1, client, NOW + 1)

        assert admitted == []
        assert evicted == []
        assert warmset.members(reader, client, NOW + 1) == [ADDR_A]

    def test_touch_is_stable_when_two_tabs_contend(self, client, reader):
        """Repeated polls from both must not swap the winner back and forth."""
        warmset.touch(reader, [ADDR_A], 1, client, NOW)

        for step in range(1, 8):
            warmset.touch(reader, [ADDR_B], 1, client, NOW + step)
            warmset.touch(reader, [ADDR_A], 1, client, NOW + step)

        assert warmset.members(reader, client, NOW + 8) == [ADDR_A]

    def test_touch_refuses_whole_rather_than_partially(self, client, reader):
        """A refused API call must not admit half a bundle.

        Admitting the ones that happen to fit would leave the caller holding an
        answer about addresses it did not ask about on their own.
        """
        warmset.touch(reader, [ADDR_A, ADDR_B], 3, client, NOW)

        admitted, evicted = warmset.touch(
            reader, [ADDR_C, ADDR_D, ADDR_E], 3, client, NOW + 1, evict=False
        )

        assert admitted == []
        assert evicted == []
        assert sorted(warmset.members(reader, client, NOW + 1)) == sorted(
            [ADDR_A, ADDR_B]
        )

    def test_touch_without_eviction_admits_what_fits(self, client, reader):
        """Refusing is for the full case, not for every API call."""
        warmset.touch(reader, [ADDR_A], 3, client, NOW)

        admitted, _ = warmset.touch(reader, [ADDR_B], 3, client, NOW + 1, evict=False)

        assert admitted == [ADDR_B]

    def test_touch_without_eviction_allows_what_is_already_warm(self, client, reader):
        """A full set may still be re-asked for, or a poll would refuse itself.

        The union of a full set with a subset of itself is the same size, so
        this has to pass - and it is the commonest API call there is.
        """
        warmset.touch(reader, [ADDR_A, ADDR_B], 2, client, NOW)

        admitted, _ = warmset.touch(
            reader, [ADDR_A, ADDR_B], 2, client, NOW + 1, evict=False
        )

        assert sorted(admitted) == sorted([ADDR_A, ADDR_B])

    def test_touch_ages_out_what_is_no_longer_watched(self, client, reader):
        """A closed tab stops counting without anything expiring it on purpose."""
        warmset.touch(reader, [ADDR_A, ADDR_B], 2, client, NOW)

        later = NOW + warmset.WARM_SECONDS + 1
        admitted, evicted = warmset.touch(reader, [ADDR_C], 2, client, later)

        assert admitted == [ADDR_C]
        assert evicted == []
        assert warmset.members(reader, client, later) == [ADDR_C]

    def test_touch_is_unlimited_when_the_cap_is_none(self, client, reader):
        """An unbanded manifest costs one round trip, not a branch per caller."""
        admitted, evicted = warmset.touch(
            reader, [ADDR_A, ADDR_B, ADDR_C], None, client, NOW
        )

        assert sorted(admitted) == sorted([ADDR_A, ADDR_B, ADDR_C])
        assert evicted == []

    def test_touch_admits_nothing_at_a_zero_cap(self, client, reader):
        """A reader below every band keeps nothing warm."""
        assert warmset.touch(reader, [ADDR_A], 0, client, NOW) == ([], [])
        assert warmset.count(reader, client, NOW) == 0

    def test_touch_ignores_empty_addresses(self, client, reader):
        """`"ADDR ".split()` is a real source of empty strings here."""
        assert warmset.touch(reader, ["", None], 5, client, NOW) == ([], [])
        assert warmset.count(reader, client, NOW) == 0

    def test_touch_separates_readers(self, client, reader, other):
        """One reader's tabs must not spend another's budget."""
        warmset.touch(reader, [ADDR_A, ADDR_B], 2, client, NOW)
        warmset.touch(other, [ADDR_C], 2, client, NOW)

        assert warmset.count(reader, client, NOW) == 2
        assert warmset.count(other, client, NOW) == 1

    def test_touch_sets_a_ttl_so_a_departed_reader_disappears(self, client, reader):
        """The set must not outlive the reader by a day."""
        warmset.touch(reader, [ADDR_A], 5, client, NOW)

        assert 0 < client.ttl(warmset.key_for(reader)) <= warmset.WARM_TTL
