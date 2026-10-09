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

## inhouse/liverefresh/views.py (timeout wrap, 2026-09-29)

2026-09-29: Wrapped `LiveRefreshView.get()` (inner renamed `_get`) and `LiveRegroupView.post()` (inner `_post`) to catch `redis.exceptions.TimeoutError` and `django_redis.exceptions.ConnectionInterrupted`, returning `HttpResponse(status=204)` instead of raising through Django's exception handler. The 204 tells htmx to leave the page unchanged; the next poll asks again. The `CONNECTION_POOL_KWARGS` `socket_keepalive` addition (see `frontend/website/config/settings/production.py`) reduces the timeout surface; this wrap ensures an occasional miss never becomes an Internal Server Error or changes the `500.html` title.

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

### `evaluate._record_readings` — one write a pass, not one a rule (2026-09-27)

Both evaluators wrote every rule they looked at, one `UPDATE` each, because a
crossing is "past the line now, not past it before" and so `last_value` advances
whether or not the rule fired. That is the whole cost of a call that happens on
nearly every block, per page, for ever.

Measured on this machine, median of three warmed runs, `evaluate_page` against rule
count:

| rules | one save each | one bulk write | |
|---|---|---|---|
| 1 | 8.2 ms | 7.0 ms | |
| 2 | 12.5 ms | 7.7 ms | −38% |
| 5 | 31.9 ms | 9.2 ms | −71% |
| 10 | 51.1 ms | 11.5 ms | −77% |
| 25 | 134 ms | 19.8 ms | −85% |
| 50 | 279 ms | 37.9 ms | −86% |

Production's own figure for the whole request is 25.77 ms mean over 92,365 calls
(`nginx` logs `$upstream_response_time` on that vhost), so at today's ~2.5 rules a
page this is worth about a fifth of it, and at a Professional's twenty-five it is
most of it. The per-rule cost was the *dominant* term, which is why this is the
refinement worth having and batching the webhook is not — see
`post-deploy/alerts-tier-analysis.md`.

**`auto_now` does not fire for `bulk_update`.** Django applies it in `Model.save`,
so the helper sets `updated_at` itself; without that a row would keep claiming it
had not changed since creation while its `last_value` moved every block. A test
pins it, because nothing else would notice.

Two tests pin the write count rather than the timing — one per evaluator — since a
timing test on this hardware would be a flake generator and the count is the thing
that actually has to hold.

### Why the webhook is not batched

The engine posts `{"page": page}` once per page per block, inside `_live_page`, so
the pass waits for the website on every block for every rule page. One POST
carrying every page that moved would turn twenty requests a block into one and
twenty waits into one, for about thirty lines on each side.

**The measurement says not yet.** At 25.77 ms a call, one page notified every block
is 13.7 minutes of worker time a day, and the largest tier's twenty pages is 1.5%
of the site's request capacity (13 gunicorn workers). There is also nothing to
batch at today's ~1.8 pages a block. And it cannot be rolled out without
coordination: a new engine sending `pages` to an old website would have its calls
refused as "No page named", so the website has to accept both shapes a deploy
before the engine starts sending the new one. Recorded here so the design does not
have to be rediscovered when it is worth it.

### `tiers` — three tables, because there are three costs (2026-09-27)

Alerts were Asastatser and up, five rules, every subject. They now open to every
authenticated reader on the half that costs nothing, which is what advertises a
feature nobody outside the paid tiers had seen.

| tier | rules | subjects | pages |
|---|---|---|---|
| authenticated, no subscription | 2 | price only | 0 |
| Intro | 5 | price only | 0 |
| Asastatser | 5 | all six | 1 |
| Professional | 25 | all six | 5 |
| Cluster | 50 | all six | 20 |

**Why the split falls there.** Measured 2026-09-27: the per-asset half is 288
website requests a day for every asset and every reader *together*, because
`price_watched_assets` asks "who cares about this asset" once per asset. The
per-page half is about 29,000 a day **per page**, for ever, because the rule keeps
the page in `lvr` and the live pass values it every block whether or not anybody
is looking. Two rules on an obscure asset cost two cache reads every five
minutes; one portfolio rule costs three to four minutes of engine CPU a day and a
permanent subscription. `post-deploy/alerts-tier-analysis.md` has the measurements.

**`ALERT_PAGES_PER_TIER` is new because the rule count bounds the wrong
quantity.** Twenty-five rules on one page cost what one does; twenty-five rules on
twenty-five heavy bundles is 25,575 holdings against a 20,000-holding budget, and
`_live_pages` admits rule pages *ahead* of paying live-refresh readers - it passes
`paid | rule_pages` and walks them first. Nothing stopped one Professional
subscriber shedding every other reader. The numbers match the `liverefresh` bands
1 / 5 / 20 deliberately: the same quantity, bought twice. They are still written
out separately, because an alert page never expires while a watched address stops
costing anything when the tab closes.

**The gate is on the subject, not only on the count**, and it has to be: a count
cannot say "two rules, but only of these kinds", and `_live_pages`' invariant that
`lvr` is a subset of the paying readers is what would break.

### How the restrictions are presented

Four surfaces, and the principle is the one this file already had: the gate is on
the control, and below the tier the control is a link to the plans rather than a
dead input.

1. **The whole-panel upsell** in `modal.html` — "Alerts are available from the
   Asastatser tier" — is what this retires for authenticated readers. The branch
   stays for a tier that keeps none; no current one reaches it, and a patched
   table is how both test suites still cover it.
2. **The subject picker is rendered short**, filtered in the view, and
   `.alerts-tiernote` beneath it names the missing half: *"Portfolio alerts — your
   total, a holding, what a holding is worth — come with Asastatser."* A short list
   on its own reads as a small feature; the note is what makes it an offer.
   `alerts.js` mirrors the subject lists to decide which *fields* to show and never
   which subjects a reader may pick, so the filtering has to be server-side.
3. **The existing count line** now carries real numbers for a free reader, so the
   allowance reads as an allowance rather than as a broken control.
4. **`.alerts-pages`** shows the page cap before it is met. A cap a reader only
   ever meets as a rejection is a cap they experience as a bug.

Both refusals name what they buy rather than only saying no, and both surface in
the panel's existing `.alerts-error` paragraph.

### `population.publish_page` — a price rule must not publish its page (2026-09-27)

`publish_page` asked `filter(address=address, active=True).exists()`, which is
subject-blind, while the form stores `address` on **every** rule including a price
one. So an `asa_price` rule written from an address page put that page into `lvr`,
and the engine's live pass then valued it every block for ever — to answer a
question the periodic price task answers, and which `evaluate_page` immediately
skips (`SKIPPED` holds both priced subjects).

Measured on 2026-09-27, that mistake is not small. From the day's nginx log:

    22,493  POST /widgets/alerts/repriced      ~2,400 an hour
       112  POST /widgets/alerts/priced        ~12 an hour = the 5-minute crontab

At 1,333 blocks an hour, one page in `lvr` is about **1,200 website requests an
hour, 29,000 a day, permanently** — each a Django request, an indexed query and an
`UPDATE` per rule — plus 0.31 ms per holding per block in the engine and a full
account read every 60 blocks. The whole per-asset half costs 288 requests a day
**for every asset and every reader together**.

It now filters on `models.PAGE_SUBJECTS`, which is the *complement* of
`PRICED_SUBJECTS` rather than a second enumeration: a subject added later needs a
page until somebody says otherwise, because a forgotten entry that way costs a
page valued for nothing, where the other way round it is an alert that silently
never fires.

This also unblocks price-only alerts for the tiers below Asastatser. Until it
landed, "price alerts are the cheap tier" was false — a free price rule would have
cost exactly what a portfolio rule costs. See `post-deploy/alerts-tier-analysis.md`
for the tier table and for the two exposures it leaves open: `lvr` pages are
admitted *ahead* of paying live-refresh readers (`_live_pages` passes
`paid | rule_pages`), and the per-tier cap counts rules where the cost is per page.

---

## inhouse/alerts/static/alerts/alerts.js

### Module

**Why htmx plus a native `<dialog>`.** Almost everything is htmx: the modal is
fetched by the control, and creating or removing a rule swaps the panel the
server re-rendered. What is left for script is the part htmx has no opinion
about — a native `<dialog>` has to be opened by `showModal()`, and which fields
a subject needs is a question about the form rather than about the server.

**Subject lists mirror the server.** `ASSET_SUBJECTS`, `PERCENT_SUBJECTS` and
`UNITLESS_SUBJECTS` duplicate `models.ASSET_SUBJECTS`, `models.PERCENT_SUBJECTS`
and the inverted `models.CURRENCY_SUBJECTS`. A percentage is a proportion and
an amount is a count of the asset itself: "I hold more than 1,000 ASASTATS" is
true whatever an ASASTATS is worth. Neither has an ALGO/USD choice to make.

### `syncFields`

**Both fields stay mounted.** Removing and re-adding them would lose what the
reader had typed when they looked at another subject and came back, and would
need a request to put them back.

### `isApplePortable`

**Used only to choose the wording**, never to decide whether push works — that
is `supportState` below, and it asks the browser rather than reading its name.
A user agent is a claim; `PushManager` is a fact.

iPadOS 13 and later report themselves as "Macintosh", so the touch points are
what tell an iPad from a Mac. `navigator.platform` would be the obvious test
and is deprecated.

### `supportState`

**Feature detection first, and that is the whole design.** iOS Safari exposes
`PushManager` only to a site installed on the Home Screen, so its absence is
the same signal there as it is in any browser that cannot do push at all — and
asking the browser is right for every engine, including ones nobody has thought
to sniff for.

The user agent is consulted afterwards, and only to pick a sentence: "add this
to your Home Screen" is something a reader can act on, and "this browser
cannot" is not.

### `showSupport`

**The copy is in the template, not here.** The script decides which sentence is
true; where sentences live is a question about editing them.

### `vapidKeyBytes`

The key is published as base64url because it travels in JSON; the Push API
takes bytes. There is no browser helper for this, which is why every push
implementation carries these six lines.

### `markEnabled`

**The warning and the button label are server-rendered from
`subscribed_browsers`, which was false when this page was built.** Saying
"This browser is on." in the status line while the paragraph above still read
"No browser is set to receive these" left the modal contradicting itself, and
the button still inviting the reader to do what they had just done.

Only the warning inside this block is removed. The other `.alerts-warning` on
the modal belongs to a deployment that cannot send at all, and no button reaches
this code in that case.

### `enablePush`

**Four things that can each say no**, and the reader is told which: the browser
may not support push, they may refuse the prompt, the worker may fail to
register, or our own endpoint may reject the subscription. A single "something
went wrong" would leave them with no idea whether to try again.

**Not an error, and not retried.** A refusal is an answer, and a browser will
not prompt again anyway — so saying where to change it is the only useful thing
left.

### `handleSwap`

**`event.target` is not the swapped content.** htmx 4 fires this on the element
that made the request — the *button* — and names the region it replaced in
`detail.ctx.target`. Reading `event.target` therefore searched inside the
button, found no dialog, and left the modal sitting in the document unopened: a
control that fetched everything correctly and looked broken. The jest suite
could not see it, because it calls `openModal` directly; only a real browser
fires a real htmx event.

**Only these two swaps are acted on.** Other widgets swap fragments into this
same page all the time — live refresh does it every block — and reopening the
dialog on one of those would put the modal back in a reader's face after they
closed it.

**A create or a delete replaces the panel by `outerHTML`, which leaves
`ctx.target` pointing at the element that was replaced** — detached, and useless
to sync. It still carries the class, so the live panel is looked up in the
document and the detached one is only used to recognise the swap. By class
rather than by id, because that is what `syncFields` itself works from and what
the jest fixture and the template are guaranteed to agree on.

### `chooseUnit`

**The hidden input is what the form posts.** The buttons are the visible state
and `aria-pressed` is what a screen reader is told; neither is what the server
reads, so they cannot disagree with it.

### `trim`

A threshold of 0.0000123 is an ordinary ASA price, and `toFixed(2)` would show
it as 0.00 — a reference figure that says the asset is worthless.

### `currentFigure` / `showCurrent` / `suggest`

**A threshold is only meaningful next to the current value**, and a reader had
no way to see one without leaving the modal. Shown rather than filled in: a
threshold equal to the current value fires on the first wobble past it, because
a rule arms on its first reading and then triggers on any crossing. The
suggestion offered beside it is offset for that reason.

Above for "rises above" and below for "falls below", because the reader has
already said which way they are watching; offering a threshold on the wrong side
of the price would be offering a rule that fires immediately.

**Never over what the reader typed.** The field is written only while it is
empty or still holds exactly the last thing written here, which is what
`data-suggested` records. Changing the subject, the asset, the direction or the
unit re-offers; typing one character ends it for good.

Only the portfolio total is known here. An asset's price is not — the page
publishes the totals, not every asset's own price — so an asset subject shows
nothing rather than something borrowed from the wrong figure.

### `syncCount`

**The swap replaces the modal, and the badge is not in it.** Creating or
removing a rule re-renders `#id-alerts-panel`; the count sits out in the toolbar
beside the button, so nothing touched it and it went stale the moment a reader
added their first rule — the modal said "4 of 5 left" over a button that still
said none.

Read off the panel rather than counted here: the server already did this
arithmetic once, and a second place doing it is a second place to get it wrong.

### `placeToolbar`

**It renders where the partial lands, which is not where it belongs.**
`_swap_entry.html` arrives near the top of the page, so without this the button
sits in a strip of its own above the heading while Sweep dust — which does
exactly this — is down in the row with Historic data and CSV export. Two
controls of the same kind, in two different places.

The same slot the sweep uses, and appended after it, so the order is stable
rather than a race between two scripts.

**It is revealed here, and rendered hidden.** Moving something the browser has
already painted is a visible jump: the button appeared in a strip above the
heading and then hopped down into the action row on every page load. The partial
marks it `hidden` and this is what takes that off, so the first time a reader
sees the button it is already in place.

Revealed even when there is nothing to move — a page with no slot, or a second
call after an htmx swap — because a toolbar that stays hidden is worse than one
in the wrong row.

### `chooseAsset`

**The hidden field is what the form posts**, so nothing is chosen until this
runs: a reader who types "USDC" and presses Add without picking a row submits no
asset, and the form tells them to choose one. Typing is not choosing, and an id
guessed from a partial match would be the wrong asset rather than no asset.

**The unit travels with the id.** The notification is built server-side, where
this widget has no asset lookup, so "USDC" has to be stored when the reader
picks it or the alert says "an asset 31566704" for ever.

**The row is the only place this price exists.** `swap_assets` ranks assets and
hands back a USD price with each; nothing else in this modal knows one, so it is
kept here for `showCurrent` to convert.

### `resolveAsset`

**The reference price had one source and it was the search results.** A row
carries `data-usdc-price`, so picking an asset out of the picker gave
`showCurrent` something to show — and the two paths where the asset arrives
already chosen gave it nothing: editing an existing rule, and a form that came
back rejected. Exactly the two moments a reader is looking at a threshold they
are trying to adjust.

The id is all a bound form carries, so this asks the same endpoint the picker
asks, by id. Reusing `swap_assets` rather than adding an endpoint is what keeps
this widget's `capability = "public"` and its empty `engine_endpoints` honest —
the picker already calls it, and every reader who may keep an alert may search.

**Silent on every failure.** A reference figure is an aid; a modal that reports
its absence would be worse than one that shows nothing.

**Only an exact id match.** The endpoint ranks by name and unit too, so a loose
match would hang another asset's price off this rule.

### `window.asastatsAlerts`

**Published so the page can tell this script is listening.** The tag that loads
this file rides in `_swap_entry.html`, which is itself swapped in — so it is
fetched asynchronously, and for a moment the control is on the page while
nothing is listening for the swap it triggers. A press in that window fetches
the modal and leaves it closed, which is a reader pressing a button that does
nothing.

The same shape as `window.asastatsWallet` and `window.asastatsSwap`, and read
for the same reason: something that arrives late has to say when it has arrived.

---

## inhouse/liverefresh/static/liverefresh/liverefresh.js

### Module

**The subscriber half of "Auto-refresh".** The free half reloads the page. This
does not: it asks for the fragments the block changed and lets htmx swap them
out of band, so scroll position, open sections and filters all survive. That is
the whole reason the idle guard the free half needs does not apply here —
nothing is thrown out from under the reader, so there is nothing to wait for
them to stop doing.

**The poll is also the subscription.** Serving it is what tells the engine this
page is being read; there is no subscribe and no unsubscribe to keep in step
with a reader who closed the tab. They stop polling, the heartbeat expires, and
the engine stops re-pricing the page.

**Nothing to swap, nothing to ask for.** The band partials live in the dynamic
layout; the legacy one renders the same figures without the ids the out-of-band
swaps address. Polling there would apply nothing while still holding an `lvx`
subscription, which costs the engine a re-price of this page every block for a
reader who would see no difference.

**Correction, 2026-10-01.** The classic layout now carries stable position-value
targets as well, so its consolidated figures can be refreshed from the same live
position payload. The guard still requires one of the two band targets.

Asked of the page rather than told by the server, so that a layout gaining the
partials starts working without anything else being changed — and one losing
them stops, rather than quietly polling into the void. Either layout's band
counts. The dynamic one renders `#id-band-total` and the classic one
`#id-band-classic`; a reader is on one or the other, and a page with neither is
one the swaps cannot reach.

**No longer read once.** The reload stopped being the only answer. A regroup
replaces venue groups in a document that stays put, so the page is carrying
different positions than it was rendered with and this has to move with them —
see `regrouped`. Left at the rendered value it would ask for the same regroup
every three seconds for ever.

### `poll`

**Hidden past the grace period stops the poll entirely**, rather than polling
on quietly. Every polling tab holds a subscription the engine re-prices on
every block, and a tab nobody has looked at for five minutes is the clearest
case of work with no reader.

### `spent`

**Handing back to the free timer is the point.** A page that simply stopped
would leave the reader with neither the live updates nor the 60-second reload a
non-subscriber gets, which is worse than never having had it — and
indistinguishable from the feature being broken.

`address.js` stands its own timer down whenever `#id-liverefresh` is on the
page, and asks every tick rather than once, so removing the marker is the whole
handover. No coordination between the two scripts beyond that.

### `showLeft`

**The badge ships in the non-cached partial and is moved here.** The address
page is `cache_page`d across readers, so a balance rendered into it would show
whoever warmed the entry to everybody else — the same trap the Dust Sweep button
hit. Rendering it per-reader and relocating it keeps the figure private while
letting it read as part of the toolbar.

Hidden again once the control is disarmed: a number that keeps sitting there
while nothing is being spent invites the reader to watch it not move.

### `humanize`

Minutes below an hour and whole hours above it: a badge counting seconds down
beside a page that updates every block is two things moving for no reason, and
the number is an allowance rather than a stopwatch.

### `rememberExpanded` / `settlePosition`

**Two things travel with a position's value and neither is inside the element
being replaced.**

`aria-expanded` is live state: `dynamic.js` toggles it, and the `.dist` panel it
controls is a *sibling*, so the panel survives a swap that resets the control.
Without this a reader watching an open breakdown would see the button claim
closed over a panel still showing.

`data-value` sits on the `.position` itself and is what `toolbar.js` sums for
every category total and for the allocation band. A fragment cannot reach an
attribute without replacing the element holding it, so the page's headline
arithmetic would drift away from its own rows — the exact failure that made
narrowing the reload a mistake in the first place.

**Once per response, not once per element.** htmx 2 bracketed every out-of-band
element with `htmx:oobBeforeSwap`/`oobAfterSwap` and this ran per element. htmx
4 has neither event: `htmx:before:swap` carries the whole task list before
anything is swapped, and `htmx:after:swap` fires once all of them are in — so
the same work is two passes rather than 2N events.

Both still fire before the whole-response event `toolbar.js` repaints on, which
is the ordering that has to survive the port. Doing it later would repaint from
the figures this is here to correct.

**`true` is the capture phase, and it is load-bearing.** Under htmx 2 this ran
on `oobAfterSwap`, which fired during the swap and so always preceded the
whole-response event `toolbar.js` repaints on. In htmx 4 both are
`htmx:after:swap`, and bubble-phase listeners run in registration order — which
puts `toolbar.js` first, because it is loaded with the page while this arrives
later inside the swapped `_swap_entry.html` partial.

That order is the bug this whole mechanism exists to prevent: the toolbar would
recompute every category total and the allocation band from the `data-value`
attributes *before* the line below corrects them. Capturing on an ancestor runs
before any bubble listener on it, whatever registered first, so the ordering no
longer depends on which script loaded when.

### `regroup`

**The one thing the poll cannot work out for itself.** A position opening or
closing changes a row inside a row the page already has. The server knows the
reader's fingerprint, which is a digest and not a list, so it can tell that the
positions moved and not which ones — and the answer is a venue group, which the
diff has no way to describe. So it asks, and this replies with one token per
position: `<asset id>:<pid>`.

The asset is sent rather than parsed out of the pid on the server, because a
pid's internals belong to `api/position_id.py` and this already knows the asset
— `data-owner` is on every row for the toolbar's sake.

Ambiguous positions carry no `data-pid` at all, so they are absent from this by
construction and the server excludes them to match. Their groups keep being
corrected by the reload, as they always were.

**One at a time.** The trigger arrives on every poll until the page has caught
up, and a regroup takes longer than the three-second interval, so without this
a slow answer would stack three or four requests all sending the same stale pid
list.

### `regrouped`

**The fingerprint the page has now caught up to.** Without this the next poll
compares the fingerprint the page was *rendered* with, finds it stale, and asks
for a regroup again — every three seconds, for ever.

A group in the venue list whose asset was just re-rendered is the old copy of a
group the page now has twice. Dropping the moved copies and asking the toolbar
to lay itself out again is what makes the swap safe in either mode.

**Sent explicitly, because nothing else here would.** This is the only POST the
widget makes, and it is made by `htmx.ajax` from a `<span>` rather than
submitted from a form — so there is no `csrfmiddlewaretoken` field to pick up
and no `hx-headers` on an ancestor to inherit. Django refused it outright, and
the browser test is what found that: every unit test around it passed, because
none of them goes through the middleware. Same read as the swap and Dust Sweep
widgets do it.

---

## inhouse/dustsweep/static/dustsweep/dustsweep.js

### Module

**The loop is the whole design.** Ask the engine what to sign next, sign exactly
that, then ask again against whatever the chain now says. No plan held on
either side, so nothing to resume, invalidate, or order — "what is closeable
now" is just current state.

**The part that matters: inspecting what we are asked to sign.** A close-out
group is up to sixteen transactions that a user approves with one click, and
`asset_close_to` moves an entire balance. That is precisely the shape the
router contract's `_assert_group_is_clean` refuses to be bait for — and the
contract cannot help here, because these groups contain no application call for
it to refuse.

So the group is decoded and checked **in the browser, against the plan that
described it**, before it reaches the wallet. Not because the engine is
expected to lie, but because "the engine said so" is the only other assurance
on offer, and a control that consists of trusting the thing it is meant to
check is not a control. Concretely this catches a response whose human-readable
description and actual bytes disagree — which is what a compromised or confused
engine, a cached answer or a mangled proxy would produce.

There is no msgpack decoder on this page and pulling algosdk in for one is a
large dependency for a small job, so `decodeMsgpack` below reads the subset an
Algorand transaction actually uses. Addresses are compared as raw bytes, which
needs base32 only — encoding one back to text would need SHA-512/256, which
WebCrypto does not offer.

### `MAX_CLOSE_OUT_FEE`

**Expressed as a fraction of what a close-out returns, deliberately.** The
number happens to be ten times the protocol minimum of 1,000, which is the
headroom a congested network needs — the engine builds these from the node's
suggested parameters, and a bound pinned at the minimum would refuse honest
groups. But the property worth keeping is the other one: at the limit, a
close-out still returns nine tenths of the minimum balance it releases.

Writing it this way makes a whole-group rule unnecessary rather than merely
redundant. A group of `n` close-outs releases `n * HOLDING_MINIMUM_BALANCE`
and can pay at most a tenth of that, so "the fees exceed what the group
recovers" is unreachable by construction and there is nothing to check for it.
Raise this above `HOLDING_MINIMUM_BALANCE` and that stops being true.

### `MAX_GROUP_FEE`

**The contract's number, mirrored rather than chosen.** `MAX_GROUP_FEE` in
`router_app.py` is 1,000,000 and `_assert_group_is_clean` totals the group
against it. Picking a different one here would mean refusing groups the chain
accepts, or accepting groups it will reject — both worse than being a copy.
Raise it there and this must follow, which is what the check named after it in
`verify-sweep.sh` is for.

The seven groups in the audit's `evidence/` measure the headroom: the dearest
thing that has actually executed is a 13-transaction swap paying 71,000, and
the three convert groups pay 43,000 to 60,000. The ceiling is fourteen times
the worst of those, so it bounds a runaway without coming near honest traffic.

### `ROUTER_APP_ID`

**A default, not the only source.** The page supplies `data-router-app` and
that wins; this is what the check falls back to, so a missing attribute cannot
silently disable the rule. What matters either way is where it does *not* come
from: the plan response. An app id the engine supplied would make this check
agree with whatever the engine wanted, which is `S2` again.

The contract has been redeployed twice already — `3688554446` is retired and
`3689591968` superseded — so this number has a lifetime. When it changes, a
conversion refuses until this is updated, which is the safe direction but a
real outage; the `data-router-app` override exists so a deployment can move
first.

### `BUDGET_ONLY_SELECTORS`

`_assert_group_is_clean` runs from 13 of the contract's 15 entry points.
`verify_discount` and `pool_budget` are the exceptions — permissionless, no
state, no inner transactions — and the contract's own reasoning for exempting
them is that they ride alongside a `route` call which sweeps the group.

That reasoning is why they cannot count here. A group of `pool_budget` plus one
hostile transfer calls the router, so a rule that asked only "does this group
call the router?" would pass it, and the guard the call was supposed to bring
would never run. So the check looks for a router call that is *not* one of
these.

Computed from the method signatures rather than read off a group:
`verify_discount(byte[])void` and `pool_budget()void`, SHA-512/256, first four
bytes. `verify-sweep.sh` pins both against the contract.

### `planLines`

**Both checks below take `described` from an HTTP response, so its shape is not
theirs to assume.** They used to reach straight for `(described || []).forEach`,
which is fine for an array and throws for everything else — a string, a number,
a bare object. `closeOutProblems` already guarded the *group* with
`Array.isArray` and did not guard the description, and that asymmetry was the
whole of it.

Found by the property tests in `dustsweep.property.test.js` on their first run.
The example suite covers `undefined` and `[]`, which are the two ways an
*array* can be missing, and no way for the field to be something else.

An unreadable description yields no expected targets, so every transaction then
fails the "was not listed" rule and the group is refused. Degrading to a
refusal is the safe direction and the one the rest of this file takes.

### `CREATOR_LOOKUP_TIMEOUT`

**A hang was the one failure that neither refused nor accepted.** Every other
way `assetCreator` can fail already produces a refusal, but algosdk v3's client
sets no timeout of its own, so an unresponsive node left the reader on a
spinner with no signature prompt and no error — the sweep neither happening nor
visibly failing. Ten seconds is far past a healthy round trip and short enough
that the refusal arrives while the reader is still watching.

### `withTimeout`

Null rather than a rejection deliberately: the caller already treats "no
creator" as a refusal, so a timeout joins the unreachable node and the
unreadable asset instead of opening a fourth path.

### `isForfeit`

**One function because two callers must never disagree.** The safety of the
whole forfeit check rests on an invariant that spans both of them: a
transaction may close to an address other than the sweeper's *only* when this
returns true, and this returning true is *also* what sends the destination to
the chain to be confirmed. `closeOutProblems` picks the expected target with
it; `forfeitTargetProblems` picks what to look up with it. Written out twice,
the two could drift — a later `> 0`, or a `disposition` field consulted in one
place — and a forfeit would quietly stop being confirmed against anything.
That is `S2` reopening silently, with every test still passing, which is why
the predicate has a name.

It pairs with `planLines` rather than repeating its work: that one decides
which lines are readable at all, this one decides what a readable line means.

### `closeOutProblems`

Structural, not advisory: each rule refuses a transaction shape rather than
judging an amount, so passing all of them means the group can do nothing except
empty the holdings the plan listed into the targets the plan named.

The rules, and what each one is stopping:

- **`axfer` only, never `pay`.** A payment's `close` field drains the entire
  ALGO balance to whoever it names. It has no legitimate place in a sweep, and
  it is the single most damaging thing that could hide in a batch of sixteen.
- **zero amount.** `asset_close_to` moves the whole balance by itself, so a
  sweep never needs to name an amount — and one that did could send tokens
  somewhere the close-out then does not.
- **sender and receiver are both the holder.** The transfer half is a no-op and
  only the close is doing anything.
- **no rekey.** A rekey hands the account away permanently. It is the reason
  `_assert_group_is_clean` exists.
- **the close target is the one the plan named for that asset**, matched by
  asset id — self for an empty holding, the asset's creator for a forfeit. A
  group that closes a *different* asset, or the right asset to a different
  address, fails here even though it is a perfectly well-formed close-out.
- **the fee is bounded**, per transaction. Nothing else bounds it: the engine
  sets it from the node's suggested parameters and the bridge preserves whatever
  arrives. Mainnet will take a fee up to the account's entire spendable balance,
  so a sweep that emptied an account without moving a single token was a valid
  group. There is deliberately no whole-group rule to go with this one;
  `MAX_CLOSE_OUT_FEE` explains why it would be dead code rather than a second
  line of defence.

**What this function cannot do, and `forfeitTargetProblems` does.** For an
*empty* holding the expected close target is the connected account, which is
known independently of the response. For a *forfeit* it is
`described[].creator`, which arrives in the same payload as the bytes — so a
response that is internally consistent passes, whatever address it names. That
was the audit's `S2`. The rule below still earns its place, because it catches
bytes that disagree with what the reader was shown; but the forfeit destination
is confirmed against the chain, separately and asynchronously.

### `forfeitTargetProblems`

**This is the half of the check that does not come from the response.**
`closeOutProblems` compares a forfeit's `asset_close_to` against
`described[].creator`, and both halves of that comparison arrive in the same
JSON: an engine that names an address it controls in `holdings` and closes to
it in `transactions` is internally consistent, so the check passes. That was
the audit's `S2`, and it defeated the stated purpose of the whitelist — a
control that consists of trusting the thing it is meant to check.

So the creator is resolved from the chain instead, through the wallet bridge's
own algod connection, and the transaction is compared against *that*. One
lookup per distinct asset, all issued together, and only for holdings
`isForfeit` says still carry a balance — an empty holding closes to the
connected account, which was never in doubt. That predicate is shared with
`closeOutProblems` rather than repeated, because a forfeit that stops matching
it here stops being confirmed against anything.

**It fails closed.** A bridge too old to expose `assetCreator`, an unreachable
node, an asset whose parameters cannot be read, and a node that never answers
at all — see `CREATOR_LOOKUP_TIMEOUT` — all produce a problem rather than a
pass. Refusing to sign costs a reader one sweep; signing an unverifiable
forfeit costs them the holding. Empty holdings are unaffected either way, and
they are where most of what a sweep recovers is.

**One round trip, not one per asset.** The lookups are independent and already
at most one per distinct asset; awaiting them in the compare loop made a group
of sixteen forfeits wait sixteen times the node's latency before the wallet
prompt opened. A rejection folds to null here so the "could not be confirmed"
branch below stays the single refusal path.

### `routedGroupProblems`

**`_assert_group_is_clean`, mirrored in the browser.** The contract already
refuses a rekey, a `close_remainder_to`, an `asset_close_to` and a group fee
over `MAX_GROUP_FEE`, over the whole group, from 13 of its 15 entry points.
That guard is real, deployed and immutable, and this is a copy of it rather
than a second opinion about it: mirroring cannot refuse a group the contract
would accept.

**What the copy buys is that it runs.** An assertion inside an application only
executes if the application is called, and nothing off-chain required a
conversion group to call the router. `signAction` chose whether to inspect a
group by reading `action.kind` from the same response that carried the bytes,
so a group labelled `convert` reached the wallet unexamined — by the widget,
which skipped it, and by the contract, which was never in the group to object.
That was the audit's `S6`, and it is the same shape as `S2` moved up a level:
`S2` was a reference value the engine supplied, this was the switch deciding
whether any checking happened at all.

So the rule is applied to the bytes, whatever the response calls them, and
`action.kind` stops being a security decision.

**Why the decoder is up to it.** It reads the msgpack subset a *close-out*
uses, and a routed group carries application calls — larger, and carrying
argument and foreign-asset arrays a close-out never has. Run over the 97
transactions in the audit's `evidence/`, every one of which executed on mainnet,
it decodes all 97: the tags they use are `fixmap`, `fixarray`, `fixstr`, `bin8`
and `uint16/32/64`, all of them already supported. A transaction that will not
decode is refused rather than skipped, so a tag that does turn up costs a
conversion instead of passing one through.

**The rule that puts the contract back in the group.** Everything above is the
hygiene half of `_assert_group_is_clean`, and hygiene is not what a conversion
needs checking for: a plain transfer of the whole balance to a stranger carries
no close, no rekey and an ordinary fee. What refuses that is the router's own
logic — the input proven spent, the co-signed floor, the pairwise-distinct
assets — and none of it runs unless the router is called. This is the audit's
`S7`: mirroring the guard duplicated the half that was already cheap and left
the half that was load-bearing.

Totalled rather than checked per transaction, for the reason the contract
gives: the total is what a signer loses, and it is the bound that survives the
builder redistributing fees across the group, which it already does.

### `convertedInputProblems`

**`S8`'s Mitigation 1: bind the moved assets to what the plan described.**
`routedGroupProblems` asks whether a group is *hygienic* and whether the router
is in it to check it. It never asks whether the group does what the reader was
shown, because it is not given the plan — so a conversion described as "convert
BUSK, worth 0.0016 ALGO" could sell five thousand USDC and be accepted. The
close-out path refuses exactly that substitution ("closes asset N, which was
not listed"); this is the same rule for the other half.

**It does not close `S8`.** A compromised engine can still add a transfer
*alongside* a route, because that transfer moves an asset the plan does name.
What this stops is the substitution: the described trade being a different
trade. The audit is explicit that the two are separate and that this one is
worth taking on its own.

**Only what the connected account sends is judged**, and that is the whole of
the rule. A route's other transactions are the quote signer's authorisation and
the pools' payouts back to the reader; neither is the reader's to constrain,
and refusing them would refuse every honest group. Checked against the seven
executed mainnet groups in the audit's `evidence/`: in each, every transfer the
holder sends moves the *same* asset — the input, split one transfer per venue —
and the parts sum to exactly the holding the plan described.

**A separate function rather than another argument to `routedGroupProblems`.**
An optional parameter that silently disables a rule when a caller forgets it is
the exact failure this file has already had once — see `state`, where
`data-router-app` was assembled and then dropped. A missing call here is
visible in `signAction`.

### `DISPOSITIONS`

**`included` is the whole of the per-line policy**, and the asymmetry in it is
deliberate. Everything the engine could value is swept unless the reader says
otherwise; `unpriced` is the one disposition that starts *off*, because it is
the one where the engine is admitting it does not know what the token is worth.
Turning it on is the reader accepting that, line by line, which is the only way
an unvalued holding is ever given away.

`keep` has no entry: it is not actionable, so it carries no control at all
rather than a disabled one.

### `INERT`

**Deliberately a second map rather than `included: false` entries.** Anything
in `DISPOSITIONS` is *actionable*: the row grows a checkbox, and switching it
on puts the asset in `opted_in`. That is right for `unpriced`, which is a
holding the sweep could take if the reader vouches for it, and wrong for these
two, which the engine will refuse whatever the body says. A checkbox that
quietly does nothing is worse than no checkbox.

### `assetLabels`

**The id is shown, not just carried.** A unit name is not an identity — anyone
can mint a second "USDC" — and the asset id is the only handle a reader can
paste into an explorer to see what they are about to close out or give away. It
is also the fallback name: `_asset_facts` returns no unit for an asset whose
parameters could not be read, and a row labelled with nothing is a row nobody
can check.

### `destinationLabel`

**The audit's `S2` recommendation 2.** The row showed unit, id, badge, value
and reason, and never the address the tokens went to — so on the one
disposition that gives something away, the destination was the single fact the
reader was not shown. `forfeitTargetProblems` now confirms that address against
the chain, which is the control; this is the disclosure, and the audit is
explicit that it is a complement rather than a substitute. A reader who can see
the creator can compare it with the wallet prompt; one who cannot is trusting
two systems instead of checking one.

**Shortened, with the whole address kept for the title.** A 58-character
address on every line is why this was not done the first time. The short form
is enough to compare against a wallet prompt at a glance, and the full one is a
hover or a copy away.

Only a forfeit names somebody else. A close returns the holding to the account
it is already in, which is worth saying plainly rather than leaving blank —
"nothing leaves this account" is the reassurance a reader wants — and a
conversion has no close target at all, so it gets nothing.

### `choicePayload`

Only *deviations* from the default are sent, which is what lets the plan be
refetched after every signature without the reader's decisions being reset: a
holding that appears for the first time takes its default, and one they touched
keeps what they said.

The two lists are not mirror images. `opted_in` widens what the sweep gives
away and `excluded` narrows it, so a holding can only reach `opted_in` by being
unvalued and switched on, and can only reach `excluded` by being something the
engine would otherwise have swept.

### `visibleLines`

"sweeping" is the default view because a reader opening a sweep wants to see
what is about to happen, not an inventory. "all" exists so the holdings the
sweep decided to leave alone are still visible — a reader who cannot see why
their token was skipped has no way to tell "kept deliberately" from "missed".

### `partialGroup`

The wire format and the bridge's format are not the same thing, and it is
`swap.js`'s `AsastatsAdapter.buildSwapGroup` that says what the difference is:
JSON carries base64 and snake_case, `signAndSendPartial` wants decoded bytes
and camelCase. Written out here rather than borrowed, because the two widgets
ship separately and neither may import the other's module.

### `signAction`

**Both paths are inspected, and that is the fix for `S6`.** This used to inspect
only the close-out one, on the reasoning that a conversion carries a router
call the contract itself checks. Every honest conversion does. But `action.kind`
is a field of the same response as the bytes, so the engine chose which branch
ran — and a group labelled `convert` that contained no application call was
refused by nobody: not by this function, which returned early, and not by
`_assert_group_is_clean`, which cannot refuse a group that never calls the
contract. `routedGroupProblems` mirrors that guard here so the answer no longer
depends on what the response calls the group.

**Both bridge methods take decoded bytes, and this used to hand them the
base64.** `signAndSend(group: Uint8Array[])` passes each entry straight to
`decodeUnsignedTransaction`, which coerces a string array-like into one byte
per *character* — so a 340-character close-out arrived as 340 zero bytes and
msgpack read one complete object in the first of them:

    RangeError: Extra 339 of 340 byte(s) found at buffer[1]

which named neither base64 nor this widget. The conversion path had the same
fault in a second form, passing the whole JSON action where the bridge wants
three named fields, and would have failed its own way at the first signature.
Decoding is therefore done here, at the single point where the wire format
becomes an argument.

### `connectionSource`

**`asastatsWallet` first, and `asastatsSwap` only as a fallback.** Connection
state is a wallet fact; the sweep needs it and needs nothing else from the
swap. Reading it off the swap object is what made this button vanish for
readers whose swap bridge failed to start, and for readers whose page had no
swap on it at all.

The fallback stays because the wallet bundle and this widget ship from
different repositories: a deployment may carry a bundle older than this file,
and on one the sweep should keep working exactly as it used to.

### `sweepableAddress`

**A sweep is only ever offered for the account the wallet is connected to.**
Every other address is unofferable by construction: the group is signed by one
key, the wallet holds one active account, and a button for any other account
builds transactions that account cannot sign. The reader used to discover that
at the signature prompt.

Both halves of the question are asked here. `candidates` is what the server
knows — the reader's own addresses among those this page shows — and `active`
is what the browser knows. An account that is connected but not on this page is
not offered either: the sweep acts on what the reader is looking at.

### `summaryFigures`

`recoverable` is the minimum balance alone, net of fees — the certain half. The
planner subtracts them there (`sweep.py`: `(closes + conversions) *
HOLDING_MINIMUM_BALANCE - fees`). A close returns exactly 0.1 ALGO whatever the
token is worth, while conversion proceeds depend on quotes not taken yet, and
promising the uncertain half up front is how a sweep ends up having
under-delivered.

**Fees are shown, not folded away.** `summary.fees` was computed by the planner
and sent here from the beginning, and nothing rendered it: there was no number
on this screen that would have moved if every fee in the group had been a
thousand times larger, which is the reporting half of the audit's `S3`. It sits
beside what the sweep returns because the two are the same arithmetic.

**It reports; it does not verify.** Both figures are the planner's, and a sweep
spans several groups while this widget only ever holds the bytes of the next
one — so there is nothing here to check the total against, and a planner that
reported zero fees would render "0.00 ALGO" unchallenged. The row is honest
reporting, not a control: what bounds what a reader can lose is
`MAX_CLOSE_OUT_FEE`, applied to the bytes about to be signed. Read it as
telling a reader when an honest sweep is not worth signing.

### `degradedNotice`

**The evaluation outage is reported first, and says the more alarming thing**,
because it is the one a reader would otherwise misread as a fact about their
account rather than about the sweep. Somebody who sees three of their thirty
holdings offered needs to be told the sweep is degraded; being told only that
conversions are unavailable would explain the wrong half.

### `state`

**`routerApp` is a parameter rather than an assignment afterwards.** It used to
be one: `start` built a state, set `current.routerApp` on it, and then the open
handler replaced the whole object with a fresh `state()` before the modal was
ever shown. So `routedGroupProblems` was called with `undefined` on every
conversion any reader ever signed, fell back to the built-in `ROUTER_APP_ID`,
and `data-router-app` did nothing at all.

That is the escape hatch for a redeployment, and its whole purpose is to let
the deployment move before this file does — so the failure it was there to
prevent is exactly the one that would happen: the router is redeployed, the
built-in id goes stale, and every conversion is refused with "the group calls
no router method that would check it" until the JavaScript is updated. Safe
direction, real outage, and the mechanism to avoid it was disconnected.

Taking it as an argument is what stops the same omission recurring quietly: a
caller that forgets it now passes `undefined` visibly at the call site rather
than dropping a key from an object literal.

### `offerToConnectedAccount`

Only the address-page entry (`.dustsweep-toolbar`, one button whose account
this decides) is touched. The standalone sweep page lists the reader's
addresses as a directory with an account already on each button, and is not a
page they arrived at to read something else.

The toolbar is also moved into `#id-dustsweep-slot` when the page offers one,
so the button sits with Historic data and CSV export rather than above the page
in a strip of its own. Moved rather than rendered there: this markup arrives in
an htmx partial, because it is the one per-reader thing on a page whose cache
entry is shared, and the partial has one mount point.

### `boot`

**Not gated on the wallet bridge.** It used to be, and the modal then never
opened for anybody who had not already connected: `whenSweepReady` waits for
`window.asastatsSwap`, which ships with the wallet bundle and is absent in a
bare browser. Reading what a sweep would do is exactly the thing a reader wants
before connecting, so the gate belongs on the signature and nowhere else — see
`sign`.

## The alerts modal, four defects from the running site (2026-09-28)

Files: `widgets/inhouse/alerts/forms.py`, `views.py`, `display.py`,
`templates/alerts/_panel.html`, `static/alerts/alerts.js`, and
`static/css/input.css` in the host.

All four were reported by the user against the deployed modal. Three are bugs;
one is a question whose answer turned out to be in the wrong place.

### 1. ALGO could not be watched, because its asset id is 0

`clean()` tested `if not cleaned.get("asset_id")`. Asset 0 is ALGO — the one
asset every reader holds — so choosing it and pressing save answered "Choose an
asset to watch" about a rule that named an asset. `is None` is the test; the
field is already `IntegerField(required=False, min_value=0)`, so 0 was always a
value it accepted, and only the truth test refused it.

**The same defect twice**, and the second half is why this is worth an entry:
`_panel.html` labelled the picker button with
`{% if form.asset_id.value %}#{{ ... }}{% else %}Choose asset{% endif %}`, so
editing an ALGO rule showed "Choose asset" over a rule that had one. A falsy
id has to be handled in every place that asks "is one chosen", and a fix to the
validator alone would have left the button lying.

### 2. Editing a rule rewrote it

`AlertsRuleEditView.get` built `initial` with the subject, direction, threshold,
asset id and window — and **neither unit**. The consequences were not symmetric:

* `threshold_unit` missing meant the template's `|default:'algo'` won, so
  opening a `$500` rule and saving it stored **500 ALGO**. The reader changed
  nothing and the rule came to mean something else.
* `asset_unit` missing meant the hidden input rendered empty and `save()`'s
  `or ""` stored that, so the unit name the notification is built from was
  dropped on every edit — silently, because the sentence falls back to the id.

Both now come from the rule. `_settle_unit` deliberately stores the currency
without converting, which is what makes the first one a data loss rather than an
arithmetic error: nothing else on the row records what the reader meant.

### 3. The threshold input showed the column's scale

`threshold` is `decimal_places=10`, so an edit form rendered
`value="100.0000000000"` and a reader who had typed `100` was asked to edit ten
zeros. `display.py` already had this problem solved for *sentences* — its module
docstring names it — and the input was simply never wired to it. Now
`plain_threshold` reuses `_trimmed(amount, STORED_DECIMALS)`.

`Decimal.normalize()` is the obvious one-liner and is wrong here: it turns 100
into `1E+2`, which the input would post back and `DecimalField` would reject.
`_trimmed` renders with `:.10f` first, so an exponent is unreachable.

**The test was green through all of this.** It asserted
`'value="100.0000000000"' in html or 'value="100' in html` — an assertion
satisfied by both the bug and the fix. Tightened to the exact string plus
`assert "100.0000000000" not in html`.

### 4. The asset picker expanded instead of covering

The picker was an inline block under the button, inside `.alerts-panel`, which is
the modal's scrolling region. Opening it pushed the rest of the form down, and a
result list arriving pushed it further — so the Save button left the visible area
of a modal already capped at `min(40rem, 100vh - 4rem)`.

It is now the swap modal's shape: `position: absolute; inset: 0` over
`.alerts-shell`, which gains `position: relative`. The results list becomes
`flex: 1 1 auto; min-height: 0` and scrolls inside the sheet, so **the list's
length can no longer move anything behind it** — which is the property worth
having, rather than a bigger cap.

The markup stays inside `.alerts-asset-field` and does not move: `chooseAsset`
and `togglePicker` both scope to that field, and an absolutely positioned box is
not clipped by a scrolling ancestor that sits *below* its containing block, so
`.alerts-panel`'s `overflow-y: auto` does not cut the sheet off. The sheet gains
a head and a close button because it covers the button that opened it, and
`togglePicker` now restores focus to that button on close — hiding an ancestor of
the focused element otherwise drops focus to the body.

**A measurement, because the first assertion I wrote did not test anything.** I
asserted the picker's box was *inside* the shell's. It passed with the old CSS
too: `.alerts-shell` has `overflow: hidden`, so an inline picker never escapes
the card either. Measured in the browser, with `.alerts-shell` at 521px tall:

| | picker box | height |
|---|---|---|
| inline (before) | 406 → 493 | 87px |
| sheet (after) | identical to the shell | 426px of 426px |

So the test asserts the picker's box **equals** the card's, which is what "it is
a sheet" means and what fails on the old CSS. The containment version would have
been a test that could not fail.

### The 1-hour minimum window, which was the fourth question

`WINDOW_CHOICES` starts at one hour, and its note explains that as sitting above
"the measured sampling gaps - p50 five minutes, p90 68 minutes". Checking that
against what actually writes the two series:

* **Portfolio totals** are bucketed at `LIVE_TOTALS_HISTORY_TICK_SECONDS = 300`
  in the engine — one point per five minutes, deliberately, even though the live
  pass re-prices every block.
* **Asset prices** come from `core.tasks.price_alert_assets`, which is
  `@periodic_task(crontab(minute="*/5"))` — also five minutes, and its own
  docstring says five is a floor chosen for the reader rather than a limit of the
  data.

So both series are written at a five-minute resolution, and the p90 of 68 minutes
does not describe either of them today. What does justify a floor is
quantisation: `percent_move` compares against the newest point *at or before*
`now - window`, so the effective period carries up to one bucket of error. At one
hour that is 8%; at fifteen minutes it would be 33%.

**One hour is therefore more conservative than the data now requires** — thirty
minutes would carry 17% and is defensible. Left alone rather than changed,
because it is a product decision and not a defect, and recorded here so the next
reader does not re-derive it from a p90 that has moved. `LIVE_TOTALS_HISTORY_SECONDS
= 604800` is what sets the *longest* window at seven days.

## The allowance badge nobody below Intro could find (2026-09-28)

File: `widgets/inhouse/liverefresh/static/liverefresh/liverefresh.js`.

A reader signed up, switched on **Settings → Real-time refresh**, and could not
find the badge. Two separate things were wrong and only one of them is code.

### The badge was put beside the wrong layout's control

`showLeft` relocated the badge with `document.getElementById("tb-refresh")`, which
is the **dynamic** toolbar's id. `ADDRESS_LAYOUTS` gives `dynamic` a `tier` of
`"Intro"`, so the only readers who can select it are subscribers — and subscribers
from Asastatser up are *unmetered*, so `_with_left` sends them no figure at all
and the badge never appears for them either.

That leaves exactly one group the badge is for: readers below Asastatser, all of
whom are on **classic**, where `tb-refresh` does not exist. The badge therefore
stayed where `_swap_entry.html` renders it — inside `#id-swap-entry-container` at
the top of `address.html` — while the control it describes is 200 lines further
down. It was visible, and nowhere near the thing it was about.

Now: `#tb-refresh || .refresh label`. The insert is unchanged, because
`control.parentNode.insertBefore(badge, control.nextSibling)` appends inside
`.refresh` when the label is last, which it is.

**A test was pinning the defect.** `it("leaves the badge where it is when there is
no control")` said "The classic layout has no `tb-refresh`; the figure still
belongs on the page, just not relocated." The first clause is true and the
inference is not: classic has its own control, `.refresh label`, and the fixture
simply never rendered one. So the test asserted a fixture's shape and read as
though it asserted the page's. It is now two tests — one for classic's control,
one for a fragment with neither — and the fixture gained a `classicControl`
option that renders `address.html`'s actual markup.

### The other half is not a bug, and it is worse

There are **two switches**, and they are in different places with different names:

1. `Settings → Real-time refresh → "Refresh on every block"` sets
   `profile.live_refresh`, which is what puts `liverefresh_url` in the context.
2. The address page's **Auto-refresh** checkbox writes `localStorage.refresh`,
   which is what `armed()` reads — and `poll()` returns immediately when it is
   false.

So a reader who flips only the first gets no live refresh and no badge, and
nothing tells them why. The settings copy makes it worse by describing the
outcome as already settled: *"Update an address page as each block arrives,
instead of reloading it every minute."* Meanwhile the checkbox that actually
starts it is titled *"Reload this page about once a minute"* — the behaviour it
has when live refresh is **off**.

**Nothing tested the link**, which is why it survived. Every browser test calls
`arm()`, whose own docstring says "Tick the Auto-refresh checkbox" and which
instead does `localStorage.setItem('refresh', 'y')`. There is now a test that
clicks the real checkbox. There is still no free-tier (`permission = 0`) browser
test anywhere in that file — everything runs at Intro or above, so the exact
configuration the Medium article invites readers into is covered only by this
one addition.

Left for a decision rather than fixed here, because it is product copy and a
possible UI change, not a defect:

* the checkbox's title should say what it does when live refresh is on, or
* the settings switch should stop promising the behaviour and say it has to be
  turned on per page, or
* flipping the settings switch should arm it, and the checkbox become the only
  control.

The article's steps were corrected to name both switches in the meantime.

## A refused poll stands down (2026-09-28)

File: `widgets/inhouse/liverefresh/static/liverefresh/liverefresh.js`.

The other half of the marker/poll disagreement recorded under
`core/views.py` in the frontend's logbook. That change stops the case that
happened — a free reader on an unlinked address never starts a poll now — but the
poll itself still had no answer to a refusal, so a tier lapsing mid-session would
reproduce the same flood: **767 requests in 85 minutes against a 403 that cannot
change**, each one a 35-line traceback, 95% of `asgi.log`.

`handBack()` is `spent()` minus the notice: stop the timer, hide the badge, remove
the marker. Removing the marker *is* the handover, because `address.js` reads it
every tick to decide whether to stand its sixty-second reload down.

**No notice, by decision.** A spent allowance is the reader's own business and
says so; a refusal is a page they were never going to be served, and the honest
behaviour is the one they had before they asked for anything — a reload every
sixty seconds, silently.

### 4xx only

A refused request stays refused however often it is repeated. A 5xx is the
opposite: a worker recycling answers 502 for about a second — there are eight
`asastats.com.socket failed` and six `no live upstreams` in one week of nginx
error log — and standing down for that would cost the reader live refresh until
they reloaded the page. So `>= 400 && < 500`.

### The event name, and why a browser test was required

**`htmx:response:error`, not `htmx:responseError`.** This build is htmx 4 and the
v1/v2 name does not exist in it; a listener for the old spelling would never fire
and nothing would say so. That is the fourth htmx 4 silent no-op in this logbook.

Read off the minified source rather than guessed, and both facts matter:

```js
if (e.response.status >= 400 && this.#L(t, "htmx:response:error", { ctx: e }))
```

with `async #se(e) { let t = e.sourceElement, ... }` and
`trigger(e, t, r, i = !0) { ... bubbles: i ... }`. So it is dispatched **on the
element that issued the request** and it bubbles — which is what makes
`event.target === marker` the correct scope, and it has to be scoped: the swap,
the sweep and alerts all issue htmx requests on the same page, and any of their
4xx responses would otherwise stand live refresh down.

The jest tests fire the event with a detail the test file chose, so they prove the
handler and nothing about the event. `test_a_refused_poll_is_handed_back_to_the_free_reload`
patches `LiveRefreshView.test_func` to `False` and drives a real browser against a
real 403; it fails when the listener is removed.

### One guard deliberately absent

`event.detail.ctx.response.status` is read straight through with no `|| {}`
fallbacks. htmx assigns `ctx.response` *before* dispatching this event, so an
absent one is not an input production can produce — and the guards cost a branch
no test could reach honestly, which is the reasoning `alerts.display.format_count`
already records for a `try` it does not have. The 100% branch threshold caught
them.

---

## inhouse/alerts/templates/alerts/_toolbar.html

### 2026-09-30 - cross-browser count refresh

The alert list is fetched only when its modal opens, so a create or delete in
one browser cannot update another browser's badge by itself. The toolbar polls
the server-rendered count every 30 seconds and replaces only its own markup.
This uses the same authoritative `AlertRule` count as the modal, avoids
same-browser-only storage events, and leaves the modal's existing htmx swaps
unchanged.

### Correction, 2026-09-30

The polling trigger was initially placed on the toolbar itself. The toolbar is
moved into the action-row slot by `alerts.js`, and production showed no count
requests from that arrangement. The trigger now lives on the stable
`id-alerts-count-poll` marker in `_swap_entry.html`; its response still replaces
only `#id-alerts`.

---

## inhouse/liverefresh/views.py

### 2026-09-30 - carry identity and runaway-session guard

The carry is session state, so a position must occupy one slot even when its
value or rank changes. The page already has the correct stable identity in
`api.position_id`; the live payload supplies the same identifying fields and
links, so `_pid` uses that shared recipe. A legacy list carry is deduplicated on
load, and a current dict carry is re-keyed on load so changing `PID_VERSION`
cannot leave an old and new copy of the same row together.

Production carries reached roughly 600,000 fragments while the configured
response budget was 100. Each poll then loaded and rewrote a very large Django
session, which matched the Redis latency, socket timeouts and Daphne failures in
the 2026-09-28 to 2026-09-30 logs. A carry over `50 * MAX_FRAGMENTS` is treated
as corrupt backlog and discarded; the next full live payload repopulates it.

Redis connection failures are handled like timeouts for both poll paths. A live
poll is a heartbeat and a regroup is an optimization, so either can safely
answer 204 and let the next request retry instead of turning transient Redis
failure into a request 500.

### 2026-10-02 - catching up on payloads a tab missed (`_caught_up`, `since`)

Every engine payload is a diff against the one before it, and `lvp` is
overwritten each block. A tab that does not fetch a payload loses that
payload's row and position changes, while the band, which is absolute, moves
on. That happens when:

* the poll runs every 3 s against ~2.8 s blocks;
* htmx drops a poll whose source still has one in flight (p90 is 3.3 s);
* a background tab is throttled.

The rows then stay wrong until the next full payload (a re-read every 60
blocks, or a strike).

The engine now stamps each payload with a per-page `seq` and keeps the last 20
in `lvl:{bundle}` (engine logbook, `utils/transmitters.py`, same date). The
poll returns `liverefresh:seq` in `HX-Trigger` (204s included). The tab sends
it back as `since`, and the view folds every held payload with
`since < seq < latest` under the latest one, oldest first, positions keyed by
`_pid`, before `_chunked`. `since == seq` sends only the carry. A missing
`since` (first poll), a garbled one, one ahead of `seq` (the engine's baseline
expired and restarted at 1), or a payload without `seq` (older engine) means
the latest only, as before. A hole is logged at debug and still applies what
is held.

`since` is per tab, deliberately not in the session: `last_total` and the
carry are per session *and bundle*, so two tabs on one bundle already share
them. That is a known gap, not changed here.

The first poll after a page load still applies only the latest diff to rows
rendered some passes earlier. Anchoring that would need the page to render the
`seq` its data matches, which the address page's source cannot say.

### 2026-10-03 - per-tab carry and last total (`tab`, `_touch_tab`)

`last_total` (`liverefresh:{bundle}`) and the carry (`liverefresh:carry:{bundle}`)
lived in the session per bundle. Two tabs on one bundle share one session, so:

* the first tab to poll took a carry that was owed to the other, whose rows
  then stayed stale until the next full payload;
* one tab's poll recorded the total, and the other tab got a 204 for a band it
  had never been shown.

The page now sends `tab`, a random id from `liverefresh.js` that lives as long
as the page. Both keys get `:{tab}` appended. `liverefresh:tabs:{bundle}` maps
tab to its last poll. Each poll drops tabs idle for more than
`TAB_IDLE_SECONDS` (600, twice the hidden-tab grace) and keeps at most
`MAX_TABS` (8), together with their keys. Every page load mints a new id, and
the 2026-09-30 runaway session showed what unbounded session growth costs.

A missing or malformed `tab` (not `[A-Za-z0-9]{1,16}`), e.g. from a page still
running the old script, uses the old per-bundle keys, so nothing changes for
it. The reload cooldown stays per bundle on purpose: it limits how often a
*reader* is reloaded, not a tab.

### 2026-10-03 - per-tab state moved from the session to the cache (`LiveState`)

The last total, the carry and the tab registry now live in the Django cache under
`lvc:<user pk>:<key>`, with a `TAB_IDLE_SECONDS` (600) lifetime, behind
`LiveState`, which reads like a session so the code around it is unchanged.

Why: every poll wrote the session (the tab registry, and the last total on any
200), every 3 s per tab, and a resync's carry put ~0.5 MB into it (two such
sessions seen 2026-10-03), up to `MAX_TABS` times per bundle. That made the
session the largest and busiest key a reader has, and it blocks moving sessions
to `cached_db`, where each save is also a database write.

The reload-cooldown stamps (`_reload_key`, `_stale_key`) stay in the session on
purpose: they are per reader rather than per tab, and written only when a page
is found out of date. Tests put a plain dict in `live_state`, so the existing
assertions read the same keys; `TestLiveStateInTheCache` covers the store and
checks that a poll leaves the session untouched.

### 2026-10-03 - correction: `LiveState` under a `DummyCache`

The entry above assumed a working cache. Development's settings use
`DummyCache`, which drops every write, so a test run with those settings failed
(`state.get("a")` was None) and a local server would have lost the carry and
the last total on every poll. `_live` now falls back to the session when the
default cache is a `DummyCache`, which is how it behaved before.
`TestLiveStateInTheCache` sets its own `LocMemCache`, so it passes under any
settings module.

## inhouse/liverefresh/views.py, templates/liverefresh/fragments.html, static/liverefresh/liverefresh.js - live log: floor rows (2026-10-08)

The live log's first row kind is a floor move. The engine half is in
`engine/docs/logbook.md`; the decisions are in `live/LIVELOG-ANALYSIS.md`.
The shell and the stylesheet are in the frontend repo.

**Where the shell lives.** `_swap_entry.html` holds the `<details id="id-livelog">`,
because it is per-reader. The cached `address_dynamic.html` must not carry it.
`liverefresh.js` moves it beside `#charts` when a watch starts, inside a
`charts-row` grid (two columns from 1024px, stacked below), and hides it when the
watch hands back. Moving a DOM node keeps its listeners, so `dynamic.js`'s bindings
on the charts survive.

**Why a row is text, not a copy of a holding's row.** The plan's stage-2 problem
was that an inserted asset row needs context the poll does not have. A log row
carries its own name and figures from the engine, so the fragment needs nothing
from the page it lands on.

**Catch-up.** `_caught_up` concatenates `events` from every missed payload, the
same way it merges `values`. A tab that has already applied the latest payload
gets `events: []`, so a repeated poll does not repeat a row. An event-only
response is not a 204, because a floor can change what a holding is worth
without moving the account's total.

**Dynamic only.** `fragments.html` renders floor rows when the layout is not
`classic`, and the shell has nothing to attach to there.

**Not built.** The unread count on the summary, the 200-row cap, and the
sessionStorage restore. None is needed for floor rows, since they never trigger
a reload; they come with the kinds that do.

**Test status.** `widgets/inhouse/liverefresh/tests` passes, 221 tests with 4
skipped, including the new catch-up and rendering cases in `test_views.py`. The
Jest suite for `liverefresh.js` was not run: `website/` has no `package-lock.json`
and no `node_modules`, so `npm ci` cannot run here. `liverefresh.js` passes
`node --check`. The stylesheet was rebuilt from `input.css` with
`build-tailwind.sh`.

## inhouse/liverefresh/static/liverefresh/liverefresh.js, templates/snippets/dynamic/livelog.html - live log: two corrections (2026-10-08)

**The log showed whenever a watch was possible, not whenever one was running.**
`start()` ran once at load and revealed the log. It runs whenever the reader's
profile has live refresh on, so a reader with the Auto-refresh checkbox off saw
an empty log, and one who turned the checkbox on after load saw nothing until a
reload. `syncLog()` now follows the checkbox on every tick, so both cases are
right without a reload. Found by the browser test
`test_the_live_log_is_folded_and_hidden_until_the_reader_watches`, which asserts
the log is hidden before the checkbox is ticked. Jest covers the same two cases.

**A row on its own arrives without its `li`.** The first row partial put
`hx-swap-oob="afterbegin:#id-livelog-list"` on the `<li>`. The vendored htmx is
4.0.0 (the site moved to it on 2026-09-21, see `live/HTMX4.md`), and for any
strategy other than `outer…` it strips the out-of-band element and keeps only
its children. The rows arrived as bare `<span>`s in the list. The project's own
pattern in `historic/templates/historic/assets.html` is the fix: a wrapper that
carries the target's id and `hx-swap-oob="beforeend"`, with the rows inside. The
log uses `<ol id="id-livelog-list" hx-swap-oob="afterbegin"><li>…` and the
integration and unit assertions were updated to match. This was not caught by
any test until the browser suite ran against the real htmx.

## inhouse/liverefresh - live log: positions opened and closed (2026-10-08)

Rows for `position_open` and `position_close` events, rendered by
`livelogposition` in `snippets/dynamic/livelog.html`. Same wrapper pattern as the
floor row, for the reason logged above (htmx 4 strips the wrapper of an
out-of-band element). A close carries no figure: the position is gone, and the
row says which one went.

Tests: unit (rendering, classic exclusion), real-Redis integration (open
delivered; close delivered to a tab that missed its block, named from the
baseline), and one browser test in which an opened position arrives as a single
row with the position still in place.

## inhouse/liverefresh/views.py - live log: restored on load (2026-10-08)

**Why the log is restored from the backlog, not from `sessionStorage`.** The
poll answers a holdings change with `HX-Refresh` and no body, so the events
cannot be written anywhere before the reload. Writing them from an `HX-Trigger`
header would depend on htmx 4 running that before the reload, and nothing here
establishes that order. The engine already keeps the last twenty payloads per
page, each carrying its events, so the shell reads those back
(`recent_log_events`). Roughly a minute of rows, with no browser storage and no
ordering to rely on. A page that loads with a quiet backlog shows an empty log,
as before.

**Bug caught by the integration suite, not by the unit tests.** The first version
keyed the backlog by the bundle hash, which exists for several addresses only.
The pass publishes a single address under its own name, so the lookup found
nothing in production while every mocked test passed. It now uses
`force_bundle=False`, as the poll does. The integration test
`test_liverefresh_integration_a_reload_restores_the_recent_rows` puts the backlog
in real Redis and reads the swap entry back.

**One row partial for both paths.** `snippets/dynamic/livelog.html#livelogevent`
renders every kind, both when a row arrives live (inside the wrapper in
`fragments.html`) and when the shell is rendered on load, so the two cannot
drift.

**Tests.** Unit: newest-first order, skipped corrupt entries, Redis unavailable,
a value that is no address, bought and sold rows. Integration: the restore above.
Browser: an asset bought reloads the page and its row is still there afterwards.

## inhouse/liverefresh - live log: NFTs bought and sold (2026-10-08)

Rows for `nft_in` and `nft_out`, in the same shared partial as the other kinds.
An NFT purchase reloads the page like an asset, so it is restored on load from
the backlog too. Tests: unit rendering, integration restore, and one browser test
mirroring the asset-bought test.

## inhouse/liverefresh - live log: the ALGO price row (2026-10-09)

A `price` event renders as "ALGO price X to Y USD" with the signed move, and
red when it falls, in the shared partial. It arrives live, and it is restored
on load from the backlog like the other kinds. Tests: unit (rise, fall),
real-Redis integration (live and restored), and one browser test that the row
lands without a reload.

## inhouse/liverefresh - live log on the classic layout, and the dynamic alignment fix (2026-10-09)

**Alignment.** On the wide grid the charts panel carried its own 1rem top
margin, while the log's wide rule removed its margin, so the log's summary sat
16px higher than the charts' (the screenshot in `live/`). The row now supplies
the spacing and neither panel sets a top margin on that grid. The regression
test measures both summaries and fails at a 16px offset; it was run against the
old rule to confirm that.

**Classic.** The log is a card in a `livelog-section` directly after `#id-cons`,
the consolidated box, right aligned. It is a sibling of that box, not a child:
inside the details it would be hidden whenever the box is folded. `liverefresh.js`
places it there when a watch starts, and the fragments render its rows on both
layouts now. The log's CSS is no longer scoped to `.dynamic-page`.

**Tests.** Jest: the placement, and that the log is not moved twice. Browser: the
inherited log tests run on the classic layout too (floor, price, folded), and the
position test is skipped there because classic reloads for a new position rather
than regrouping it. A new classic test checks the section sits below the box and
its right edge lines up with the box.

## inhouse/liverefresh - live log: unread count, row cap, and the gap line (2026-10-09)

**Unread count.** A `MutationObserver` on the list counts rows added while the
log is closed, and the summary shows "N new". Opening the log clears it. It is
attached when the watch starts, after the rows restored on load are in the list,
so restored rows are not counted as new.

**Row cap.** The list keeps 200 rows; the observer drops the oldest beyond that.

**Gap line.** `_caught_up` reports the updates the backlog could no longer give:
`seq - since - 1` minus what was found. The fragments render "N updates not
received" once. A gap is news, so a response carrying one is not a 204.
Nothing is invented for the missing updates; the line only counts them.

**Tests.** Jest: counting, reset on open, restored rows not counted, the cap.
Unit: the gap count, and the line's wording (singular and plural). Integration:
a real backlog gap is reported. Browser: a row arriving while the log is folded
shows "1 new", and opening the log clears it, on both layouts.

## inhouse/alerts/tests/conftest.py - alert tests stay off the engine's Redis (2026-10-09)

Saving an alert rule publishes its page to `lvr`, the set the engine's live pass
fetches every block. The alert view tests saved rules against placeholder
addresses, so each test run wrote placeholders into the engine's watch set, and
they failed on every block. The conftest patches the population module's Redis
client for the unit suite. The integration suite still uses the real set, on
purpose. Verified: after the alert, asastats, folks, dustsweep and widgethost
test packages ran, the engine's `lvr` held no placeholder.

## config/settings/automated_tests.py - the suite uses Redis database 15 (2026-10-09)

Unit and functional tests wrote bundle mappings to database 0, the database the
engine's live pass reads. `create_bundle` stores a bundle's addresses on every
call, so a test that used placeholder addresses left them there for the engine
to fetch. All the integration suites already used database 15; the automated
settings now do too. Verified: after the widget, core and api suites ran, database
0 held no placeholder.

Nine tests in `core/tests` failed only in one combined invocation that passed
the widget config file; they pass with the project's own configuration, alone and
in the same run as the integration suite.

## inhouse/liverefresh/static/liverefresh/liverefresh.js - session storage and deduplication, 2026-10-09

### Session storage persistence

The live log is persisted across F5 (user refresh) using sessionStorage, keyed
by `pollUrl` (stable per address/bundle). Changing the key to `holdings`
(fingerprint) was broken: holdings change on reload and F5 is what reloads it,
so saved rows were under the old key and not restored.

Rows are saved as `{html, className, key}` to preserve gap styling (`livelog-gap`)
and the deduplication key for the next load.

### Keyed deduplication

F5 creates duplicates because rows arrive from three sources: server-rendered
backlog (from `recent_log_events`), saved rows from sessionStorage, and the
first poll's payload (no `since` query). Each copy has the same key. The template
renders each row with `data-key="{{ event.round }}|{{ event.kind }}|{{ event.asset }}|{{ event.name }}"`.

On restore, a set of existing server keys is built, and saved rows matching a key
are skipped. The observer checks for duplicate keys before counting new rows toward
the unread badge. Gap rows (no key) are never deduplicated.

### `logRestored` flag

`restoreLog()` runs only once per page load (before `watchLog` attaches the observer),
not every 3 seconds on each poll tick. Without the flag, the same saved rows would be
prepended repeatedly, climbing the unread badge and filling the 200-row cap with
duplicates by the first poll interval.
