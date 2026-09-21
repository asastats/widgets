"""Testing module for the Real-time refresh widget's view."""

import json
import time
import msgpack
import pytest
from django.http import HttpResponse

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.liverefresh.views import (
    PAYLOAD_PREFIX,
    SUBSCRIBED_KEY,
    LiveRefreshView,
)

ADDRESS = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"


#: Unlimited, which is every tier the feature is actually sold to.
ASASTATSER = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]


def _view(
    mocker,
    bundle="HASH",
    addresses=ADDRESS,
    session=None,
    holdings=None,
    permission=ASASTATSER,
):
    view = LiveRefreshView()
    view.bundle = bundle
    view.addresses = addresses
    view.request = mocker.MagicMock(session=session if session is not None else {})
    # A real integer, not the mock's attribute: the daily allowance compares it
    # against the tier bands, and a MagicMock raises rather than comparing.
    view.request.user.profile.permission = permission
    view.request.user.pk = 42
    # A real mapping, not the MagicMock's attribute: `GET.get` on a mock answers
    # a truthy mock for every key, which would make every poll look like a page
    # reporting a fingerprint it never sent.
    view.request.GET = {} if holdings is None else {"holdings": holdings}
    view.kwargs = {}
    return view


class TestLiveRefreshViewPoll:
    """What the poll does with what the engine published."""

    def test_liverefresh_poll_is_the_heartbeat(self, mocker):
        """**Serving the poll is what keeps the engine re-pricing this page.**

        There is no subscribe and no unsubscribe to keep in step with a reader
        who closed a tab: they stop polling, and the page ages out of the set
        the engine reads. Nothing else writes it, so if this stops the feature
        goes quiet rather than wrong.
        """
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        view.get(view.request)

        # By key, not by call order: a paying reader's poll also marks `lvq`,
        # so `call_args` is whichever landed last.
        beats = {
            call.args[0]: call.args[1] for call in client.zadd.call_args_list
        }
        assert list(beats[SUBSCRIBED_KEY]) == [ADDRESS]

    def test_liverefresh_poll_heartbeats_even_with_nothing_published(self, mocker):
        """The order matters: a page nobody has re-priced yet is exactly the one
        that needs the engine told about it."""
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        response = view.get(view.request)

        assert client.zadd.called
        assert response.status_code == 204

    def test_liverefresh_poll_reads_the_published_payload(self, mocker):
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 5.0, "values": {1: 2.0}})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        client.get.assert_called_once_with(f"{PAYLOAD_PREFIX}:HASH")
        assert rendered.call_args.args[0]["payload"]["total"] == 5.0

    def test_liverefresh_poll_decodes_integer_asset_keys(self, mocker):
        """msgpack refuses integer map keys unless told otherwise, and the
        values map is keyed by asset id. Without this the payload is a thousand
        readable bytes that nobody can read."""
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 5.0, "values": {31566704: 2.5}}
        )
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert rendered.call_args.args[0]["payload"]["values"] == {31566704: 2.5}

    def test_liverefresh_poll_answers_204_when_the_total_has_not_moved(self, mocker):
        """**Most blocks move nothing for most pages.**

        htmx leaves the page alone on a 204, so an unchanged block costs one
        request and no DOM work - which is the difference between a poll that
        is cheap and one that repaints a page every three seconds for nothing.
        """
        session = {"liverefresh:HASH": 5.0}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 5.0})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        response = view.get(view.request)

        assert response.status_code == 204

    def test_liverefresh_poll_renders_when_the_total_moved(self, mocker):
        session = {"liverefresh:HASH": 5.0}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 7.5})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert rendered.called
        assert session["liverefresh:HASH"] == 7.5

    def test_liverefresh_poll_remembers_per_page_not_per_reader(self, mocker):
        """A reader with two address pages open must not have one silence the
        other, so what was last shown is keyed by the page."""
        session = {"liverefresh:OTHER": 7.5}
        view = _view(mocker, session=session)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 7.5})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert session["liverefresh:HASH"] == 7.5
        assert session["liverefresh:OTHER"] == 7.5


class TestLiveRefreshViewGate:
    """Who may poll at all."""

    def test_liverefresh_gate_uses_the_widget_manifest(self, mocker):
        """**It is a widget, not a condition in a view.**

        A reader selects it and a subscriber pays for it, and a fork of this
        site should be able to host it for its own users on its own bands - so
        the gate is the manifest, exactly as the historic widget's is.
        """
        view = LiveRefreshView()
        view.kwargs = {"value": ADDRESS}
        view.args = ()
        view.request = mocker.MagicMock()
        # A paid reader, so the free tier's linked-address requirement - tested
        # on its own below - does not stand in for the manifest here.
        view.request.user.profile.permission = SUBSCRIPTION_TIER_PERMISSIONS[
            "Asastatser"
        ]
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=("HASH", f"{ADDRESS} {ADDRESS}"),
        )
        gate = mocker.patch.object(
            LiveRefreshView, "manifest_test_func", return_value=True
        )

        view.test_func()

        gate.assert_called_once_with(2)

    def test_liverefresh_the_free_tier_may_only_watch_what_it_has_linked(
        self, mocker
    ):
        """**The half that stops an abuser needing no accounts at all.**

        The free allowance hangs on the address so that farming accounts buys
        nothing. Without this, farming accounts is unnecessary: a list of other
        people's addresses does just as well, and every one of them arrives with
        a fresh two hours. Requiring the wallet signature means the addresses a
        reader can spend are the addresses they control.
        """
        view = LiveRefreshView()
        view.kwargs = {"value": ADDRESS}
        view.args = ()
        view.request = mocker.MagicMock()
        view.request.user.profile.permission = 0
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=(None, ADDRESS),
        )
        mocker.patch.object(LiveRefreshView, "manifest_test_func", return_value=True)
        linked = mocker.patch(
            "widgets.inhouse.liverefresh.views.is_linked_to_user", return_value=False
        )

        assert view.test_func() is False
        linked.assert_called_once_with(view.request.user, ADDRESS)

    def test_liverefresh_a_paid_reader_may_watch_any_address(self, mocker):
        """Watching an address you do not own is an ordinary thing to buy."""
        view = LiveRefreshView()
        view.kwargs = {"value": ADDRESS}
        view.args = ()
        view.request = mocker.MagicMock()
        view.request.user.profile.permission = SUBSCRIPTION_TIER_PERMISSIONS["Intro"]
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=(None, ADDRESS),
        )
        mocker.patch.object(LiveRefreshView, "manifest_test_func", return_value=True)
        linked = mocker.patch(
            "widgets.inhouse.liverefresh.views.is_linked_to_user", return_value=False
        )

        assert view.test_func() is True
        assert not linked.called


class TestLiveRefreshFragments:
    """What actually reaches the page, rendered rather than asserted about.

    The eight tests above cover the view's decisions - heartbeat, 204, session.
    None of them rendered the template, so the fragments could have been
    anything: the placeholder they started as, a `partialdef` that was never
    loaded, or an include naming a partial that does not exist. Each of those
    fails at the first real poll and none of them fails in a unit test that
    stops at the response.
    """

    #: A published block, keyed exactly as `Total`'s fields are.
    PAYLOAD = {
        "total": 1881.509592,
        "algo": 300.0,
        "asa": 86.517108,
        "nft": 1494.992484,
        "totalusdc": 216.302465,
        "priceusdc": 8.698512,
        "pricealgo": 0.114962,
    }

    def _rendered(self, layout="dynamic", values=None):
        from django.template.loader import render_to_string

        payload = dict(self.PAYLOAD, values=values or {})
        return render_to_string(
            "liverefresh/fragments.html", {"payload": payload, "layout": layout}
        )

    def test_liverefresh_fragments_are_marked_for_out_of_band_swaps(self):
        """Without this htmx puts the whole response where the poll fired.

        `hx-swap-oob` is what lets one response update the band in two places
        at once, neither of them where the request came from.
        """
        html = self._rendered()

        assert html.count('hx-swap-oob="true"') == 2
        assert 'id="id-band-total"' in html
        assert 'id="id-band-usd"' in html

    def test_liverefresh_fragments_carry_the_figures_the_block_changed(self):
        """Formatted the way the page formats them, because it is the page's
        own partial doing the formatting."""
        html = self._rendered()

        assert "1,881.51 ALGO" in html
        assert "216.30 USD at 0.114962 USD/ALGO" in html

    def test_liverefresh_fragments_carry_what_the_currency_switch_reads(self):
        """`address.js` converts every figure on the page from these.

        The span is replaced whole, so an attribute missing here is an
        attribute gone from the page - and the switch then reads `undefined`
        and renders NaN, a block after the reader last touched anything.
        """
        html = self._rendered()

        for attribute, value in (
            ("data-price", "8.698512"),
            ("data-pricealgo", "0.114962"),
            ("data-total", "216.302465"),
            ("data-totalwnft", "1881.509592"),
            ("data-totalnft", "1494.992484"),
        ):
            # Quoted: an unquoted attribute that renders empty swallows the
            # next one, so the quotes are load-bearing rather than style.
            assert f'{attribute}="{value}"' in html, attribute

    def test_liverefresh_fragments_leave_the_nft_floor_alone(self):
        """It is not block-volatile and it lives outside the replaced span.

        `data-totalnftfloor` sits on the h1 for exactly this reason. Sending it
        from here would be harmless only until the value it carried went stale,
        because the engine's re-price never touches NFT floors.
        """
        assert "data-totalnftfloor" not in self._rendered()


class TestLiveRefreshRowFragments:
    """The per-holding half: one span per row whose figure moved."""

    BAND = {
        "total": 1881.509592,
        "algo": 300.0,
        "asa": 86.517108,
        "nft": 1494.992484,
        "totalusdc": 216.302465,
        "priceusdc": 8.698512,
        "pricealgo": 0.114962,
    }

    def _rendered(self, values):
        from django.template.loader import render_to_string

        return render_to_string(
            "liverefresh/fragments.html",
            {"payload": dict(self.BAND, values=values)},
        )

    def test_liverefresh_rows_land_on_the_row_they_belong_to(self):
        """Addressed by asset id, because that is the only identity a payload
        and a rendered row share - the engine does not know the page's order
        and the page does not know the block's."""
        html = self._rendered({31566704: 2.5, 226701642: 0.0})

        assert '<span id="v31566704" hx-swap-oob="true"' in html
        assert '<span id="v226701642" hx-swap-oob="true"' in html

    def test_liverefresh_rows_are_formatted_by_the_row_s_own_partial(self):
        """Two decimals for the reader, the full figure in `data-val`.

        The currency switch recomputes from `data-val`, never from the visible
        text, so a fragment that rounded the attribute too would make every
        switch lose precision a block after the reader stopped touching it.
        """
        html = self._rendered({31566704: 2.5678901})

        assert 'data-val="2.5678901"' in html
        assert ">2.57<" in html

    def test_liverefresh_sends_no_rows_on_a_quiet_block(self):
        """The engine diffs against last block, so most blocks move the band
        and nothing else. That has to cost no spans at all, not empty ones."""
        html = self._rendered({})

        assert 'class="v val"' not in html
        # The band still went, which is the whole point of the quiet case.
        assert 'id="id-band-total"' in html

    def test_liverefresh_rows_do_not_touch_the_row_around_them(self):
        """Only the figure is swapped.

        Swapping the `<details>` would close it, discard the reader's drag
        order and lose anything open inside - so `data-sort-value` on the row
        stays as the page was built, and nothing here may address it.
        """
        html = self._rendered({31566704: 2.5})

        assert "data-sort-value" not in html
        assert "<details" not in html


class TestLiveRefreshOlderEngine:
    """The window where the frontend is ahead of the engine.

    The two services deploy separately, so a browser can poll a payload
    published by an engine that predates a field the band reads. Every figure
    the band shows comes off this payload, so a missing key is not a smaller
    update - it is a figure the reader watches go blank.
    """

    def test_liverefresh_derives_pricealgo_when_the_engine_omitted_it(self, mocker):
        """It is the reciprocal of a field the old engine did send.

        So there is a right answer available, and refusing to compute it would
        blank the "USD/ALGO" figure for as long as the two versions differ.
        """
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 6.0, "totalusdc": 12.0, "priceusdc": 0.5, "values": {}}
        )

        payload = view._payload(client)

        assert payload["pricealgo"] == 2.0

    def test_liverefresh_keeps_the_engine_s_own_pricealgo(self, mocker):
        """Derived only when absent. The engine's figure is the authority -
        it is computed from the same block as everything beside it."""
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 6.0, "totalusdc": 12.0, "priceusdc": 0.5,
             "pricealgo": 1.9999, "values": {}}
        )

        payload = view._payload(client)

        assert payload["pricealgo"] == 1.9999

    def test_liverefresh_survives_a_price_of_zero(self, mocker):
        """No division, and no exception inside a poll that fires every block.

        A zero price is the engine failing to read a pool, not an ALGO worth
        nothing, and the band showing a blank beats the poll 500ing.
        """
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 6.0, "totalusdc": 0.0, "priceusdc": 0.0, "values": {}}
        )

        payload = view._payload(client)

        assert "pricealgo" not in payload or not payload["pricealgo"]

    def test_liverefresh_band_attributes_are_quoted(self):
        """**An empty unquoted attribute eats the next one.**

        Rendered without `pricealgo`, `data-pricealgo=` unquoted took
        `data-total=216.3` as its value and `data-total` disappeared - so one
        missing key cost two figures, and the currency switch computed the
        total from `undefined`. Quoting contains the damage to the key that is
        actually missing.
        """
        from core.tests.dom import parse
        from django.template.loader import render_to_string

        html = render_to_string(
            "liverefresh/fragments.html",
            {
                "payload": {
                    "total": 1881.5,
                    "algo": 300.0,
                    "asa": 86.5,
                    "nft": 1494.99,
                    "totalusdc": 216.3,
                    "priceusdc": 8.698512,
                    "values": {},
                }
            },
        )
        band = [
            element
            for element in parse(html).select("span")
            if element.attrs.get("id") == "id-band-total"
        ][0]

        assert band.attrs.get("data-total") == "216.3"
        assert band.attrs.get("data-pricealgo") == ""


class TestLiveRefreshAddressLimits:
    """How many addresses each tier may watch live.

    The manifest is the only place these numbers live, so this is the only
    place they can be pinned. They are a pricing decision rather than a
    technical one, and a band edited by hand - the top one was the historic
    widget's 10 until it was given this widget's own 20 - is exactly the kind
    of value that moves without anybody noticing.
    """

    #: Addresses a reader of each tier may watch.
    #:
    #: **`Intro` clears one now, and so does a reader with no tier at all.** The
    #: free band admits every authenticated reader to a single address; what
    #: separates them from Asastatser is the daily allowance in `allowance.py`,
    #: which a manifest band cannot express. Anonymous readers still clear
    #: nothing, because the access mixin requires `is_authenticated` before any
    #: band is consulted.
    EXPECTED = {"Intro": 1, "Asastatser": 1, "Professional": 5, "Cluster": 20}

    def test_liverefresh_an_untiered_reader_clears_one_address(self):
        """The free band, which is what makes the allowance reachable at all."""
        from widgethost.manifest import addresses_limit_for_permission

        from widgets.inhouse.liverefresh.manifest import MANIFEST

        assert addresses_limit_for_permission(MANIFEST.required_permission, 0) == 1

    def test_liverefresh_free_readers_get_no_second_address(self):
        """One address is the taste. A free reader asking for a bundle is
        refused by the manifest before the allowance is ever consulted."""
        from widgethost.manifest import can_access

        from widgets.inhouse.liverefresh.manifest import MANIFEST

        assert can_access(0, MANIFEST.required_permission, 1) is True
        assert can_access(0, MANIFEST.required_permission, 2) is False

    def test_liverefresh_bands_are_the_agreed_address_counts(self):
        from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
        from widgethost.manifest import addresses_limit_for_permission

        from widgets.inhouse.liverefresh.manifest import MANIFEST

        for tier, expected in self.EXPECTED.items():
            allowed = addresses_limit_for_permission(
                MANIFEST.required_permission, SUBSCRIPTION_TIER_PERMISSIONS[tier]
            )
            assert allowed == expected, f"{tier} may watch {allowed}, not {expected}"

    def test_liverefresh_counts_addresses_rather_than_pages(self):
        """A bundle of five and five single addresses cost the same allowance.

        The gate is asked with the number of addresses a page resolves to, so a
        Professional reader may spend their five on one bundle in one tab or on
        five tabs - which is the promise made to them, and the reason this asks
        about `size` rather than about how they arranged it.
        """
        from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
        from widgethost.manifest import can_access

        from widgets.inhouse.liverefresh.manifest import MANIFEST

        professional = SUBSCRIPTION_TIER_PERMISSIONS["Professional"]

        assert can_access(professional, MANIFEST.required_permission, 5)
        assert can_access(professional, MANIFEST.required_permission, 1)
        assert not can_access(professional, MANIFEST.required_permission, 6)

    def test_liverefresh_does_not_yet_limit_the_total_across_tabs(self):
        """**A known gap, asserted so it is a decision rather than a surprise.**

        `can_access` is asked once per request with that page's count, so five
        tabs of five-address bundles is five passing checks and twenty-five
        addresses re-priced every block - well past the twenty the tier buys.

        Closing it needs `lvx` to carry who is watching; it is keyed by the
        address string alone. When that changes, this test is the one that
        should start failing.
        """
        from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
        from widgethost.manifest import can_access

        from widgets.inhouse.liverefresh.manifest import MANIFEST

        professional = SUBSCRIPTION_TIER_PERMISSIONS["Professional"]

        # Each tab passes on its own, and nothing sums them.
        assert all(
            can_access(professional, MANIFEST.required_permission, 5)
            for _ in range(5)
        )


class TestLiveRefreshPageKey:
    """The Redis key this widget reads has to be the one the engine writes.

    **Nothing above this caught the two sides disagreeing**, because every test
    here sets `view.bundle` by hand and so never runs the resolution. The widget
    asked for a hash of a single address; the engine publishes single addresses
    under the address itself. Bundles agreed, single addresses never did - and
    the symptom was a permanent 204, which is indistinguishable from a quiet
    chain.

    **Asserted on the argument, not on the result.** The first version of these
    called through to the real `api.widgets` and passed here and failed for the
    user: `widgets/inhouse/historic/tests/conftest.py` installs a fake
    `api.widgets` into `sys.modules` whose
    `bundle_and_addresses_from_path` is ``lambda *a, **kw: None``, so whether
    the real one is reachable depends on which widget suites ran first. What
    was wrong was the argument this view passes, and that is a fact about this
    view - so it is patched at this view's own import site and holds either
    way.
    """

    ADDRESS = "MULILZCPNVCE3DZHTIWY4B2SDY2H3U2QN6KWZFFSS6JSFU6FWZFSXO3BBM"
    RESOLVER = "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path"

    def test_liverefresh_does_not_hash_the_page_it_looks_up(self, mocker):
        """`force_bundle=False`, or a single address is asked for as a hash.

        `_live_page` publishes under
        ``bundle_from_addresses(addresses) if " " in addresses else addresses``.
        Hashing here asks for a key nothing writes, and the poll answers 204
        for as long as the page exists.
        """
        view = _view(mocker)
        view.kwargs = {"value": self.ADDRESS}
        resolver = mocker.patch(
            self.RESOLVER, return_value=(self.ADDRESS, self.ADDRESS)
        )
        mocker.patch.object(
            LiveRefreshView, "manifest_test_func", return_value=True
        )

        view.test_func()

        assert resolver.call_args.kwargs.get("force_bundle") is False, (
            "the page is being hashed before lookup; a single address is its "
            "own key at the engine"
        )

    def test_liverefresh_reads_the_page_the_resolver_returned(self, mocker):
        """Both halves are kept: the key to read, and the page to heartbeat.

        `_payload` reads `lvp:<bundle>` and `_heartbeat` scores `addresses`, so
        dropping either would break a different half of the loop.
        """
        pair = f"{self.ADDRESS} {self.ADDRESS}"
        view = _view(mocker)
        view.kwargs = {"value": "540A5D8CEC896E073F9170AF0A962503E69147CF"}
        mocker.patch(
            self.RESOLVER,
            return_value=("540A5D8CEC896E073F9170AF0A962503E69147CF", pair),
        )
        mocker.patch.object(
            LiveRefreshView, "manifest_test_func", return_value=True
        )

        view.test_func()

        assert view.bundle == "540A5D8CEC896E073F9170AF0A962503E69147CF"
        assert view.addresses == pair


class TestLiveRefreshViewHoldingsChanged:
    """The half the fragments cannot express.

    **An out-of-band swap can only reach a row the page already has.** So an
    asset just bought has nowhere to arrive, one just sold is never mentioned
    and its row stays exactly as it was, and the amount column is not what a
    value fragment carries. The engine publishes a fingerprint of the holdings
    themselves; when it disagrees with what the reader's page was rendered from,
    the honest update is the page.
    """

    def _published(self, mocker, payload):
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(payload)
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        return client

    def test_liverefresh_poll_orders_a_reload_when_the_holdings_changed(self, mocker):
        """`HX-Refresh` rather than anything of our own: htmx reloads on it, and
        the address page's own cache entry is keyed on the same fingerprint, so
        the reload cannot be answered with the markup that prompted it."""
        view = _view(mocker, holdings="beef1234")
        self._published(mocker, {"total": 5.0, "values": {}, "holdings": "cafe5678"})

        response = view.get(view.request)

        assert response.status_code == 200
        assert response["HX-Refresh"] == "true"

    def test_liverefresh_poll_swaps_fragments_while_the_holdings_stand(self, mocker):
        """**A price move is not a reload.** This is most blocks for most pages,
        and throwing the reader's scroll position and open rows away on every
        one of them would be worse than not updating at all."""
        view = _view(mocker, holdings="beef1234")
        self._published(mocker, {"total": 5.0, "values": {1: 2.0}, "holdings": "beef1234"})
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        response = view.get(view.request)

        assert "HX-Refresh" not in response
        assert rendered.called

    def test_liverefresh_poll_does_not_reload_a_page_that_sent_no_fingerprint(
        self, mocker
    ):
        """A page rendered before this existed, and the legacy layout. Neither
        can be compared against anything, and a reload on every poll is what
        guessing would cost."""
        view = _view(mocker)
        self._published(mocker, {"total": 5.0, "values": {}, "holdings": "cafe5678"})
        mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        response = view.get(view.request)

        assert "HX-Refresh" not in response

    def test_liverefresh_poll_does_not_reload_against_an_older_engine(self, mocker):
        """An engine that does not publish the fingerprint yet. The two services
        deploy separately, so this window is real rather than hypothetical, and
        the answer is the behaviour that existed before: fragments only."""
        view = _view(mocker, holdings="beef1234")
        self._published(mocker, {"total": 5.0, "values": {}})
        mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        response = view.get(view.request)

        assert "HX-Refresh" not in response

    def test_liverefresh_poll_reloads_even_when_the_total_is_unchanged(self, mocker):
        """**The case a total cannot see.** Swapping one asset for another of
        equal value, or receiving something the pass prices at zero, leaves the
        total exactly where it was - and the 204 shortcut would then leave the
        reader on a page whose rows are wrong. The holdings check comes first
        for that reason."""
        view = _view(
            mocker, session={"liverefresh:HASH": 5.0}, holdings="beef1234"
        )
        self._published(mocker, {"total": 5.0, "values": {}, "holdings": "cafe5678"})

        response = view.get(view.request)

        assert response.status_code == 200
        assert response["HX-Refresh"] == "true"


class TestLiveRefreshFragmentsPerLayout:
    """The two layouts render different markup, and the wrong set reaches nothing.

    **The fragments address ids only one layout renders.** The dynamic band is
    `#id-band-total` and `#id-band-usd`; the classic one is `#id-band-classic`
    and `#id-total-tip`, a `.tooltip` wrapper and an sr-only span rather than a
    figure and a visible sub-line. Serving one layout's set to the other means
    every swap lands nowhere - and htmx says so on every poll, so it is not even
    a quiet failure.

    Rendering both and letting htmx discard the unmatched half was the obvious
    shortcut and is closed: htmx 2 fires `htmx:oobErrorNoTarget`, and htmx 4
    does not document the case at all.
    """

    PAYLOAD = TestLiveRefreshFragments.PAYLOAD

    def _rendered(self, layout, values=None):
        return TestLiveRefreshFragments._rendered(self, layout, values)

    def test_liverefresh_classic_renders_the_classic_band(self):
        html = self._rendered("classic")

        assert 'id="id-band-classic"' in html
        assert 'id="id-total-tip"' in html
        assert 'id="id-band-total"' not in html
        assert 'id="id-band-usd"' not in html

    def test_liverefresh_dynamic_renders_the_dynamic_band(self):
        html = self._rendered("dynamic")

        assert 'id="id-band-total"' in html
        assert 'id="id-band-usd"' in html
        assert 'id="id-band-classic"' not in html

    def test_liverefresh_classic_band_is_marked_for_out_of_band_swaps(self):
        """Without this htmx puts the response where the poll fired instead."""
        html = self._rendered("classic")

        assert html.count('hx-swap-oob="true"') >= 2

    def test_liverefresh_classic_carries_the_unit_inside_the_value(self):
        """The layouts differ in what they render, not only in what they
        address: classic puts ALGO inside the value span, the dynamic layout in
        a sibling. A shared fragment would print the unit twice on one of them.
        """
        classic = self._rendered("classic", {7: 12.5})
        dynamic = self._rendered("dynamic", {7: 12.5})

        assert 'id="v7"' in classic and "ALGO" in classic
        assert 'id="v7"' in dynamic
        assert "ALGO" not in dynamic.split('id="v7"')[1].split("</span>")[0]

    def test_liverefresh_an_unknown_layout_gets_the_dynamic_set(self):
        """A layout key nobody planned for is not a reason to send nothing: the
        dynamic page is the design direction, and its ids are what a new layout
        is most likely to have copied."""
        html = self._rendered("something-new")

        assert 'id="id-band-total"' in html


class TestLiveRefreshAllowance:
    """The refilling bucket, and what the key it hangs on is defending.

    **A feature nobody has seen is a hard thing to sell.** The bands were
    all-or-nothing, so a reader below Asastatser never saw figures move in place
    while their scroll position and open rows survived - which is the whole
    argument, and one no pricing page makes as well as ten seconds of watching.

    What replaced the daily clock is a bucket: a grant to start, a weekly
    top-up, capped back at the grant. Daily renewal was what made farming worth
    scripting - a new account every morning was a new fifteen minutes - and a
    bucket that refills slowly is a taste rather than a supply.
    """

    FREE = 0
    INTRO = SUBSCRIPTION_TIER_PERMISSIONS["Intro"]
    PAID = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]
    ADDRESS = "MULILZCPNVCE3DZHTIWY4B2SDY2H3U2QN6KWZFFSS6JSFU6FWZFSXO3BBM"

    class _Redis:
        """Enough Redis to hold one hash, since the arithmetic is the subject."""

        def __init__(self):
            self.hashes = {}

        def hgetall(self, key):
            return dict(self.hashes.get(key, {}))

        def hset(self, key, mapping=None):
            self.hashes.setdefault(key, {}).update(
                {name: str(value) for name, value in (mapping or {}).items()}
            )

        def expire(self, key, seconds):
            pass

    def test_liverefresh_terms_by_tier(self):
        from widgets.inhouse.liverefresh.allowance import terms

        assert terms(self.PAID) is None
        assert terms(self.INTRO)["capacity"] == 4 * 60 * 60
        assert terms(self.INTRO)["per_week"] == 30 * 60
        assert terms(self.FREE)["capacity"] == 2 * 60 * 60
        assert terms(self.FREE)["per_week"] == 15 * 60

    def test_liverefresh_free_hangs_on_the_address_and_intro_on_the_reader(self):
        """**This is the whole anti-abuse design, in one function.**

        An allowance bound to an account is bound to the cheapest thing in the
        system: accounts are free and need no email, so a hundred of them would
        be a hundred allowances. Bound to the address, a hundred accounts
        watching one address all spend the same bucket, and buying more free
        time means splitting a portfolio across addresses - which costs fees and
        minimum balances and fragments the combined view that was the reason to
        watch.

        Intro hangs on the reader instead, because a subscriber is not what that
        defends against, and because per-address would be four hours for every
        address they open, which is no limit at all.
        """
        from widgets.inhouse.liverefresh.allowance import bucket_key

        assert bucket_key(self.FREE, self.ADDRESS, 7) == self.ADDRESS
        assert bucket_key(self.INTRO, self.ADDRESS, 7) == "u:7"
        assert bucket_key(self.PAID, self.ADDRESS, 7) is None

    def test_liverefresh_only_the_free_tier_is_held_to_linked_addresses(self):
        """The other half of it: without this an abuser needs no accounts at
        all, only a list of other people's addresses, each arriving with a fresh
        grant. Paid tiers are unaffected - watching an address you do not own is
        an ordinary thing to buy."""
        from widgets.inhouse.liverefresh.allowance import requires_linked_address

        assert requires_linked_address(self.FREE) is True
        assert requires_linked_address(self.INTRO) is False
        assert requires_linked_address(self.PAID) is False

    def test_liverefresh_a_paid_reader_is_not_metered_at_all(self):
        """Unlimited is the common case for anyone this is sold to, so it must
        cost neither a Redis round trip nor a query."""
        from widgets.inhouse.liverefresh.allowance import spend

        client = self._Redis()

        assert spend(self.PAID, self.ADDRESS, 1, client, 1000.0) is None
        assert client.hashes == {}

    @pytest.mark.django_db
    def test_liverefresh_the_first_poll_of_a_session_charges_nothing(self):
        """There is no previous poll to measure from, and guessing would charge
        a reader for opening a page."""
        from widgets.inhouse.liverefresh.allowance import spend

        client = self._Redis()

        assert spend(self.FREE, self.ADDRESS, 1, client, 1000.0) == 2 * 60 * 60

    @pytest.mark.django_db
    def test_liverefresh_charges_wall_clock_between_polls(self):
        from widgets.inhouse.liverefresh.allowance import spend

        client = self._Redis()
        spend(self.FREE, self.ADDRESS, 1, client, 1000.0)

        assert spend(self.FREE, self.ADDRESS, 1, client, 1003.0) == 2 * 60 * 60 - 3

    @pytest.mark.django_db
    def test_liverefresh_switching_it_off_is_a_pause_that_costs_one_step(self):
        """**Pausing needs no mechanism of its own.** What is not polled is not
        charged, and a reader who comes back after an hour pays `MAX_STEP` for
        the gap rather than the hour - they were not watching it."""
        from widgets.inhouse.liverefresh.allowance import MAX_STEP, spend

        client = self._Redis()
        spend(self.FREE, self.ADDRESS, 1, client, 1000.0)

        left_after = spend(self.FREE, self.ADDRESS, 1, client, 1000.0 + 3600)

        assert 2 * 60 * 60 - left_after <= MAX_STEP

    @pytest.mark.django_db
    def test_liverefresh_two_accounts_share_one_address_bucket(self):
        """The farming case, stated as a test: a second account buys nothing."""
        from widgets.inhouse.liverefresh.allowance import spend

        client = self._Redis()
        spend(self.FREE, self.ADDRESS, 1, client, 1000.0)
        spend(self.FREE, self.ADDRESS, 1, client, 1010.0)

        assert spend(self.FREE, self.ADDRESS, 999, client, 1020.0) < 2 * 60 * 60

    @pytest.mark.django_db
    def test_liverefresh_one_intro_reader_shares_a_bucket_across_addresses(self):
        from widgets.inhouse.liverefresh.allowance import spend

        client = self._Redis()
        spend(self.INTRO, self.ADDRESS, 1, client, 1000.0)
        spend(self.INTRO, self.ADDRESS, 1, client, 1010.0)

        assert spend(self.INTRO, "X" * 58, 1, client, 1020.0) < 4 * 60 * 60

    @pytest.mark.django_db
    def test_liverefresh_a_spent_bucket_stops_at_zero(self):
        """Never negative: the view treats anything at or below zero as spent,
        and a negative balance would refill into credit the reader never had."""
        from widgets.inhouse.liverefresh.allowance import SPEND_KEY, spend

        client = self._Redis()
        client.hset(
            f"{SPEND_KEY}:{self.ADDRESS}",
            mapping={"balance": 1.0, "seen": 1000.0, "flushed": 0},
        )

        assert spend(self.FREE, self.ADDRESS, 1, client, 1100.0) == 0.0

    @pytest.mark.django_db
    def test_liverefresh_exhaustion_is_written_through_immediately(self):
        """**Redis may lose an entry; this moment may not be lost with it.**
        Sixty seconds of spend can be forgiven, a spent bucket cannot - that is
        the difference between a cache and the anti-abuse mechanism."""
        from core.models import LiveAllowanceBucket
        from widgets.inhouse.liverefresh.allowance import SPEND_KEY, spend

        client = self._Redis()
        client.hset(
            f"{SPEND_KEY}:{self.ADDRESS}",
            mapping={"balance": 1.0, "seen": 1000.0, "flushed": 0},
        )
        spend(self.FREE, self.ADDRESS, 1, client, 1100.0)

        assert LiveAllowanceBucket.objects.get(key=self.ADDRESS).balance == 0.0

    @pytest.mark.django_db
    def test_liverefresh_reading_what_is_left_does_not_spend_it(self):
        """The figure beside the button must not tick down while nothing moves."""
        from widgets.inhouse.liverefresh.allowance import left, spend

        client = self._Redis()
        spend(self.FREE, self.ADDRESS, 1, client, 1000.0)

        assert left(self.FREE, self.ADDRESS, 1, client) == 2 * 60 * 60
        assert left(self.FREE, self.ADDRESS, 1, client) == 2 * 60 * 60
        assert left(self.PAID, self.ADDRESS, 1, client) is None

    def test_liverefresh_the_refill_is_capped_at_the_grant(self):
        """Uncapped, an address nobody touched would accumulate indefinitely and
        be worth farming precisely because nobody had used it."""
        from core.models import LiveAllowanceBucket
        from widgets.inhouse.liverefresh.allowance import WEEK

        capacity, per_second = 2 * 60 * 60.0, (15 * 60) / WEEK

        assert LiveAllowanceBucket.refilled(0, WEEK, capacity, per_second) == 900.0
        assert LiveAllowanceBucket.refilled(0, WEEK * 100, capacity, per_second) == capacity
        assert LiveAllowanceBucket.refilled(capacity, WEEK * 9, capacity, per_second) == capacity
        # A clock that steps backwards must not refund anything.
        assert LiveAllowanceBucket.refilled(500, -10, capacity, per_second) == 500


class TestLiveRefreshSpentResponse:
    """What a reader is told when the day's free watching is gone."""

    def test_liverefresh_a_spent_reader_is_told_rather_than_ignored(self, mocker):
        """**Not a 204.** A page that simply stopped moving is indistinguishable
        from a broken one, and leaves the reader with neither the live updates
        nor the 60-second reload a non-subscriber gets - strictly worse than
        never having had it."""
        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=-1.0)
        mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=-1.0
        )

        response = view.get(view.request)

        assert response.status_code == 200
        assert response["HX-Trigger"] == "liverefresh:spent"

    def test_liverefresh_a_spent_reader_still_heartbeats_first(self, mocker):
        """The order matters only for the block they are still mid-way through;
        the engine drops the page 90 s after the last beat either way."""
        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=0.0)
        mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=0.0
        )

        view.get(view.request)

        assert client.zadd.called

    def test_liverefresh_an_unlimited_reader_is_never_spent(self, mocker):
        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        response = view.get(view.request)

        assert "HX-Trigger" not in response


class TestLiveRefreshPaidPriority:
    """Telling the engine which pages a subscriber is watching.

    **`lvx` says which pages are watched and nothing about who.** Shedding on
    freshness alone let a reader spending fifteen free minutes on a heavy page
    displace a Cluster subscriber, who then saw exactly what a non-subscriber
    sees - having paid not to. Harmless while everyone watching had paid, and a
    giveaway that costs a customer the moment a free tier exists.
    """

    def test_liverefresh_a_paying_reader_is_marked(self, mocker):
        from widgets.inhouse.liverefresh.views import PAID_KEY

        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        view.get(view.request)

        keys = [call.args[0] for call in client.zadd.call_args_list]
        assert PAID_KEY in keys

    def test_liverefresh_a_free_reader_is_not(self, mocker):
        """Or the set would say everybody has paid and order nothing."""
        from widgets.inhouse.liverefresh.views import PAID_KEY

        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=600.0)
        mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=600.0
        )

        view.get(view.request)

        keys = [call.args[0] for call in client.zadd.call_args_list]
        assert PAID_KEY not in keys

    def test_liverefresh_a_spent_reader_is_not_marked_either(self, mocker):
        from widgets.inhouse.liverefresh.views import PAID_KEY

        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=-1.0)
        mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=-1.0
        )

        view.get(view.request)

        keys = [call.args[0] for call in client.zadd.call_args_list]
        assert PAID_KEY not in keys

    def test_liverefresh_the_paid_mark_is_scored_like_the_heartbeat(self, mocker):
        """Same score and the same ageing, so a page stops counting as paid 90 s
        after the last subscriber closes it and nothing has to expire it."""
        from widgets.inhouse.liverefresh.views import PAID_KEY, SUBSCRIBED_KEY

        view = _view(mocker)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        view.get(view.request)

        scores = {
            call.args[0]: list(call.args[1].values())[0]
            for call in client.zadd.call_args_list
        }
        assert scores[PAID_KEY] == scores[SUBSCRIBED_KEY]


class TestLiveRefreshChargesOnlyForWhatItDelivers:
    """**An allowance is for watching a page move, not for asking whether it did.**

    The poll used to charge before it looked at the payload, so a reader whose
    page had nothing published was billed wall-clock seconds for 204s. Three
    ways that happens, none of them hypothetical:

    * the pass has not reached a newly-watched page yet;
    * admission control shed the page - on 2026-09-16 the overnight rotation
      shed 528 of 978 wanted pages at once - and the 120 s TTL behind `lvp`
      then expired it;
    * the deployment runs no live pass at all, which is any fork: the widget
      reads its own Redis and spends none of our API, so a fork may host it,
      and with nothing publishing it would have metered a feature that never
      produced a figure.
    """

    def test_liverefresh_nothing_published_is_not_charged(self, mocker):
        """The whole of the fix: no payload, no spend."""
        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = None  # `lvp:<bundle>` absent
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=600.0)
        spend = mocker.patch("widgets.inhouse.liverefresh.views.spend")

        response = view.get(view.request)

        assert response.status_code == 204
        assert not spend.called

    def test_liverefresh_a_delivered_payload_is_charged(self, mocker):
        """The other half, and the one that stops the fix becoming a giveaway:
        a poll that *did* return a figure still costs the reader time."""
        import msgpack

        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 1.0, "priceusdc": 0.2})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=600.0)
        spend = mocker.patch(
            "widgets.inhouse.liverefresh.views.spend", return_value=597.0
        )

        view.get(view.request)

        assert spend.called

    def test_liverefresh_nothing_published_still_heartbeats(self, mocker):
        """**Not charging must not become not subscribing.**

        The heartbeat is what puts the page in `lvx`, and `lvx` is what makes
        the pass publish it. Skipping it for a page with no payload would be
        self-fulfilling: the page nothing has published for would be the page
        nothing ever publishes for.
        """
        from widgets.inhouse.liverefresh.views import SUBSCRIBED_KEY

        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=600.0)
        mocker.patch("widgets.inhouse.liverefresh.views.spend")

        view.get(view.request)

        keys = [call.args[0] for call in client.zadd.call_args_list]
        assert SUBSCRIBED_KEY in keys

    def test_liverefresh_nothing_published_still_marks_a_payer(self, mocker):
        """**The same trap, and worse, for a subscriber.**

        `lvq` is what lifts a page over the admission budget. A shed page has no
        payload, so deciding the paid mark on the payload would leave a
        subscriber's shed page unmarked, unadmitted and therefore never
        published - permanently shed, by the very condition that shedding
        caused.
        """
        from widgets.inhouse.liverefresh.views import PAID_KEY

        view = _view(mocker)  # Asastatser: unmetered
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )

        view.get(view.request)

        keys = [call.args[0] for call in client.zadd.call_args_list]
        assert PAID_KEY in keys

    def test_liverefresh_a_spent_reader_is_told_even_with_no_payload(self, mocker):
        """**The spent check cannot be folded into the no-payload branch.**

        A reader who is out must be *told*, so the widget stops polling and
        `address.js` picks the plain 60-second reload back up. Answering with a
        204 because nothing happened to be published would leave them with
        neither the live updates nor the reload.
        """
        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = None
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=0.0)

        response = view.get(view.request)

        assert response.status_code == 200
        assert response["HX-Trigger"] == "liverefresh:spent"


class TestLiveRefreshAllowanceEdges:
    """The branches the happy path never reaches.

    Every one of these is a `try/except` or a fallback that exists because the
    two layers behind the allowance - a Redis hash and a database row - can
    disagree, go missing, or hold something that will not parse. They are
    unreachable from a normal poll by construction, which is exactly why they
    need writing down: a defensive branch nobody exercises is a defensive branch
    nobody knows is wrong.
    """

    def test_liverefresh_terms_is_none_below_every_band(self):
        """**The bands are floors, and the lowest is zero.**

        Nothing reaches this from a real profile - a permission is unsigned in
        practice - but `terms` is the function every other one asks "is this
        reader metered", so it answers for any integer rather than raising at
        the bottom of the stack.
        """
        from widgets.inhouse.liverefresh.allowance import terms

        assert terms(-1) is None

    def test_liverefresh_is_free_tier_splits_at_intro(self):
        """The paid/free line the settings copy and the linked-address rule both
        key on."""
        from widgets.inhouse.liverefresh.allowance import is_free_tier

        assert is_free_tier(0) is True
        assert is_free_tier(SUBSCRIPTION_TIER_PERMISSIONS["Intro"]) is False
        assert is_free_tier(ASASTATSER) is False

    def test_liverefresh_step_survives_an_unparseable_hash(self):
        """**A corrupt hash must charge nothing, not crash the poll.**

        Redis holds strings, so anything that can write to the key can put a
        word where a float belongs. Falling back to "no previous poll" charges
        this one nothing, which is the same thing a new session gets.
        """
        from widgets.inhouse.liverefresh.allowance import _step

        step, used = _step({"used": "not-a-number", "seen": "1000"}, 2000.0)

        assert step == 0.0
        assert used == 0.0

    def test_liverefresh_step_never_refunds_on_a_backwards_clock(self):
        """An NTP correction must not hand time back."""
        from widgets.inhouse.liverefresh.allowance import _step

        step, _used = _step({"used": "10", "seen": "2000"}, 1000.0)

        assert step == 0.0

    @pytest.mark.django_db
    def test_liverefresh_spend_survives_an_unparseable_balance(self, mocker):
        """A balance that will not parse falls back to the row, not to zero -
        charging a reader their whole allowance because a cache entry was
        garbled would be the worst possible reading of it."""
        from widgets.inhouse.liverefresh.allowance import spend

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"balance": b"not-a-number",
            b"seen": b"1000",
            b"flushed": b"also-not-a-number",
        }

        balance = spend(0, ADDRESS, 42, client, 1010.0)

        # The row was created at capacity, and the ten seconds since the stored
        # `seen` are clamped to MAX_STEP - a reader whose tab slept for an hour
        # is charged one poll, not an hour.
        from widgets.inhouse.liverefresh.allowance import MAX_STEP

        assert balance == pytest.approx(2 * 60 * 60 - MAX_STEP)

    @pytest.mark.django_db
    def test_liverefresh_left_falls_back_to_capacity_with_no_row(self, mocker):
        """A reader nobody has metered yet has the whole grant, and asking must
        not create a row - `left` is called to render a badge."""
        from core.models import LiveAllowanceBucket
        from widgets.inhouse.liverefresh.allowance import left

        client = mocker.MagicMock()
        client.hgetall.return_value = {}

        assert left(0, ADDRESS, 42, client) == float(2 * 60 * 60)
        assert not LiveAllowanceBucket.objects.filter(key=ADDRESS).exists()

    @pytest.mark.django_db
    def test_liverefresh_left_reads_the_row_when_redis_is_empty(self, mocker):
        """The row is the durable half: Redis entries age out, and a reader who
        comes back tomorrow must not find the grant refilled by the eviction."""
        from core.models import LiveAllowanceBucket
        from widgets.inhouse.liverefresh.allowance import left

        LiveAllowanceBucket.objects.create(
            key=ADDRESS, balance=90.0, capacity=2 * 60 * 60
        )
        client = mocker.MagicMock()
        client.hgetall.return_value = {}

        # Refill is 15 minutes a week, so a row written just now is worth what
        # it says to within a second.
        assert left(0, ADDRESS, 42, client) == pytest.approx(90.0, abs=1.0)

    @pytest.mark.django_db
    def test_liverefresh_left_falls_back_when_the_cached_balance_is_garbled(
        self, mocker
    ):
        """Same fallback as `spend`, reached the same way and separately, since
        a badge that read zero would tell a reader they were out when they are
        not."""
        from core.models import LiveAllowanceBucket
        from widgets.inhouse.liverefresh.allowance import left

        LiveAllowanceBucket.objects.create(
            key=ADDRESS, balance=120.0, capacity=2 * 60 * 60
        )
        client = mocker.MagicMock()
        client.hgetall.return_value = {b"balance": b"not-a-number"}

        assert left(0, ADDRESS, 42, client) == pytest.approx(120.0, abs=1.0)


class TestLiveRefreshRemainingBranches:
    """The two branches in the view that only a specific poll reaches."""

    def test_liverefresh_the_poll_that_exhausts_it_says_so(self, mocker):
        """**Spent is checked twice, and this is the second.**

        The first check catches a reader who arrived with nothing left. This one
        catches the poll that took the last of it: the payload was delivered and
        charged, and the reader has to be told now rather than on the next poll,
        which would spend another step first.
        """
        view = _view(mocker, permission=0)
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb({"total": 1.0, "priceusdc": 0.2})
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        mocker.patch("widgets.inhouse.liverefresh.views.left", return_value=3.0)
        mocker.patch("widgets.inhouse.liverefresh.views.spend", return_value=0.0)

        response = view.get(view.request)

        assert response.status_code == 200
        assert response["HX-Trigger"] == "liverefresh:spent"

    def test_liverefresh_too_many_addresses_for_the_tier_is_refused(self, mocker):
        """The manifest's bands are the gate, and a bundle wider than the band
        is refused before the address is looked at - so a Professional reader
        cannot reach a twenty-address page by asking for it directly."""
        view = _view(mocker, permission=0)
        view.args = ()
        view.kwargs = {"value": ADDRESS}
        # Mocked like every other `test_func` test here: the path parsing is a
        # different unit, and leaving it real made this test depend on state
        # another widget's suite mutates - it passed alone and failed in the
        # combined run.
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=(None, ADDRESS),
        )
        mocker.patch.object(view, "manifest_test_func", return_value=False)

        assert view.test_func() is False


class TestLiveRefreshUrls:
    """The widget's own URL entry.

    Imported by the host at startup rather than by anything here, so nothing in
    the suite loaded this module and a typo in the pattern would have surfaced
    only as a 404 in a browser.
    """

    def test_liverefresh_the_poll_url_is_registered_for_an_address_and_a_bundle(
        self,
    ):
        """**Read off the module, not through `reverse`.**

        `reverse` loads the root URLconf, which pulls in the whole site - and in
        the widgets-only run that dies on an unrelated import. The historic
        widget's routing test reads its patterns the same way for the same
        reason. What matters here is that the module imports and that its one
        pattern accepts both lengths.
        """
        import re

        from widgets.inhouse.liverefresh import urls

        assert len(urls.urlpatterns) == 1
        entry = urls.urlpatterns[0]
        assert entry.name == "liverefresh"
        assert entry.lookup_str == (
            "widgets.inhouse.liverefresh.views.LiveRefreshView"
        )
        pattern = re.compile(str(entry.pattern))
        assert pattern.match(ADDRESS)  # 58, an address
        assert pattern.match("A" * 40)  # 40, a bundle hash
        assert not pattern.match("A" * 39)


class TestLiveRefreshChunksALargeResync:
    """Spreading a full payload over several polls.

    **The engine's full send is deliberate and stays.** A reader polling every
    three seconds against 2.7-second blocks cannot see every diff, so the
    payload after a re-read carries every holding and heals the drift. Turning
    that into a diff would make values quietly wrong on every page.

    What it could not do was arrive all at once. One real account measured 85 kB
    of fragments in a single response, out-of-band swapped into a 22 MB
    document, every time the account was struck - which pinned the browser and
    made the page unusable. So the values are released a hundred at a time and
    nothing is dropped.
    """

    @staticmethod
    def _payload(count, total=5.0):
        return msgpack.packb(
            {"total": total, "values": {1000 + i: float(i) for i in range(count)}}
        )

    @staticmethod
    def _rendered(mocker, view, raw, session=None):
        client = mocker.MagicMock()
        client.get.return_value = raw
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )
        view.get(view.request)
        return rendered

    def test_liverefresh_a_small_payload_is_untouched(self, mocker):
        """**Every page but the pathological one.** An ordinary block moves a
        handful of values, and they must not pay for this."""
        view = _view(mocker, session={})
        rendered = self._rendered(mocker, view, self._payload(5))

        assert len(rendered.call_args.args[0]["payload"]["values"]) == 5
        assert "liverefresh:carry:HASH" not in view.request.session

    def test_liverefresh_a_large_payload_is_capped(self, mocker):
        from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS

        view = _view(mocker, session={})
        rendered = self._rendered(mocker, view, self._payload(250))

        sent = rendered.call_args.args[0]["payload"]["values"]
        assert len(sent) == LIVEREFRESH_MAX_FRAGMENTS
        assert len(view.request.session["liverefresh:carry:HASH"]) == 150

    def test_liverefresh_the_remainder_goes_out_on_later_polls(self, mocker):
        """**Nothing is dropped, which is the whole claim.** A capped response
        that quietly forgot the rest would leave figures stale on the page with
        nothing to say so."""
        from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS

        view = _view(mocker, session={})
        seen = set()

        rendered = self._rendered(mocker, view, self._payload(250))
        seen.update(rendered.call_args.args[0]["payload"]["values"])

        # The same total on the polls that follow: nothing new has moved, and
        # the reader is owed the rest regardless.
        for _ in range(2):
            rendered = self._rendered(mocker, view, self._payload(0))
            seen.update(rendered.call_args.args[0]["payload"]["values"])

        assert len(seen) == 250
        assert seen == {1000 + i for i in range(250)}
        assert not view.request.session.get("liverefresh:carry:HASH")
        assert LIVEREFRESH_MAX_FRAGMENTS == 100

    def test_liverefresh_the_carry_keeps_integer_asset_keys(self, mocker):
        """**A session round-trips through JSON, which has no integer keys.**

        The fragments are addressed by asset id, and `_payload` decodes the map
        with `strict_map_key=False` precisely to keep those integers. A carried
        id coming back as `"31566704"` would never match the `31566704` a later
        payload brings, and would address no element on the page.
        """
        view = _view(mocker, session={})
        self._rendered(mocker, view, self._payload(150))
        # Exactly what a cache-backed session does to it.
        carried = view.request.session["liverefresh:carry:HASH"]
        view.request.session["liverefresh:carry:HASH"] = json.loads(
            json.dumps(carried)
        )

        rendered = self._rendered(mocker, view, self._payload(0))

        sent = rendered.call_args.args[0]["payload"]["values"]
        assert sent
        assert all(isinstance(key, int) for key in sent)

    def test_liverefresh_a_newer_value_wins_mid_resync(self, mocker):
        """A holding that moves again while the queue drains must go out at its
        new figure, not the one it had when it joined the queue."""
        view = _view(mocker, session={})
        self._rendered(mocker, view, self._payload(250))

        moved = msgpack.packb({"total": 9.0, "values": {1249: 99.0}})
        rendered = self._rendered(mocker, view, moved)

        sent = rendered.call_args.args[0]["payload"]["values"]
        assert sent[1249] == 99.0

    def test_liverefresh_does_not_answer_204_while_it_still_owes_values(
        self, mocker
    ):
        """**A resync outlives the block that started it.** The total settles
        while values are still going out, and 204 then would strand them."""
        view = _view(mocker, session={})
        self._rendered(mocker, view, self._payload(250))

        # Same total as the poll before: unchanged, but the queue is not empty.
        rendered = self._rendered(mocker, view, self._payload(0))

        assert rendered.called

    def test_liverefresh_a_reload_clears_what_was_queued(self, mocker):
        """The page is about to be rendered whole, so the queue describes
        markup that is about to stop existing."""
        view = _view(mocker, session={}, holdings="stale")
        self._rendered(mocker, view, self._payload(250))
        assert view.request.session.get("liverefresh:carry:HASH")

        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 5.0, "holdings": "fresh", "values": {}}
        )
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        view.get(view.request)

        assert not view.request.session.get("liverefresh:carry:HASH")

    def test_liverefresh_a_non_numeric_carry_key_survives(self, mocker):
        """**Handed back rather than forced.**

        Every key the payload carries today is an asset id, so this branch is
        unreachable from the engine as it stands. It is here because the
        alternative - `int()` on whatever a future payload is keyed by - turns
        a new field into a 500 on the poll, and the mechanism that drains a
        backlog is the worst place to put a crash.
        """
        from widgets.inhouse.liverefresh.views import _asset_key

        assert _asset_key("31566704") == 31566704
        assert _asset_key(31566704) == 31566704
        assert _asset_key("total") == "total"
        assert _asset_key(None) is None


class TestLiveRefreshCountsEveryFragmentAgainstTheBudget:
    """**The cap was here and three quarters of the payload walked past it.**

    Until 2026-09-21 `_chunked` counted `values` alone, which was right when it
    was written: a changed asset was one fragment. `11f5e9f` then began
    publishing `amounts` and `positions` - the rows inside a row - and neither
    went through the budget at all.

    What a wide account's full payload actually sent was a hundred capped values
    plus every amount and every position uncapped. Measured on production on
    2026-09-21: 46.5 kB in one response, on the order of a thousand out-of-band
    swaps, every three seconds, into a fifty-thousand element page. The reader
    turned JavaScript off, which is the strongest report this feature has had.

    See `post-deploy/FINDING-poll-cost-on-heavy-pages.md`.
    """

    @staticmethod
    def _packed(assets, positions_each=0, total=5.0, with_amounts=True):
        """One asset per id, each optionally owning `positions_each` rows."""
        payload = {
            "total": total,
            "values": {1000 + i: float(i) for i in range(assets)},
        }
        if with_amounts:
            payload["amounts"] = {1000 + i: [i, 6] for i in range(assets)}
        payload["positions"] = [
            {
                "asset": 1000 + i,
                "value": float(i),
                "amount": 10,
                "decimals": 6,
                "fields": {"type": "Balance", "name": f"v{j}"},
                "links": [],
            }
            for i in range(assets)
            for j in range(positions_each)
        ]
        return msgpack.packb(payload)

    @staticmethod
    def _rendered(mocker, view, raw):
        client = mocker.MagicMock()
        client.get.return_value = raw
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )
        view.get(view.request)
        return rendered.call_args.args[0]

    @staticmethod
    def _emitted(context):
        """How many out-of-band elements the template would produce.

        Counted the way the fragment emits them: one per value, one per amount,
        one per position and a second for a position that carries an amount.
        """
        payload = context["payload"]
        return (
            len(payload.get("values") or {})
            + len(payload.get("amounts") or {})
            + sum(
                2 if position.get("amount") else 1
                for position in context.get("positions") or ()
            )
        )

    def test_liverefresh_positions_and_amounts_are_capped_too(self, mocker):
        """The regression itself, stated in the unit the browser pays in."""
        from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS

        view = _view(mocker, session={})
        context = self._rendered(mocker, view, self._packed(259, positions_each=2))

        assert self._emitted(context) <= LIVEREFRESH_MAX_FRAGMENTS

    def test_liverefresh_the_uncapped_payload_really_was_that_large(self, mocker):
        """**The counter-test, so the one above cannot pass vacuously.**

        259 assets each owning two positions that carry an amount is 259 values
        + 259 amounts + 518 position elements = 1,036 - which is what production
        was sending. A cap that did nothing would let all of it through.
        """
        from utils.constants.core import LIVEREFRESH_MAX_FRAGMENTS

        view = _view(mocker, session={})
        context = self._rendered(mocker, view, self._packed(259, positions_each=2))

        owed = view.request.session["liverefresh:carry:HASH"]
        assert owed, "nothing was deferred, so nothing was capped"
        assert 1036 - self._emitted(context) > 0
        assert LIVEREFRESH_MAX_FRAGMENTS == 100

    def test_liverefresh_a_row_and_its_positions_never_split(self, mocker):
        """**The reason the budget is spent per asset rather than per fragment.**

        Sending a position while deferring the value above it - or the reverse -
        leaves a row whose parts disagree about money, which is the fault
        `11f5e9f` was written to close. An asset is admitted with everything it
        owns or waits with all of it.
        """
        view = _view(mocker, session={})
        context = self._rendered(mocker, view, self._packed(80, positions_each=3))

        payload = context["payload"]
        sent = set(payload["values"])
        assert sent  # something went, or this proves nothing
        assert set(payload["amounts"]) == sent
        assert {position["asset"] for position in context["positions"]} == sent

    def test_liverefresh_nothing_is_dropped_when_positions_are_carried(self, mocker):
        """The claim the whole mechanism rests on, now that the queue holds more
        than values: a capped poll owes the rest and pays it off."""
        view = _view(mocker, session={})

        context = self._rendered(mocker, view, self._packed(259, positions_each=2))
        seen = set(context["payload"]["values"])
        positions = len(context["positions"])

        for _ in range(20):
            if not view.request.session.get("liverefresh:carry:HASH"):
                break
            context = self._rendered(mocker, view, self._packed(0))
            seen.update(context["payload"]["values"])
            positions += len(context["positions"])

        assert seen == {1000 + i for i in range(259)}
        assert positions == 259 * 2
        assert not view.request.session.get("liverefresh:carry:HASH")

    def test_liverefresh_a_fat_asset_is_not_stepped_over_forever(self, mocker):
        """**Starvation, which filling the budget greedily would cause.**

        One holding with more positions than the whole budget can never fit
        beside anything. If the loop skipped it to top up with cheaper assets
        behind it, it would be skipped again on every poll that had any - and
        would be the one row on the page that never came right. So the first
        asset that does not fit closes the poll.
        """
        packed = msgpack.packb(
            {
                "total": 5.0,
                "values": {1: 1.0, 2: 2.0},
                "amounts": {1: [1, 0], 2: [2, 0]},
                "positions": [
                    {
                        "asset": 1,
                        "value": 1.0,
                        "amount": 1,
                        "decimals": 0,
                        "fields": {"name": f"p{i}"},
                        "links": [],
                    }
                    for i in range(400)
                ],
            }
        )
        view = _view(mocker, session={})

        # Asset 2 is cheap and asset 1 is far over budget. Asset 1 arrives first
        # and must not be passed over for it.
        context = self._rendered(mocker, view, packed)
        assert set(context["payload"]["values"]) == {1}
        assert len(context["positions"]) == 400

    def test_liverefresh_an_old_shaped_carry_is_still_paid_off(self, mocker):
        """**A reader mid-resync across the deploy.**

        The carry used to be `{asset id: value}` and is now a bundle per asset.
        A session written by the old code has to keep draining, or that reader's
        backlog sits in their session until it expires with the page never
        coming right - and nothing on the page would say so.
        """
        view = _view(mocker, session={})
        view.request.session["liverefresh:carry:HASH"] = {"31566704": 12.5}

        context = self._rendered(mocker, view, self._packed(0))

        assert context["payload"]["values"] == {31566704: 12.5}
        assert not view.request.session.get("liverefresh:carry:HASH")

    def test_liverefresh_a_zero_value_is_sent_and_not_mistaken_for_absent(
        self, mocker
    ):
        """**Zero is a real published figure**, and the one that matters most: it
        is how the pass says a holding went away, since a fragment cannot delete
        a row. Splitting the payload on `is not None` rather than on truthiness
        is what keeps it - `if held["value"]` would silently drop every row that
        just went to zero, leaving the stale figure on the page.
        """
        packed = msgpack.packb(
            {"total": 5.0, "values": {1: 0.0}, "amounts": {1: [0, 6]}}
        )
        view = _view(mocker, session={})

        context = self._rendered(mocker, view, packed)

        assert context["payload"]["values"] == {1: 0.0}
        assert context["payload"]["amounts"] == {1: [0, 6]}


class TestLiveRefreshReloadCooldown:
    """Bounding how often the poll may order a page reload.

    **A page slower to render than its account is to transact never converges.**
    The reload fires when the fingerprint the page was rendered with differs
    from the one the engine published, and that fingerprint's counter steps on
    every block striking the account. A bundle with one busy address is struck
    most blocks - so a page taking seven seconds to render is already stale on
    arrival, reloads, and is stale again on arrival.

    Observed on a real bundle as a page reloading forever, every reload a cold
    render, and the auto-refresh checkbox flickering off and on because each
    load repaints the markup before `address.js` re-reads localStorage.
    """

    @staticmethod
    def _poll(mocker, view, holdings="published"):
        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 5.0, "holdings": holdings, "values": {}}
        )
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        return view.get(view.request)

    def test_liverefresh_the_first_mismatch_reloads(self, mocker):
        """The mechanism still has to work: a page that really did gain an
        asset needs the one renderer that can produce a row for it."""
        view = _view(mocker, session={}, holdings="rendered")

        response = self._poll(mocker, view)

        assert response["HX-Refresh"] == "true"

    def test_liverefresh_a_second_mismatch_is_refused(self, mocker):
        """**The loop, closed.** The fingerprint still disagrees - it will keep
        disagreeing for as long as the account is busy - and answering every
        poll with a reload is what made the page unusable."""
        view = _view(mocker, session={}, holdings="rendered")
        self._poll(mocker, view)

        response = self._poll(mocker, view)

        assert "HX-Refresh" not in response

    def test_liverefresh_fragments_still_flow_during_the_cooldown(self, mocker):
        """Refusing the reload must not mean refusing the update. Values keep
        arriving; only the row structure waits."""
        view = _view(mocker, session={}, holdings="rendered")
        self._poll(mocker, view)

        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 7.0, "holdings": "published", "values": {31566704: 2.5}}
        )
        mocker.patch(
            "widgets.inhouse.liverefresh.views.redis_instance", return_value=client
        )
        rendered = mocker.patch.object(
            LiveRefreshView, "render_to_response", return_value=HttpResponse()
        )

        view.get(view.request)

        assert rendered.called
        assert rendered.call_args.args[0]["payload"]["values"] == {31566704: 2.5}

    def test_liverefresh_reloads_again_once_the_cooldown_passes(self, mocker):
        """It is a cooling-off, not a switch: a page whose holdings really are
        stale must eventually be rebuilt."""
        from utils.constants.core import LIVEREFRESH_RELOAD_COOLDOWN_SECONDS

        view = _view(mocker, session={}, holdings="rendered")
        self._poll(mocker, view)

        view.request.session["liverefresh:reloaded:HASH"] = (
            time.time() - LIVEREFRESH_RELOAD_COOLDOWN_SECONDS - 1
        )
        response = self._poll(mocker, view)

        assert response["HX-Refresh"] == "true"

    def test_liverefresh_matching_fingerprints_never_reload(self, mocker):
        """Unchanged from before: the cooldown only ever refuses, never
        proposes."""
        view = _view(mocker, session={}, holdings="same")

        response = self._poll(mocker, view, holdings="same")

        assert "HX-Refresh" not in response
        assert "liverefresh:reloaded:HASH" not in view.request.session

    def test_liverefresh_a_position_fragment_carries_the_id_its_row_has(
        self, mocker
    ):
        """**The join this whole design rests on.**

        The engine cannot name a position - the live pass never serializes one,
        so it cannot build a `pid`. The page cannot value one. The engine sends
        what the position *is* and the view turns that into the same id
        `api/position_id.py` gave the row.

        Asserted against `position_id` itself rather than a literal, because a
        literal would agree with a broken recipe just as happily.
        """
        from api.position_id import position_id
        from widgets.inhouse.liverefresh.views import _named_positions

        program = {
            "program": {
                "type": "Added",
                "name": "Liquidity",
                "provider": {"name": "Pact"},
                "url": "https://app.pact.fi",
            },
            "linked": [{"text": "Source LP token", "id": 1129173576}],
        }
        published = {
            "positions": [
                {
                    "asset": 31566704,
                    "fields": {
                        "type": "Added",
                        "name": "Liquidity",
                        "provider": "Pact",
                        "code": "",
                        "url": "https://app.pact.fi",
                    },
                    "links": [["Source LP token", "1129173576"], ["Vestige", "7"]],
                    "value": 4.5,
                    "amount": 100,
                    "decimals": 6,
                    "breakdown": False,
                }
            ]
        }

        named = _named_positions(published)

        assert len(named) == 1
        assert named[0]["pid"] == position_id(31566704, program)

    def test_liverefresh_a_position_without_an_asset_is_skipped(self, mocker):
        """**The asset id is half the identity, so there is none without it.**

        `position_id` hashes it as the first part and prefixes the result with
        it, so a position missing one would be named `p1-None-...` - an id no
        row on any page carries, and therefore a fragment landing nowhere on
        every poll for as long as the engine kept sending it.

        Skipping costs that position its live figure and nothing else: the
        reload corrects it, which is what corrected every position until now.
        """
        from widgets.inhouse.liverefresh.views import _named_positions

        published = {
            "positions": [
                {"fields": {"type": "Balance"}, "value": 1.0, "amount": 1},
                {
                    "asset": 5,
                    "fields": {"type": "Balance"},
                    "links": [],
                    "value": 2.0,
                    "amount": 2,
                },
            ]
        }

        named = _named_positions(published)

        assert [position["asset"] for position in named] == [5]

    def test_liverefresh_a_payload_without_positions_is_not_an_error(self, mocker):
        """An engine that predates this sends no `positions` at all, and the
        two services deploy separately - so that window is real."""
        from widgets.inhouse.liverefresh.views import _named_positions

        assert _named_positions({"values": {}}) == []
        assert _named_positions(None) == []

    def test_liverefresh_a_struck_account_alone_does_not_reload(self, mocker):
        """**The reload this whole line of work exists to retire.**

        A fingerprint is `<counter>:<digest>`. The counter steps on every block
        that strikes the account; the digest covers which assets are held. Same
        assets, different counter means nothing structural moved, and every
        figure that did is now a fragment - including a position's, which is
        what made this unsafe the first time it was tried.
        """
        view = _view(mocker, session={}, holdings="3:same-assets")

        response = self._poll(mocker, view, holdings="9:same-assets")

        assert "HX-Refresh" not in response

    def test_liverefresh_a_changed_asset_set_still_reloads(self, mocker):
        """No fragment can create a row for an asset that has just arrived, and
        that is exactly what moves the digest."""
        view = _view(mocker, session={}, holdings="3:old-assets")

        response = self._poll(mocker, view, holdings="3:new-assets")

        assert response["HX-Refresh"] == "true"

    def test_liverefresh_a_fingerprint_without_a_counter_is_compared_whole(
        self, mocker
    ):
        """A page rendered before the counter existed, or any shape without a
        separator. Comparing it against itself works; guessing does not."""
        view = _view(mocker, session={}, holdings="bare-old-form")

        assert "HX-Refresh" not in self._poll(mocker, view, holdings="bare-old-form")
        assert self._poll(mocker, view, holdings="different")["HX-Refresh"] == "true"

    def test_liverefresh_a_position_fragment_carries_the_id_its_row_has(
        self, mocker
    ):
        """**The join this whole design rests on.**

        The engine cannot name a position - the live pass never serializes one,
        so it cannot build a `pid`. The page cannot value one. The engine sends
        what the position *is* and the view turns that into the same id
        `api/position_id.py` gave the row.

        Asserted against `position_id` itself rather than a literal, because a
        literal would agree with a broken recipe just as happily.
        """
        from api.position_id import position_id
        from widgets.inhouse.liverefresh.views import _named_positions

        program = {
            "program": {
                "type": "Added",
                "name": "Liquidity",
                "provider": {"name": "Pact"},
                "url": "https://app.pact.fi",
            },
            "linked": [{"text": "Source LP token", "id": 1129173576}],
        }
        published = {
            "positions": [
                {
                    "asset": 31566704,
                    "fields": {
                        "type": "Added",
                        "name": "Liquidity",
                        "provider": "Pact",
                        "code": "",
                        "url": "https://app.pact.fi",
                    },
                    "links": [["Source LP token", "1129173576"], ["Vestige", "7"]],
                    "value": 4.5,
                    "amount": 100,
                    "decimals": 6,
                    "breakdown": False,
                }
            ]
        }

        named = _named_positions(published)

        assert len(named) == 1
        assert named[0]["pid"] == position_id(31566704, program)

    def test_liverefresh_a_position_without_an_asset_is_skipped(self, mocker):
        """**The asset id is half the identity, so there is none without it.**

        `position_id` hashes it as the first part and prefixes the result with
        it, so a position missing one would be named `p1-None-...` - an id no
        row on any page carries, and therefore a fragment landing nowhere on
        every poll for as long as the engine kept sending it.

        Skipping costs that position its live figure and nothing else: the
        reload corrects it, which is what corrected every position until now.
        """
        from widgets.inhouse.liverefresh.views import _named_positions

        published = {
            "positions": [
                {"fields": {"type": "Balance"}, "value": 1.0, "amount": 1},
                {
                    "asset": 5,
                    "fields": {"type": "Balance"},
                    "links": [],
                    "value": 2.0,
                    "amount": 2,
                },
            ]
        }

        named = _named_positions(published)

        assert [position["asset"] for position in named] == [5]

    def test_liverefresh_a_payload_without_positions_is_not_an_error(self, mocker):
        """An engine that predates this sends no `positions` at all, and the
        two services deploy separately - so that window is real."""
        from widgets.inhouse.liverefresh.views import _named_positions

        assert _named_positions({"values": {}}) == []
        assert _named_positions(None) == []

    def test_liverefresh_a_reader_who_went_away_is_not_still_cooling_off(
        self, mocker
    ):
        """**Closing the tab is not polling, and the stamp outlived it.**

        Reported 2026-09-18: swap, close the window, swap again, come back - and
        the reload the page now genuinely needed was refused because the *first*
        swap had spent the cooldown less than a minute earlier. "60 seconds and
        an F5" is this constant to the second.

        The gap is what a runaway cannot fake: it is found out of date on every
        poll, so its stamp is never stale.
        """
        from utils.constants.core import LIVEREFRESH_RELOAD_COOLDOWN_SECONDS

        view = _view(mocker, session={}, holdings="rendered")
        self._poll(mocker, view)
        assert "HX-Refresh" not in self._poll(mocker, view)

        # Away for longer than the cooldown, then back with a page that is
        # stale again. Both stamps are old; only the gap decides.
        gone = time.time() - LIVEREFRESH_RELOAD_COOLDOWN_SECONDS - 1
        view.request.session["liverefresh:stale:HASH"] = gone

        assert self._poll(mocker, view)["HX-Refresh"] == "true"

    def test_liverefresh_a_reader_who_kept_polling_still_cools_off(self, mocker):
        """The other half, and the one that matters: a page found stale on
        consecutive polls is the runaway, and it must stay refused. Without this
        the fix above would simply reopen the loop."""
        view = _view(mocker, session={}, holdings="rendered")
        self._poll(mocker, view)

        # A moment later, still stale - which is what a busy account looks like.
        view.request.session["liverefresh:stale:HASH"] = time.time() - 1

        assert "HX-Refresh" not in self._poll(mocker, view)

    def test_liverefresh_a_page_in_sync_records_no_staleness(self, mocker):
        """The stamp says when the page was last found *out of date*, not when
        it last polled. A page that has been in sync for ten minutes has no
        cooldown left worth honouring, and must not be made to look like one."""
        view = _view(mocker, session={}, holdings="same")

        self._poll(mocker, view, holdings="same")

        assert "liverefresh:stale:HASH" not in view.request.session
