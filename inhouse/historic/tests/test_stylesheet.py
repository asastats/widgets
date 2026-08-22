"""Markup in this widget's templates has rules in this widget's stylesheet.

The widget links exactly one stylesheet -- its own ``static/historic/style.css``
-- and it may not name framework classes, because it is dropped into a host page
that has no Tailwind and no Materialize. Those two facts together mean a class
in one of these templates either has a rule here or does nothing at all.

Nothing enforced that, and the DaisyUI conversion made it easy to get wrong:
stripping the framework classes out of the markup is *correct*, and adding the
replacement rules is a separate step that can simply be forgotten. Two places
where it was:

* the consolidated category row (``.cons-text`` / ``.cons-value``) rendered as a
  run of undifferentiated inline text -- the user's "like CSS is missing"
  report, which was literally that;
* ``.sr-only`` had no rule, so ``<span class="sr-only">Total value:</span>``
  was not screen-reader-only. It was just text, and the heading read
  "Total value: 1,234.56 ALGO" to everybody.

Neither fails a template test, because the markup is right in both. Neither
fails a jest test, because no script touches them. They are only visible to
someone looking at the page, or to this.

The sweep at the bottom is the general form: every class these templates use has
a rule here unless it is listed as deliberately unstyled. It was written after
the two above were fixed by hand, and it immediately found eleven more of the
same thing -- among them the progress bars, which were empty divs of zero
height, and the NFT thumbnail, whose only size constraint had been Materialize's
``.responsive-img``, so an image served at 1200px rendered at 1200px and burst
the card.

The allowlist is the reason it can be an assertion rather than a report. It is
short, every line says why, and adding to it is meant to be an argument rather
than a formality: "no rule" is the normal state for a script hook and a defect
for anything else.
"""

import re

from pathlib import Path

import pytest

#: The widget's root, from this file.
WIDGET = Path(__file__).resolve().parent.parent

#: The one stylesheet the widget links; see ``templates/historic/index.html``.
STYLESHEET = WIDGET / "static" / "historic" / "style.css"

#: Every template the widget renders.
TEMPLATES = sorted((WIDGET / "templates" / "historic").glob("*.html"))

#: Classes that carry presentation and nothing else -- no script reads them, so
#: losing the rule loses the whole effect with no other symptom.
PRESENTATION_ONLY = [
    "circle",
    "cons-grid",
    "cons-text",
    "cons-value",
    "determinate",
    "historic-total",
    "hoverable",
    "indeterminate",
    "nft-element-image",
    "nft-trait",
    "phase-bar",
    "phase-rows",
    "progress",
    "responsive-img",
    "sr-only",
    "title",
    "truncate",
]

#: Classes that are meant to have no rule, and why. A name here is a claim that
#: its absence is deliberate; anything not here and not styled fails the sweep.
DELIBERATELY_UNSTYLED = {
    # Script hooks. `historic.js` finds elements by these and reads or writes
    # their contents; none of them says anything about how the element looks.
    "val": "figures the currency switch rewrites",
    "unit": "the unit span beside a figure",
    "pricetip": "carries the price and totals as data attributes",
    "consolidated": "marks the summary block for mainConsolidated",
    "totalnonft": "the without-NFTs checkbox's container",
    "switch": "the currency control's container; the checkbox inside it is "
    "styled by the `input[type=checkbox]` rule, which is what the "
    "conversion replaced Materialize's switch with",
    "filter": "wraps the filter input, which is styled as an input",
    # Structural markers: a name for a thing, with nothing to say about it.
    "cons": "a cell of `.cons-grid`, which already centres its text",
    "nft-element": "an NFT card, which is a `.fitem` and styled as one",
    "section-list": "a container the streamed batches are swapped into",
    "historic-settings-notes": "wraps `.historic-note` sections, which space "
    "themselves with an adjacent-sibling rule",
    # Owned elsewhere, on purpose.
    "c": "not a class: the templates emit `c{{ slot }}`, and the per-slot "
    "colours are the host's, because a stripe has to equal the colour "
    "Chart.js drew. See the comment on `.item-header.token`",
    "tooltip": "the host page's; `data-tip` is read by the site stylesheet, "
    "which is where these tooltips come from",
}

#: A class attribute's worth of tokens, with Django's tags taken out first so
#: `{% if %}` cannot contribute its keywords as class names.
TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.DOTALL)
CLASS_ATTR = re.compile(r"""class=["']([^"']*)["']""")
NAME = re.compile(r"[A-Za-z][-\w]*\Z")


#: A CSS comment. Stripped before anything is matched: this stylesheet explains
#: itself at length and names the very classes under test in its prose, so a
#: search over the raw text finds `.cons-value` inside the comment describing it
#: and then runs on to the *next* rule's body. That read as a pass for one
#: assertion here and a failure for another, which is how it was noticed.
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


@pytest.fixture(scope="module")
def stylesheet():
    return COMMENT.sub("", STYLESHEET.read_text())


def _rule(css, name):
    """Return the body of the first rule whose selector uses this class.

    :param css: stylesheet text, comments already stripped
    :type css: str
    :param name: class name, without the dot
    :type name: str
    :return: str declarations, or "" when the class is never styled
    """
    found = re.search(
        r"\.%s[\s,{][^{}]*\{([^}]*)\}" % re.escape(name), css
    )
    return found.group(1) if found else ""


@pytest.mark.parametrize("name", PRESENTATION_ONLY)
def test_the_class_is_styled_at_all(stylesheet, name):
    """The blunt one. A class with no rule in here has no rule anywhere."""
    assert _rule(stylesheet, name).strip(), (
        f".{name} is used in the templates and styled nowhere. The widget links "
        "only its own stylesheet, so this class currently does nothing."
    )


def test_the_category_label_is_quieter_than_its_figure(stylesheet):
    """What went wrong: label and figure at the same size and weight.

    The row is a name over a number, and the name is the smaller of the two.
    Asserted as properties rather than exact values so the design can be tuned
    without a test failing for no reason -- what may not come back is the label
    being indistinguishable from the figure.
    """
    label = _rule(stylesheet, "cons-text")

    assert "display: block" in label, (
        "the label must be its own line, or the figure sits beside it"
    )
    assert "font-size" in label, "the label must be smaller than its figure"
    assert "opacity" in label or "color" in label, (
        "the label must be quieter than its figure"
    )


def test_the_category_figure_carries_the_weight(stylesheet):
    assert "font-weight" in _rule(stylesheet, "cons-value")


def test_the_progress_bars_have_something_to_show(stylesheet):
    """They were empty divs. The template drives a width and nothing appeared.

    `processing.html` writes `style="width: N%"` onto `.determinate` and
    `historic.js` adds `.progress` to the loading bar's parent, so both were
    driving an element with no height and no colour: an address processed with
    nothing on screen moving. The track has to establish a containing block,
    because both fills are positioned inside it.
    """
    track = _rule(stylesheet, "progress")

    assert "height" in track, "the track has no height, so nothing can show in it"
    assert "position: relative" in track, (
        "the fills are absolutely positioned, so the track must contain them"
    )
    assert "background" in _rule(stylesheet, "determinate"), (
        "the fill has no colour, so a part-finished phase looks like an empty one"
    )


def test_the_loading_bar_is_a_bar_only_while_there_is_work(stylesheet):
    """`.progress` is a state the script drives, not a description.

    `historic.js` puts `.progress` on `.historic-progress` while work is in
    flight and takes it off when it is done, so the rules that give the bar an
    appearance have to be conditional on it. The first version of them was not,
    and the bar swept for as long as the page stayed open -- which had been
    invisible up to then only because the element had no rules at all.

    The phase bars in `processing.html` are the other case: they carry
    `.progress` in the markup because they are always on screen, so styling
    `.progress` itself is right and it is `.historic-progress` alone that must
    show nothing.
    """
    idle = re.search(
        r"\.historic-progress:not\(\.progress\)[^{]*\{([^}]*)\}", stylesheet
    )
    assert idle, "the loading bar has no idle state, so it animates forever"
    assert "display: none" in idle.group(1) or "height: 0" in idle.group(1)


def test_the_total_is_centred_over_the_row_it_breaks_down(stylesheet):
    """It was the one heading here with no rule, so it sat hard left.

    `.cons-grid` below it, `.cons-expand` below that and `.phase-address` above
    are all centred; the summary reads as one block and the figure it is about
    was the only part not lined up with it.
    """
    assert "text-align: center" in _rule(stylesheet, "historic-total")


def test_the_nft_thumbnail_cannot_burst_its_card(stylesheet):
    """The worst of them, and the least visible in the markup.

    The image carries `responsive-img hoverable nft`. `.nft` is a script hook
    that `deferImages` reads, and `.hoverable` is decoration, so
    `.responsive-img` was the only thing holding the image to its cell -- and it
    had no rule. An NFT served at its natural size rendered at its natural size,
    burst the grid, and put a horizontal scrollbar on the page.
    """
    assert "max-width: 100%" in _rule(stylesheet, "responsive-img")


def test_clipped_text_is_actually_clipped(stylesheet):
    """`.truncate` is paired with a `title` attribute holding the full text.

    That pairing only makes sense if the visible text is cut short, and it is
    the whole reason the attribute is there.
    """
    rule = _rule(stylesheet, "truncate")

    assert "text-overflow: ellipsis" in rule
    assert "overflow: hidden" in rule
    assert "nowrap" in rule


def test_screen_reader_only_text_is_actually_hidden(stylesheet):
    """It has to be off-screen, not `display: none`.

    `display: none` and `visibility: hidden` take it out of the accessibility
    tree as well, which removes the label from the screen reader it was written
    for -- leaving the heading announced as a bare number.
    """
    rule = _rule(stylesheet, "sr-only")

    assert "position: absolute" in rule
    assert "display: none" not in rule
    assert "visibility: hidden" not in rule


def _classes_in_templates():
    """Return every class name the templates use, mapped to the files using it.

    Django's tags are stripped before the class attributes are read, or
    ``class="a{% if x %} b{% endif %}"`` contributes ``if``, ``x`` and ``endif``.
    A token left holding template syntax -- ``c{{ slot }}`` becomes ``c`` -- is
    kept, because it is a real prefix worth accounting for; see the ``c`` entry
    in DELIBERATELY_UNSTYLED.

    :return: dict of str class name -> set of str filenames
    """
    found = {}
    for path in TEMPLATES:
        bare = TAG.sub(" ", path.read_text())
        for attr in CLASS_ATTR.findall(bare):
            for token in attr.split():
                if NAME.match(token):
                    found.setdefault(token, set()).add(path.name)
    return found


def test_every_class_in_the_templates_is_styled_or_declared(stylesheet):
    """The general form of both faults above.

    The widget links one stylesheet and may not name framework classes, so a
    class in a template either has a rule here, or is listed as deliberately
    unstyled with a reason. Anything else is markup asking for a presentation
    nothing provides -- which is how the consolidated row, the progress bars,
    the NFT thumbnail's size constraint and the screen-reader label were all
    lost in the same conversion, none of them failing a test.
    """
    styled = set(re.findall(r"\.([a-zA-Z][-\w]*)", stylesheet))
    used = _classes_in_templates()

    orphans = {
        name: sorted(files)
        for name, files in used.items()
        if name not in styled and name not in DELIBERATELY_UNSTYLED
    }

    assert not orphans, (
        "these classes are used in the templates and styled nowhere:\n  "
        + "\n  ".join(f"{name}: {', '.join(files)}" for name, files in sorted(orphans.items()))
        + "\n\nEither give each a rule in style.css, or add it to "
        "DELIBERATELY_UNSTYLED with the reason its absence is intended."
    )


def test_the_allowlist_does_not_outlive_the_markup():
    """An entry whose class has left the templates is a stale excuse.

    Without this the allowlist only ever grows, and a name kept in it long after
    its markup is gone would quietly excuse a *new* class that happened to
    reuse it.
    """
    used = set(_classes_in_templates())

    stale = sorted(name for name in DELIBERATELY_UNSTYLED if name not in used)

    assert not stale, (
        f"DELIBERATELY_UNSTYLED names classes no template uses any more: {stale}"
    )
