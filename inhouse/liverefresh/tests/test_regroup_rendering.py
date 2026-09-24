"""Render the regroup fragment against the real sample payload.

**The reason this is a rendering test and not a view test.** The view decides
*which* groups to send; what it sends is the address page's own
`programgroups` partial, rendered from the snapshot rather than from an
`AsaItem` the page built. Those two contexts are not identical, and the only
way to find out whether the partial survives the second one is to render it.
"""

import json
from pathlib import Path

import pytest
from django.template.loader import render_to_string

SAMPLE_PATH = (
    Path(__file__).parent.parent.parent
    / "utils"
    / "tests"
    / "sample_serialized_540A5.json"
)


@pytest.fixture(scope="module")
def asaitems():
    if not SAMPLE_PATH.exists():
        pytest.skip(f"sample payload not at {SAMPLE_PATH}")
    from api.position_id import annotate_positions

    with SAMPLE_PATH.open() as handle:
        payload = json.load(handle)
    for item in payload.get("asaitems") or ():
        annotate_positions(item["asset"]["id"], item.get("programs"))
    return [item for item in payload["asaitems"] if item.get("programs")]


class TestLiveRegroupRendering:
    """What the reader's page actually receives."""

    def test_liveregroup_renders_every_group_it_is_given(self, asaitems):
        """Every asset in the sample, not one: a partial that raises on the
        third asaitem is a partial that works in a test and takes a page's
        positions away in production."""
        html = render_to_string("liverefresh/regroup.html", {"changed": asaitems})

        assert html.count('class="program-groups"') == len(asaitems)

    def test_liveregroup_addresses_the_group_the_page_rendered(self, asaitems):
        """`pg-f<asset>` is the id the address page puts on `.program-groups`,
        and an out-of-band swap that names anything else lands nowhere."""
        html = render_to_string("liverefresh/regroup.html", {"changed": asaitems[:1]})

        assert f'id="pg-f{asaitems[0]["asset"]["id"]}"' in html
        assert 'hx-swap-oob="true"' in html

    def test_liveregroup_carries_the_rows_and_their_ids(self, asaitems):
        """The point of sending the group: the rows inside it. Each one keeps
        the `data-pid` the next block's value fragments land on."""
        item = next(
            item
            for item in asaitems
            if any(
                program.get("pid") and not program.get("pid_ambiguous")
                for program in item["programs"]
            )
        )
        html = render_to_string("liverefresh/regroup.html", {"changed": [item]})

        pid = next(
            program["pid"]
            for program in item["programs"]
            if program.get("pid") and not program.get("pid_ambiguous")
        )
        assert f'data-pid="{pid}"' in html
        assert f'id="pv-{pid}"' in html

    def test_liveregroup_sends_the_page_no_swap_attribute_of_its_own(self, asaitems):
        """`hx-swap-oob` belongs on the swapped element and nowhere else. The
        page renders the same partial without `oob`, and a stray attribute
        there would make the address page try to swap itself into itself."""
        from django.template.loader import render_to_string as render

        html = render(
            "snippets/dynamic/asset.html#programgroups",
            {"asaitem": asaitems[0], "asset": asaitems[0]["asset"]},
        )

        assert "hx-swap-oob" not in html
        assert f'id="pg-f{asaitems[0]["asset"]["id"]}"' in html

    def test_liveregroup_renders_nothing_for_nothing(self):
        """An empty body never reaches the template - the view answers 204 -
        but a partial that raised on an empty list would turn a quiet block
        into a 500 the moment that changed."""
        assert render_to_string("liverefresh/regroup.html", {"changed": []}).strip() == ""


def _built_asaitem(programs):
    """Return an asaitem in the shape the snapshot hands the partial.

    **Built rather than captured, and only because the capture is optional.**
    The sample payload is what the tests above render, and it is the real
    thing; this exists so that a checkout without it still fails when the
    partial stops rendering, rather than skipping the whole file and reporting
    green. Anything the sample proves and this cannot is proved above.
    """
    from api.position_id import annotate_positions

    item = {
        "asset": {"id": 31566704, "unit": "USDC", "name": "USDC", "decimals": 6},
        "amount": 5500500,
        "value": 22.0,
        "programs": programs,
    }
    annotate_positions(item["asset"]["id"], item["programs"])
    return item


def _program(name, value, amount, provider="Mallow"):
    return {
        "program": {
            "type": "Staked",
            "name": name,
            "provider": {"name": provider},
            "url": "https://usemallow.app/",
            "code": "",
        },
        "value": value,
        "amount": amount,
        "linked": [],
        "distribution": [],
    }


class TestLiveRegroupRenderingWithoutTheCapture:
    """The partial itself, on a checkout with no sample payload."""

    def test_liveregroup_renders_the_group_and_its_rows(self):
        item = _built_asaitem(
            [
                _program("Mallow (ALGO up)", 12.0, 3000000),
                _program("Mallow (ALGO down)", 10.0, 2500000),
            ]
        )

        html = render_to_string("liverefresh/regroup.html", {"changed": [item]})

        assert 'id="pg-f31566704"' in html
        assert 'hx-swap-oob="true"' in html
        assert "Mallow (ALGO up)" in html
        assert "Mallow (ALGO down)" in html
        assert html.count('class="position"') == 2

    def test_liveregroup_counts_a_group_of_two_and_subtotals_it(self):
        """**Why the group is the unit and the row is not.** A count beside the
        venue and a subtotal in the money column both appear only above two
        positions, so a row arriving changes three things outside itself.
        Sending the row alone leaves a group of two labelled as a group of one.
        """
        one = render_to_string(
            "liverefresh/regroup.html",
            {"changed": [_built_asaitem([_program("Mallow (ALGO up)", 12.0, 3000000)])]},
        )
        two = render_to_string(
            "liverefresh/regroup.html",
            {
                "changed": [
                    _built_asaitem(
                        [
                            _program("Mallow (ALGO up)", 12.0, 3000000),
                            _program("Mallow (ALGO up)", 10.0, 2500000),
                        ]
                    )
                ]
            },
        )

        assert "pgroup-total" not in one
        assert "pgroup-total" in two

    def test_liveregroup_gives_every_named_row_the_ids_a_fragment_lands_on(self):
        """The group is sent once; the figures in it are corrected every block
        after that by `pv-` and `pq-`. A group rendered without them would go
        still until the next position change."""
        item = _built_asaitem([_program("Mallow (ALGO down)", 10.0, 2500000)])
        pid = item["programs"][0]["pid"]

        html = render_to_string("liverefresh/regroup.html", {"changed": [item]})

        assert f'id="pv-{pid}"' in html
        assert f'id="pq-{pid}"' in html
        assert f'data-pin-position="{pid}"' in html
