"""Testing module for the Real-time refresh widget's view."""

import msgpack
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
        mocker.patch(
            "widgets.inhouse.liverefresh.views.bundle_and_addresses_from_path",
            return_value=("HASH", f"{ADDRESS} {ADDRESS}"),
        )
        gate = mocker.patch.object(LiveRefreshView, "manifest_test_func")

        view.test_func()

        gate.assert_called_once_with(2)


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
    """The daily free taste, and what it costs to give away.

    **A feature nobody has seen is a hard thing to sell.** The bands were
    all-or-nothing, so a reader below Asastatser never saw figures move in place
    while their scroll position and open rows survived - which is the whole
    argument, and one no pricing page makes as well as ten seconds of watching.
    """

    def test_liverefresh_allowance_by_tier(self):
        from widgets.inhouse.liverefresh.allowance import daily_allowance

        assert daily_allowance(0) == 15 * 60
        assert daily_allowance(SUBSCRIPTION_TIER_PERMISSIONS["Intro"]) == 30 * 60
        assert daily_allowance(SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]) is None
        assert daily_allowance(SUBSCRIPTION_TIER_PERMISSIONS["Cluster"]) is None

    def test_liverefresh_a_nonsense_permission_gets_nothing(self):
        """**The fall-through, and it falls the safe way.**

        Every band is cleared by a permission of zero or more, so this is only
        reached by a negative one - a corrupt profile row, or a caller passing a
        sentinel. Returning the free allowance there would hand time out on the
        strength of bad data; returning zero costs a reader who does not exist
        nothing, and is visible as "it never works for them" rather than as a
        quietly generous bug.
        """
        from widgets.inhouse.liverefresh.allowance import daily_allowance

        assert daily_allowance(-1) == 0

    def test_liverefresh_remaining_is_the_allowance_less_what_is_spent(self, mocker):
        """The metered path, which is the one every free reader takes.

        `remaining` going negative is not guarded here on purpose: the view
        treats anything at or below zero as spent, and a number that says *how
        far* over tells a log reader more than a clamp would.
        """
        from widgets.inhouse.liverefresh.allowance import _today, remaining

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"880", b"seen": b"1000"
        }

        # 15 minutes of allowance, 880 seconds gone, plus 2.5 for this poll.
        assert remaining(0, 1, client, 1002.5) == 15 * 60 - 882.5

    def test_liverefresh_remaining_goes_negative_once_spent(self, mocker):
        from widgets.inhouse.liverefresh.allowance import _today, remaining

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"901", b"seen": b"1000"
        }

        assert remaining(0, 1, client, 1000.0) < 0

    def test_liverefresh_a_paid_reader_is_not_metered_at_all(self, mocker):
        """Unlimited is the common case for anyone this is sold to, so it must
        not cost a Redis round trip the poll had not already made."""
        from widgets.inhouse.liverefresh.allowance import remaining

        client = mocker.MagicMock()

        assert remaining(
            SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"], 1, client, 1000.0
        ) is None
        assert not client.hgetall.called

    def test_liverefresh_the_first_poll_of_a_day_charges_nothing(self, mocker):
        """There is no previous poll to measure from, and guessing would charge
        a reader for opening a page."""
        from widgets.inhouse.liverefresh.allowance import charge

        client = mocker.MagicMock()
        client.hgetall.return_value = {}

        assert charge(1, client, 1000.0) == 0.0

    def test_liverefresh_a_new_day_starts_the_allowance_over(self, mocker):
        """Yesterday's spend is not today's. Unix 1000 is 1970-01-01, so the
        stored day here really is a different one - the first draft of this test
        used that very date as the "different" day and passed for the wrong
        reason."""
        from widgets.inhouse.liverefresh.allowance import charge

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": b"1999-12-31", b"used": b"899", b"seen": b"1000"
        }

        assert charge(1, client, 1002.5) == 0.0

    def test_liverefresh_the_same_day_accumulates(self, mocker):
        from widgets.inhouse.liverefresh.allowance import charge, _today

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"10", b"seen": b"1000"
        }

        assert charge(1, client, 1002.5) == 12.5

    def test_liverefresh_a_long_absence_is_charged_the_cap(self, mocker):
        """**A reader who shut the laptop was not watching it.** Charging the
        wall-clock gap would spend a whole allowance on one poll after lunch."""
        from widgets.inhouse.liverefresh.allowance import MAX_STEP, charge, _today

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"0", b"seen": b"1000"
        }

        assert charge(1, client, 1000.0 + 3600) == MAX_STEP

    def test_liverefresh_several_tabs_do_not_multiply_the_spend(self, mocker):
        """Four tabs poll four times as often, each charging a quarter of the
        gap, so a reader spends one second per second however they arranged it -
        which is the same promise the address bands make."""
        from widgets.inhouse.liverefresh.allowance import charge, _today

        client = mocker.MagicMock()
        state = {"day": _today(1000.0), "used": "0", "seen": "1000"}
        client.hgetall.side_effect = lambda *a: {
            k.encode(): str(v).encode() for k, v in state.items()
        }
        client.hset.side_effect = lambda key, mapping: state.update(
            {k: str(v) for k, v in mapping.items()}
        )

        # Twelve seconds of wall clock, polled by four tabs every 0.75s.
        now = 1000.0
        for _ in range(16):
            now += 0.75
            used = charge(1, client, now)

        assert 11.5 <= used <= 12.5, used

    def test_liverefresh_a_clock_that_steps_backwards_refunds_nothing(self, mocker):
        """An NTP correction must not hand out allowance."""
        from widgets.inhouse.liverefresh.allowance import charge, _today

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"100", b"seen": b"1000"
        }

        assert charge(1, client, 990.0) == 100.0

    def test_liverefresh_unreadable_spend_starts_the_day_over(self, mocker):
        """Rubbish in the hash is a reader who gets their allowance again, not a
        poll that raises. Nothing else writes this key, but it is a shared cache
        and the failure should be generous rather than loud."""
        from widgets.inhouse.liverefresh.allowance import charge, _today

        client = mocker.MagicMock()
        client.hgetall.return_value = {
            b"day": _today(1000.0).encode(), b"used": b"nonsense", b"seen": b"x"
        }

        assert charge(1, client, 1002.5) == 0.0


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
        mocker.patch(
            "widgets.inhouse.liverefresh.views.remaining", return_value=-1.0
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
        mocker.patch(
            "widgets.inhouse.liverefresh.views.remaining", return_value=0.0
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
        mocker.patch(
            "widgets.inhouse.liverefresh.views.remaining", return_value=600.0
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
        mocker.patch(
            "widgets.inhouse.liverefresh.views.remaining", return_value=-1.0
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
