# Widgets logbook

Why the code in this submodule is the way it is: the measurements, the outages,
the decisions taken and the ones reversed.

One section per module or template, under its path from this repository's root.
Inside it, `## Module` holds notes about the file as a whole and a subsection
per function, partial or block carries the rest.

The code carries what a reader needs to *use* it correctly. This carries what
they would need to *change* it safely.

Entries are dated where the date is known, and append-only: a note that turned
out to be wrong gets a correction beneath it rather than an edit.

The host repository keeps its own at `frontend/docs/logbook.md`. A note belongs
there when it is about the page, and here when it is about a widget.

---

## inhouse/liverefresh/templates/liverefresh/regroup.html

### Module

**Why whole groups rather than the rows that moved.** A row arriving changes
three things outside itself: the count beside the venue name, the subtotal in
the money column, and whether either of them is rendered at all. Sending the row
alone leaves a group of two labelled as a group of one.

**Why it renders the page's own partial.** A group carries a heading, a count, a
conditional subtotal, a pin control per row and a breakdown panel under it. A
second copy of all that in JavaScript would drift the first time any of it
changed, silently, because nothing renders both and compares.

---

## inhouse/historic/templates/historic/assets.html

### The metadata panels

These were `<span>`s with the label written into the text and a `<br />` after
each, so the panel announced no terms and no definitions - nothing tied "Total
supply" to its number for a reader who cannot see the layout. The gap between one
program and the next belongs to the list that holds them, not to a trailing break
inside the last one.

### The total heading

The heading was the number itself, so it announced a figure with nothing saying
what it counts.

**`.htip`, not `.tooltip`.** The latter is DaisyUI's, and it worked here only
because this widget renders inside the site's base template. `.htip` is defined
in the widget's own stylesheet and reads the same `data-tip`.

Making every figure focusable was the alternative and would be worse: it puts a
tab stop on each of several dozen numbers to expose something the currency switch
already offers in one keystroke. Only the total's tip carries the exchange rate,
which is available nowhere else.

---

## inhouse/swapcore/templates/swap/_swap_modal.html

### The router name

It was in the header, and hidden under 600px because the header is one row -
title, tag, slippage, close - and a phone has no room for a fourth thing. Which
hid it exactly where the reader is least likely to know which router they are on.

### The mode tabs

`[data-swap-mode]` replaced the Materialize `.tabs`, which also dropped the
zero-width-indicator workaround that tabs initialised inside a `display:none`
modal needed.

---

## inhouse/dustsweep/templates/dustsweep/_sweep_modal.html

### Module

The anatomy is the swap modal's, deliberately: the swap modal is the design the
rest of the site is moving onto, so this follows it rather than inventing a
second language. **What is not copied is the class names** - a sweep is not a
swap, and reusing `.swap-*` would tie this to rules that will be changed for swap
reasons.

The three figures are the three questions a reader has: what do I get back, how
many times must I sign, and how much of my account does this touch.

---

## inhouse/liverefresh/views.py

### `LiveRefreshView.get`

**Billing a reader for a page that could not move.** On 2026-09-16 the overnight
rotation shed 528 of 978 wanted pages at once. Each shed page's payload aged out
of the 120 s TTL behind it, and every reader of one was being charged wall-clock
seconds for a page the engine had stopped re-pricing. The "nothing published,
nothing charged" branch is that fix; the warm-set branch above it exists because
the same defect had already been shipped once in the other direction.

A deployment whose engine publishes nothing at all is the same shape. A fork can
host this widget - it reads its own Redis and spends none of our API - but with
no live pass behind it the payload never arrives, and charging an allowance down
to zero for a feature that never produced a figure is indefensible.

### `_reload_response`

**Narrowing the comparison to the asset digest was tried on 2026-09-19 and
reverted within the hour.** Fragments reached a row's aggregate and nothing
inside it: a row's positions - "Wallet balance", a farm, a lend - rendered with
no id, so nothing addressed them and the whole-page rebuild was the only thing
that ever corrected one. Removing it froze every position while the total above
it stayed live, which is a page disagreeing with itself about money. Observed as
1 USDC moved between two watched pages: the sender's "Wallet balance" sat at
3.7552 until F5.

What made it safe the second time is that a position is now addressable and
published - `pq-<pid>`/`pv-<pid>`, `positions` in the payload, and a handler
carrying the figure up to the `.position`'s own `data-value`. Narrowing this
again without all three is how the same bug comes back.

Note that the inline comment described the fingerprint as `<counter>:<digest>`
long after it had grown a third part. It is `<counter>:<assets>:<positions>`;
`_digest` and `_positions_digest` are the authority.

### The reload cooldown

Reported 2026-09-18 as "it took 60 seconds and an F5", which is this constant to
the second. The stamp lives in the session, so it survived the tab being closed:
a reader who was told to reload, closed the window, transacted and came back was
refused the reload they now genuinely needed, and sat on stale rows until the
clock ran out.

### `_log_reload_decision`

Written because a reader reported a page reloading within seconds of being
opened and nothing recorded which two fingerprints disagreed, so the cause could
only be reasoned about. That is how a day went on the previous live-page
detector; see the host's `live-log-two-pages-one-prefix` note.

### `_page_key`

**`force_bundle=False`.** Hashing a single address asks for a key nothing
writes, and the failure has the worst possible shape: the poll still runs and
still heartbeats, so the engine goes on re-pricing the page every block while
every response is a 204 - a live indicator over a page that never moves, with
nothing logged anywhere. A bundle worked throughout, because both sides hash
those.

---

## inhouse/alerts/

### `models.AlertRule.subject`

Widened from 16 to 32 because `asa_price_percent` is 17 characters. A choice
field costs nothing for the width, and running out again would mean another
migration for a name.

### `models.PushSubscription.user_agent`

Kept only so a reader can tell two browsers apart in the settings list. It is
never parsed to decide behaviour — `alerts.js` asks the browser what it can do.

### `forms` — why an edit re-arms

`last_value` describes a comparison against the *previous* threshold. Carried
across an edit it makes a rule fire on the difference between two rules rather
than on a crossing: move a "falls below 100" to 50 while the last reading was
90, and the rule is suddenly on the other side of its own line through no
movement at all. An edited rule therefore behaves like a new one, which is also
what the reader means by changing it.

### `forms` — why an edit spends no slot

Counting the rule being edited refuses every edit made by a reader at their
limit — the reader most likely to want to change a rule rather than add one, and
with no way to see why the form kept saying they were full.

### `views` — `priceusdc` is ALGO per USD

It is how much ALGO one dollar buys, about 4 when ALGO is $0.25. The name says
the direction because calling it "algo_usd" is how this widget came to convert
it backwards in three places. Nothing converts a threshold with it any more; it
is there so the modal can show the reader the other currency.

### `views` — publishing on delete

A rule stores the page it was made from, and the modal lists every rule a reader
keeps rather than only the ones belonging to the page they are on. Publishing
the view's own bundle would leave the real page in `lvr` with no rules and take
one out that still has some.

### `display` — naming a threshold in the reader's currency

Thresholds used to be converted to ALGO when the rule was written, so a dollar
threshold was shown back as an ALGO figure the reader never typed.

The holding subject used to repeat the unit, which read "My ASASTATS holding
rises above 1,000,000 ASASTATS". The subject already names the asset.

### `evaluate` — depth is attached at the moment a rule fires

An asset that is deep today can be thin next month, so a rule cannot carry its
depth. A price out of a shallow pool moves several percent on one swap and back;
telling the reader what a trade could absorb lets them judge it. See
`notifications/DESIGN.md`.
