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
