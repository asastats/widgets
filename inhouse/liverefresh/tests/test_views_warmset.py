"""What the poll does with one reader's warm set, against a real Redis.

**Separate from `test_views.py` because the client has to be real.** Every test
in that module hands the view a `MagicMock`, which is right for what they check
- the client is a collaborator there, not the subject. But a mock's sorted set
is always empty, so the cap can never bite and this entire path would pass
without once executing. Here the set's actual contents are the thing under test.

The hole being closed: the tier bands are checked per *page*. `can_access` is
asked once per request with that page's address count, so five tabs of one
address each are five independent size-1 checks that all pass. The warm set is
what counts a reader's addresses together, across tabs and across surfaces.

Keys are namespaced per test and deleted afterwards, and every test skips when
no Redis answers, so a checkout without one is not a failure.
"""

import time
import uuid

import pytest

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.liverefresh import warmset
from widgets.inhouse.liverefresh.views import (
    PAID_KEY,
    PAYLOAD_PREFIX,
    SUBSCRIBED_KEY,
    LiveRefreshView,
)

ADDRESS = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"
OTHER = "OGRUNXPSMO7Z7EGOGONA7BVEIN7YIJZZB372GZGJIAPB363C6KB42CEN2M"

#: Asastatser's band is one address wide, which makes it the cheapest tier to
#: demonstrate a full set with - and the tier the feature is first sold to.
ASASTATSER = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]


@pytest.fixture
def client():
    """Return a real Redis client, skipping the test when none answers."""
    from utils.clients import redis_instance

    try:
        instance = redis_instance()
        instance.ping()
    except Exception as error:  # noqa: BLE001 - any failure is "no Redis here"
        pytest.skip(f"no Redis to test against: {error}")
    return instance


@pytest.fixture
def view(mocker, client):
    """Return a poll view for an isolated reader, cleaned up afterwards.

    Mirrors `test_views._view`, with a unique primary key so concurrent runs
    and leftovers from a killed run cannot reach each other.
    """
    instance = LiveRefreshView()
    instance.bundle = "HASH"
    instance.addresses = ADDRESS
    instance.request = mocker.MagicMock(session={})
    # Real integers, not the mock's attributes: the tier bands are compared
    # against these, and a MagicMock compares truthy against everything.
    instance.request.user.profile.permission = ASASTATSER
    instance.request.user.pk = f"test-{uuid.uuid4().hex}"
    instance.request.GET = {}
    instance.kwargs = {}

    mocker.patch(
        "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
    )
    yield instance
    client.delete(warmset.key_for(instance.request.user.pk))


def fill_the_slot(view, client):
    """Leave this reader's one slot held by another, actively-polled page."""
    warmset.touch(view.request.user.pk, [OTHER], 1, client, time.time())


def keys_written(spy):
    """Return the sorted-set keys a `zadd` spy was called with."""
    return [call.args[0] for call in spy.call_args_list]


class TestWarmSetPoll:
    """A page over the reader's cap is not kept alive, and costs them nothing."""

    def test_a_second_page_over_the_cap_is_not_heartbeated(
        self, mocker, view, client
    ):
        """**The hole this closes.** An Asastatser may watch one address.

        Their second tab passes its own size-1 access check, so before the warm
        set existed it was heartbeated too and the engine re-priced both pages
        every block for a reader entitled to one.
        """
        spy = mocker.patch.object(client, "zadd", wraps=client.zadd)
        fill_the_slot(view, client)

        response = view.get(view.request)

        assert response.status_code == 204
        assert SUBSCRIBED_KEY not in keys_written(spy)

    def test_an_over_cap_page_is_not_marked_paid(self, mocker, view, client):
        """`lvq` is what lifts a page over the engine's admission budget.

        Asking the engine to prioritise a page we have deliberately not
        subscribed would be asking for work we just decided not to want.
        """
        spy = mocker.patch.object(client, "zadd", wraps=client.zadd)
        fill_the_slot(view, client)

        view.get(view.request)

        assert PAID_KEY not in keys_written(spy)

    def test_an_over_cap_page_is_not_charged(self, mocker, view, client):
        """A page that cannot move must not cost the reader time.

        The same rule as the nothing-published branch, which exists because
        readers were billed wall-clock seconds for pages admission control had
        shed - 528 of 978 wanted pages in one night.

        **A payload has to exist for this to mean anything.** Without one the
        nothing-published branch skips the charge too, so the test passes
        whatever the warm set decides - which is how it was first written, and
        sabotaging the wiring is what exposed it.
        """
        import msgpack

        published = f"{PAYLOAD_PREFIX}:{view.bundle}"
        client.set(published, msgpack.packb({"total": 5.0, "values": {1: 2.0}}))
        spend = mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=None
        )
        fill_the_slot(view, client)
        try:
            view.get(view.request)

            assert not spend.called
        finally:
            client.delete(published)

    def test_the_charge_does_happen_when_the_page_fits(self, mocker, view, client):
        """The other half, or the test above could pass by never charging.

        This is what makes "not charged" a statement about the warm set rather
        than about the fixture.
        """
        import msgpack

        published = f"{PAYLOAD_PREFIX}:{view.bundle}"
        client.set(published, msgpack.packb({"total": 5.0, "values": {1: 2.0}}))
        spend = mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=None
        )
        try:
            view.get(view.request)

            assert spend.called
        finally:
            client.delete(published)

    def test_the_readers_own_single_page_still_fits(self, mocker, view, client):
        """A lone page must never refuse itself, or nobody gets anything.

        The obvious way to get this wrong is to compare the page's size against
        the cap *after* adding it and conclude it does not fit.
        """
        spy = mocker.patch.object(client, "zadd", wraps=client.zadd)

        view.get(view.request)

        assert SUBSCRIBED_KEY in keys_written(spy)

    def test_repolling_the_same_page_keeps_fitting(self, mocker, view, client):
        """The commonest request there is: the same page, every few seconds.

        It must stay admitted rather than counting itself twice and tipping
        over its own cap on the second poll.
        """
        view.get(view.request)
        spy = mocker.patch.object(client, "zadd", wraps=client.zadd)

        view.get(view.request)

        assert SUBSCRIBED_KEY in keys_written(spy)

    def test_the_slot_frees_when_the_other_tab_stops_polling(
        self, mocker, view, client
    ):
        """A closed tab gives its slot up, and the waiting page starts working.

        Nothing expires it on purpose: the score simply ages past
        `IDLE_SECONDS` and the next poll takes it.
        """
        warmset.touch(
            view.request.user.pk,
            [OTHER],
            1,
            client,
            time.time() - warmset.IDLE_SECONDS - 1,
        )
        spy = mocker.patch.object(client, "zadd", wraps=client.zadd)

        view.get(view.request)

        assert SUBSCRIBED_KEY in keys_written(spy)
