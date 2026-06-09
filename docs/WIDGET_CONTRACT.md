# ASA Stats Widget Contract (v2 — ratified)

## Model

One in-process tier. Every published widget — `inhouse` or `thirdparty` — is audited
and published by ASA Stats and runs inside the deployment's Django process under one
security umbrella. The **audit is the trust boundary**, applied before publication: it
verifies a widget's code stays within what its manifest declares.

A *deployment* is a website built from the asastats + widgets repos. The official ASA
Stats site is one deployment; forks are others. Each holds **one** engine API token.

Two orthogonal manifest axes, neither affecting how a widget runs:
- **origin** — `inhouse | thirdparty`. Provenance + revenue accounting only.
- **capability** — `public | engine-backed`. `public` may call the public `/api/v2/`
  and declared hosts; `engine-backed` may additionally call the privileged engine
  endpoints it declares. The grant is recorded at publication and verified by audit.

## Enforcement — three parts, three owners, two layers

An engine-backed request passes three independent checks:

| check                 | question                                  | where  | owner / forkable       |
|-----------------------|-------------------------------------------|--------|------------------------|
| token `scopes`        | may this *deployment* call this endpoint? | engine | ASA Stats — unforkable |
| token `limits[widget]`| how *much* may this deployment consume?   | engine | ASA Stats — unforkable |
| `required_permission` | may this *user* use the widget?           | host   | deployment — forkable  |

- **`scopes`** (on the deployment token) — which engine endpoints the deployment may
  hit. A fork never granted `historic:*` cannot run historic; `HasWidgetScope` enforces
  it at the engine.
- **`limits[widget_id]`** (on the deployment record) — an **open, per-widget bag of
  named limits the widget defines** (e.g. `{"historic": {"max_addresses": 10}}`). The
  engine enforces it against the deployment. **Absence of a configured limit denies** —
  a deployment never gets unlimited resources by omission. The widget's own endpoints
  check the keys they declare; the audit confirms each engine-backed widget actually
  checks the limits it claims ("declare a limit, check a limit").
- **`required_permission`** (manifest) — the user-permission bar, forkable deployment
  policy, enforced host-side against `Profile.permission`. The engine never sees the
  user.

These are independent: a fork with a high-permission token may set its users' bar to
`0`; a modest-token fork may set a high bar. Neither caps the other — they gate
different subjects at different layers. The only hard ceiling a fork cannot raise is its
token's `scopes` + `limits` at the engine.

## `required_permission` (manifest, host-enforced)

A bare integer (simple widgets) or an ordered band list keyed by resource volume
(historic). First band whose `max_addresses >= size` wins; over the largest band →
deny. `size` is the count of **resolved** addresses (host resolves bundle→addresses,
then counts — so `data` injection happens before the check).

```toml
# simple widget
required_permission = 500000000

# historic — reproduces the former can_access() exactly
[[required_permission]]
max_addresses = 1
permission    = 23299689438      # Asastatser
[[required_permission]]
max_addresses = 5
permission    = 258885438200     # Professional
[[required_permission]]
max_addresses = 10
permission    = 3236067977500    # Cluster
```

Both the thresholds and the integers are manifest data a fork may change. The engine's
`limits` ceiling independently caps the resource dimension, so a fork editing its top
band to `max_addresses = 100` is still refused by the engine at the granted ceiling.

## Manifest (`widget.toml`, one per widget) — metadata only

The manifest carries **metadata and the enforced grants** — nothing the widget can wire
up itself through ordinary Django. It does **not** contain routes, websocket consumers,
menu entries, or asset paths (see "What the manifest does not contain" below).

```toml
id            = "historic"
name          = "Historic data"
version       = "0.9.0"
origin        = "inhouse"             # inhouse | thirdparty
capability    = "engine-backed"       # public | engine-backed
revenue_account = ""                  # payout id for thirdparty; empty for inhouse
required_permission = [ ... ]         # integer or band list (above)
engine_endpoints = ["historic:process","historic:evaluate","historic:timestamp",
                    "historic:events","historic:reset"]
data          = ["portfolio:bundle", "profile:permission"]
hosts         = []                    # external hosts a public widget may call
```

`data` is **enforced**: the host injects only declared keys; widgets do not access the
ORM directly. `engine_endpoints` must be a subset of the deployment token's `scopes`,
and a `public` widget must declare none.

### What the manifest does NOT contain

- **routes / websocket consumers** — a widget keeps its own regex `urls.py` and
  `routing.py`. asastats already includes `widgets/urls.py` (at `/widgets/`) and
  `widgets/routing.py` (websocket patterns); those two includes are unchanged. The
  registry does not synthesize URLconf or Channels routing from manifests.
- **menu** — there is no widget-driven navigation/menu system. If a widget's link
  appears in a template, that stays a template concern. A manifest menu field would
  describe a feature that does not exist.
- **assets (static/templates)** — discovered by Django's normal app loaders, since each
  widget is a Django app. No manifest declaration needed.

These were dropped because each duplicated something the widget already does natively;
keeping them in the manifest would invite drift between the declaration and the code the
audit must actually verify.

## In-process lifecycle (host registry)

1. **Discover** — the registry scans the widgets repo for `widget.toml`. The presence of
   a manifest is what marks a directory as a widget, replacing the hardcoded
   `INHOUSE_WIDGETS` list (`discover_widgets()` → `(INHOUSE_WIDGETS, THIRDPARTY_WIDGETS)`
   split by `origin`).
2. **Validate** — manifest schema; `engine_endpoints ⊆` token `scopes`; `public`
   declares no `engine_endpoints`.
3. **Wire (unchanged host includes)** — the widget's own `urls.py`/`routing.py` are
   picked up by asastats's existing `widgets` URL and websocket includes. Discovery only
   populates the inhouse/thirdparty widget lists; it does not assemble routing.
4. **Gate (per request)** — host resolves and injects declared `data` (bundle→addresses
   via public `bundle_and_addresses_from_path`), then checks `Profile.permission` against
   `required_permission` for the resolved address count.
5. **Run** — widget renders / opens its consumer; engine-backed calls go through the
   host's generic `engine_request(scope, method, path, allowed_scopes, **kw)` using the
   single deployment token.

## Realtime (engine-backed widgets)

Shared Channels-Redis message bus between engine workers and the open consumer
(transient pub/sub, not stored data). `group_name_from_bundle` is **vendored** into the
widget (deterministic) so both sides resolve the identical group with no `engine.*`
import.

## Historic mapped onto this contract

- **Open (widgets repo):** manifest; own `urls.py`/`routing.py`; `HistoricView` shell +
  host gate; templates; chart JS; slimmed `ViewStatus` (range/zoom math only — no
  DataFrames); thin `consumers.py` relaying via `engine_request` + the bus; vendored
  `group_name_from_bundle` and the pure `check_chart_period`. The consolidated-view
  charts are assembled **host-side** from the engine's `assets_data` dict via the host's
  shared `utils.charts` (a one-function `charts.py`), since that step is generic
  presentation over already-interpreted data and needs no proprietary code.
- **Engine (closed):** storage, ledger evaluation, `ASA_PROGRAMS`, the DataFrame chart
  pipeline, and the asset interpretation, exposed as render-ready JSON: `process`,
  `evaluate` (period; `null` ⇒ initial charts), `timestamp` (returns the interpreted
  `assets_data` dict), `events`, `reset`. `ASA_PROGRAMS` and DataFrames never cross the
  boundary. Per-bundle `asset_values` cached to disk; the `StorageCarrier` held in a
  TTL-bounded in-process LRU; address count persisted to `meta.json` and re-checked
  against the `limits` ceiling on every engine-backed call.
- **Bus:** shared Channels-Redis; vendored `group_name_from_bundle`.

## Changelog

- **v2** — manifest is metadata-only: removed `routes`, `consumers`, `menu`, and
  `assets` (widgets keep their own `urls.py`/`routing.py`; templates/static via Django
  app discovery; no menu system exists). Discovery replaces the hardcoded
  `INHOUSE_WIDGETS` list. Recorded the historic charts/assets seam: engine returns the
  `assets_data` dict from `timestamp`, and the widget builds consolidated charts from it
  host-side via `utils.charts`.
- **v1** — ratified the three-part enforcement model (`scopes`, `limits`,
  `required_permission`) and the `required_permission` integer-or-band schema.
