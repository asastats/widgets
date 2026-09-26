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