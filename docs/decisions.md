# DealFlow360 — Architectural Decision Record

Only meaningful decisions are recorded here. This file is the project's long-term memory.

---

## DEC-001 — Build on Odoo 17.0 Community via Docker

- **Date:** 2026-09-05
- **Decision:** Target Odoo 17.0 Community, run via `docker compose` (odoo:17 + postgres:15).
- **Reason:** The problem statement is technology-agnostic but the project brief mandates Odoo. Docker gives a reproducible stack with zero local PostgreSQL/Python dependency hell — critical under hackathon time pressure. Odoo 17 uses the stable `<tree>` view syntax and has the widest, most reliable body of reference material.
- **Alternatives considered:** Odoo 18 — rejected: renamed view elements (`<tree>`→`<list>`) and OWL churn add avoidable risk. Native source install — rejected: no local PostgreSQL present, long dependency install, machine-specific breakage.
- **Status:** Accepted

---

## DEC-002 — Single addon `dealflow360`

- **Date:** 2026-09-05
- **Decision:** All custom code lives in one addon rather than several feature addons.
- **Reason:** Cross-addon dependency ordering and manifest churn is a common source of "module won't upgrade" failures. One addon keeps upgrades atomic and serial development simple.
- **Alternatives considered:** One addon per phase (dealflow_discount, dealflow_fulfillment, ...) — rejected: more ceremony than value at this scale, and raises the chance of a broken dependency graph mid-demo.
- **Status:** Accepted

---

## DEC-003 — Blended Discount Risk Score formula

- **Date:** 2026-09-05
- **Decision:** The problem statement deliberately leaves the formula to the team. DealFlow360 uses a revenue-weighted excess model combined with a worst-line term.

For each order line *i*:
```
effective_ceiling_i = min(customer_tier_ceiling, product_category_ceiling)
excess_i            = max(0, discount_i − effective_ceiling_i)      # in percentage POINTS
weight_i            = line_subtotal_i / order_subtotal              # revenue share
```

Order-level:
```
blended_excess = Σ (excess_i × weight_i)      # revenue-weighted average overshoot
max_excess     = max(excess_i)                # worst single line

risk_score     = min(100, 6 × blended_excess + 3 × max_excess)
```

Routing thresholds:
| Condition | Risk level | Approval chain |
|---|---|---|
| every line within its ceiling (`max_excess == 0`) | **NONE** | none — auto-approve |
| `0 < risk_score ≤ 40` | **MEDIUM** | Sales Manager |
| `risk_score > 40` | **HIGH** | Sales Manager → Finance |

- **Reason:** The specification requires two distinct behaviours that a single metric cannot capture:
  1. *"one line broke its own stricter limit ⇒ the whole quotation gets flagged"* — handled by the `max_excess` term, which fires even when the offending line is a small share of order value.
  2. *"many lines each a little over … cannot slip through unnoticed"* — handled by `blended_excess`, which accumulates small overshoots across the order.

  Weighting by revenue share matters because 8 points over on a €50 000 line is a materially larger giveaway than 8 points over on a €200 line.

  **Validation against the spec's own worked example** (Gold customer; Laptop/Hardware 12% given vs 15% allowed; Setup Service 18% given vs 10% allowed; subtotals 1000 / 500):
  `excess = [0, 8]`, `weights = [0.667, 0.333]` → `blended = 2.67`, `max = 8`
  → `score = 6(2.67) + 3(8) = 40` → **MEDIUM → Sales Manager approval required.**
  This reproduces the specification's stated outcome exactly.

  **Validation of the "many small violations" case** (three lines 2, 3, 2 points over, equal value):
  `blended = 2.33`, `max = 3` → `score = 23` → **MEDIUM → approval required.** No silent slip-through.

- **Alternatives considered:**
  - *Simple max-excess only* — rejected: ignores the explicitly-required blended/accumulation behaviour.
  - *Unweighted mean excess* — rejected: a single trivial line could dilute a large violation, and it treats a €200 line as equal to a €50 000 line.
  - *Total margin currency given away* — rejected: not comparable across order sizes, so fixed thresholds become meaningless.
- **Status:** Accepted — but see **DEC-010**, which amends the routing thresholds from code constants to admin-configurable data. The formula and the 40 default are unchanged, so every worked example above still holds.

---

## DEC-004 — Implement recurring billing natively; do not depend on `sale_subscription`

- **Date:** 2026-09-05
- **Decision:** Recurring/subscription behaviour is implemented as `dealflow.recurring.plan` + `dealflow.billing.schedule`, which generate **real `account.move` invoices**.
- **Reason:** Odoo's `sale_subscription` module is **Enterprise-only** and is not available in Odoo 17 Community. The brief says to prefer native functionality, but the native subscription module simply does not exist in our runtime. Billing schedules therefore materialize through native `account.move` / `account.payment`, so the financial records remain genuinely native — only the scheduling layer is ours.
- **Alternatives considered:** Odoo Enterprise — rejected: licensing, and not available for the hackathon. A purely visual billing screen — rejected outright: the brief explicitly forbids a fake billing UI disconnected from financial records.
- **Status:** Accepted

---

## DEC-005 — Deal Health scoring methodology

- **Date:** 2026-09-05
- **Decision:** Health starts at 100 and accrues penalties:

| Signal | Penalty | Cap |
|---|---|---|
| Stalled — no activity beyond threshold (default 7 days) | −5 per extra day | 30 |
| Discount anomaly — order avg discount > 1.5× the rep's 90-day average | −20 | 20 |
| Approval delay — a step pending > 2 days | −5 per extra day | 25 |
| Delivery risk — a line cannot be fully sourced from total available stock | −25 | 25 |

Buckets: **≥80 Healthy · 50–79 At Risk · <50 Critical**

- **Reason:** The specification names exactly these four signals (stalled quotes, discount anomalies, approval delays, delivery promise slippage) but prescribes no formula. A transparent additive penalty model is explainable to a judge in one sentence and every term traces to a real record.
- **Alternatives considered:** ML/statistical anomaly scoring — rejected: the brief forbids claiming AI that is not implemented, and there is no training data. Pure rule flags without a score — rejected: the mockup shows a health dashboard requiring ranking/prioritisation.
- **Status:** Accepted

---

## DEC-006 — Warehouse allocation minimizes shipment count, greedily

- **Date:** 2026-09-05
- **Decision:** The allocation engine reads live per-warehouse availability from `stock.quant`, then greedily prefers warehouses that can completely fulfil the most order lines, tie-broken by configured shipping cost weight. Remaining quantity becomes a backorder. Manual override always permitted.
- **Reason:** The specification asks to "minimize number of shipments" with a shipping cost weighting. A greedy set-cover heuristic delivers that objective, runs instantly, and is explainable. Exact optimisation is unnecessary at these order sizes.
- **Alternatives considered:** ILP/exact optimiser — rejected: heavy dependency, negligible benefit at demo scale. Naive per-line nearest-warehouse — rejected: fragments orders into more shipments, defeating the stated goal.
- **Status:** Accepted

---

## DEC-007 — Portal isolation enforced by ORM record rules, not controller checks

- **Date:** 2026-09-05
- **Decision:** Customer portal access is restricted primarily by an `ir.rule` on `sale.order` limiting portal users to their own `partner_id` (including child contacts), with controller-level token/ownership checks as a second layer.
- **Reason:** The brief requires the portal be genuinely restricted, not a relabelled internal screen. Controller-only checks are bypassable through any other RPC path; a record rule is enforced by the ORM for every access path. Defence in depth.
- **Alternatives considered:** Controller checks only — rejected: not a real security boundary. A fully separate application — rejected: discards native Odoo portal auth for no security gain.
- **Status:** Accepted

---

## DEC-008 — Subscription lifecycle lives on `sale.order.line`, not a new model

- **Date:** 2026-09-05
- **Decision:** Mockup screen 9 (Subscriptions list) is backed by **`sale.order.line` extended with lifecycle fields** — `df_sub_state` (active/paused/cancelled), `df_sub_start_date`, `df_sub_next_bill_date`, `df_sub_end_date`, `df_mrr` (computed) — not by a new `dealflow.subscription` aggregate. Screen 9 is an act_window over `sale.order.line` filtered on `df_is_recurring = True`.
- **Reason:** Raised by Don in DF-005a: the architecture modelled recurring *plans* and billing *events* but had nowhere to hold per-subscription state, so "cancel this subscription" had no home. That gap is real. But a new aggregate is the wrong fix here: `dealflow.billing.schedule` already keys on `order_line_id`, so the line is **already** the anchor for recurring behaviour, and in our scope one recurring order line *is* exactly one subscription (we do not renew into new orders). Extending the line satisfies CLAUDE.md's native-first rule, keeps one source of truth, and avoids a second record that could drift out of sync with the line it mirrors. Mid-cycle proration mutates line quantity, so state belongs beside quantity.
- **Alternatives considered:** New `dealflow.subscription` model (Don's recommendation) — rejected: duplicates the order line's identity and adds a sync burden for no capability we need. Client-side `read_group` aggregation over billing schedules — rejected: derives state from invoice events, so a paused subscription with no pending rows becomes indistinguishable from a finished one, and it puts business meaning in the frontend.
- **Status:** Accepted

---

## DEC-009 — Per-tier pricing uses native `product.pricelist`; it is NOT the discount-ceiling system

- **Date:** 2026-09-05
- **Decision:** Mockup screen 17's "Price Rules" table is implemented with **native `product.pricelist`**, one per customer tier, applied to customers via the native `res.partner.property_product_pricelist`. No new model.
- **Reason:** Raised by Don in DF-005a as a possible conflict. It is not a conflict — it is a **second, separate requirement** we had not yet modelled. Problem statement §A2 explicitly requires "Price Lists: Customer tier based pricing, currency specific rules", and Odoo's pricelist engine already does tier- and currency-scoped pricing including percentage rules.

  The two mechanisms compose and must not be confused:
  - **Pricelist** sets the *base price* a tier pays (e.g. Gold sees list minus 10%).
  - **Discount ceiling** (DEC-003) caps the *additional manual discount* a rep may apply on top of that price.

  A line's `discount` percentage is therefore measured against the pricelist price, not the catalogue price. Implementations must not double-count the pricelist reduction as rep discount when computing `excess_i`.
- **Alternatives considered:** A custom per-tier price-adjustment model — rejected: reimplements a mature native subsystem and forfeits currency rules, date validity and quantity breaks. Folding tier pricing into the ceiling system — rejected: conflates a pricing decision with a governance control, and would make rep discounts appear artificially large.
- **Status:** Accepted

---

## DEC-010 — Approval routing thresholds are configurable data, not code constants (amends DEC-003)

- **Date:** 2026-09-05
- **Decision:** The MEDIUM/HIGH routing boundaries from DEC-003 are **admin-configurable** via native `res.config.settings` backed by `ir.config_parameter`:
  - `dealflow.risk_high_min` — default **40** (score above this ⇒ HIGH ⇒ Sales Manager then Finance)
  - MEDIUM is any score above zero and at or below that boundary; NONE remains structurally defined as "every line within its ceiling" and is **not** configurable.

  The scoring *formula* itself stays in code. Only the routing boundary is data.
- **Reason:** Raised by Don in DF-005a, who recommended keeping the thresholds static. **I overruled that recommendation**, because problem statement §A3 states the requirement directly: *"Configure approval chain: which discount range needs Sales Manager only, and which range needs Sales Manager followed by Finance."* That is an explicit configuration requirement, and DEC-003 as originally written under-delivered against it. Mockup screen 18 independently shows this panel with a "Save configuration" button, so both sources agree. `res.config.settings` is the native Odoo idiom for exactly this and costs almost nothing.
- **Alternatives considered:** Hardcoded constants (original DEC-003, and Don's recommendation) — rejected: fails an explicit stated requirement. A full `dealflow.approval.rule` model with arbitrary bands — rejected: more machinery than the spec asks for; the spec describes two levels, not an arbitrary ladder.
- **Status:** Accepted — supersedes the "thresholds are constants" reading of DEC-003. The formula and the 40 default are unchanged, so all DEC-003 worked examples still hold.

---

## DEC-011 — Deal health exposes its four signals individually, not only a blended score

- **Date:** 2026-09-05
- **Decision:** In addition to `df_health_score` / `df_health_status`, `sale.order` exposes `df_health_flags` (the four DEC-005 signals: stalled / discount_anomaly / approval_delay / delivery_risk), `df_health_reason` (human-readable text) and `df_health_flagged_date`.
- **Reason:** Raised by Don in DF-005a. The problem statement's Deal Health dashboard requires *per-signal* alerts ("stalled deals", "discount anomaly alerts", "delivery promise slippage indicators") that are individually clickable, not a single opaque number. DEC-005 computed the four penalties internally but discarded which ones fired, which would have forced the frontend to re-derive them — violating the rule that business logic never lives in JavaScript.
- **Alternatives considered:** Score only, with the frontend inferring cause — rejected: duplicates scoring logic client-side and cannot distinguish two deals with equal scores for different reasons.
- **Status:** Accepted

---

## DEC-012 — Portal isolation must use a GLOBAL `ir.rule`, because group rules OR together

- **Date:** 2026-09-05
- **Decision:** DealFlow360's portal restriction on `sale.order` is implemented as a **global** `ir.rule` (empty `groups_id`), not as a rule attached to the portal group. Its domain restricts on `partner_id` (`commercial_partner_id` of the requesting user, including child contacts). Odoo's native follower-based portal rule stays in place; controller-level token/ownership checks remain the second layer (DEC-007).

- **Reason:** Raised by Pam in DF-001d. Odoo already ships an `ir.rule` — *"Portal Personal Quotations/Sales Orders"* — scoped to the `Portal` group with domain `message_partner_ids child_of user.commercial_partner_id`. Two problems:

  1. **It is follower-based, not ownership-based.** `message_partner_ids` is the chatter follower set. Anyone added as a follower gains read access, and it diverges from DEC-007's stated intent of restricting on `partner_id`.

  2. **The combination trap — this is the important part.** Odoo combines record rules as:
     ```
     final = (AND of all GLOBAL rules) AND (OR of all applicable GROUP rules)
     ```
     Group rules **OR** together. So adding a second, stricter rule *on the portal group* would **widen** access, not narrow it — a portal user would match either rule and pass. An engineer trying to tighten security this way would silently achieve the opposite, and the resulting hole would look like hardening in the diff.

     Only a **global** rule (no `groups_id`) is AND-combined and can therefore genuinely narrow access. Hence the decision.

- **Alternatives considered:**
  - *Add a stricter rule to the portal group* — **rejected: actively harmful**, it widens access for the reason above. Recorded explicitly so nobody re-proposes it.
  - *Modify/replace Odoo's native portal rule* — rejected: fights the framework, and a future module update or reinstall could restore it, silently reopening the hole.
  - *Rely on controller checks only* — rejected by DEC-007; not a real boundary since other RPC paths bypass controllers.
- **Status:** Accepted — binding on DF-014. AT-08's "customer cannot read another customer's quotation" must be proven against the ORM directly (e.g. `search_read` as a portal user), not merely through the HTTP route.

---

## DEC-013 — Finance gets READ on the discount governance config

- **Date:** 2026-09-05
- **Decision:** The Finance group receives read access to `dealflow.discount.tier` and `dealflow.category.limit`. Write/create/unlink on both remains **Admin-only**.
- **Reason:** Raised by Pam in DF-001d, who found Finance had *zero* access — not even read — because no ACL row grants it and Finance's `implied_ids` do not reach Sales Rep. Finance's role in the problem statement is to handle second-level approval of high-risk discounts. An approver who cannot see the ceiling being enforced cannot meaningfully judge the exception, and the approval screen would fail to render the governance context. This was an oversight, not a deliberate restriction.
- **Alternatives considered:** Leave Finance with no access and surface ceilings only via computed fields on `sale.order` — rejected: fragile, and it hides the actual rule from the person accountable for the exception. Grant Finance write — rejected: separation of duties, the approver must not be able to move the goalposts they are approving against.
- **Status:** Accepted

---

## DEC-014 — `product.category.df_max_discount` is the single source of truth; drop `dealflow.category.limit`

- **Date:** 2026-09-05
- **Decision:** Delete the `dealflow.category.limit` model. Category discount ceilings live **only** on `product.category.df_max_discount`. The Admin "Category Limits" screen becomes a tree/form view over `product.category` exposing that field.

- **Reason:** Found by Pam in DF-002-QA. The original architecture (my error) specified **both** `dealflow.category.limit` *and* `product.category.df_max_discount`, with nothing linking them. The governance compute reads only `product.category.df_max_discount` (`sale_order_line.py:70`), so an admin editing a ceiling through the intended Configuration screen saw it save successfully **with zero effect on quotation behaviour** — a governance illusion behind a menu built for exactly that purpose. Pam confirmed live: editing the Hardware limit 15 → 2 left `product.category.df_max_discount` at 15 and a fresh Hardware line still computed a ceiling of 15.

  `product.category` already exists and is the natural home for a per-category ceiling, so extending it satisfies the native-first rule and removes any possibility of desync. A write-through (`inverse`/`related`) between the two models would work but keeps two records where one will do, and a custom model shadowing a native field is the wrong direction.

  **Note the asymmetry, which is correct and must be preserved:** `dealflow.discount.tier` **stays**. Odoo has no native concept of a customer discount tier, so that model earns its existence — and because `res.partner.df_tier_id` points at it directly, the ceiling the compute reads *is* the field the admin edits. Pam verified live that editing a tier takes effect immediately. Only the category side was redundant.

- **Alternatives considered:**
  - *Keep both, add an inverse/write-through* — rejected: preserves two sources of truth and a permanent sync burden to fix a problem that disappears by deleting one of them.
  - *Make `product.category.df_max_discount` a related field off `dealflow.category.limit`* — rejected: inverts native-first, making a custom model authoritative over a native one.
- **Status:** Accepted — supersedes the `dealflow.category.limit` row in architecture.md §3.2.

- **Implementation addendum (DF-003c, 2026-09-05):** checked whether the deleted model's admin ACL (`perm_write=1`) needed a replacement now that "Category Limits" is a view over `product.category`. `product`'s own `ir.model.access.csv` grants `product.category` write/create/unlink only to `base.group_system`, which none of our `group_dealflow_*` roles imply — so a naive read of that one file suggested `group_dealflow_admin` would lose write access. It does not: `sale`'s own `ir.model.access.csv` separately grants full CRUD on `product.category` to `sales_team.group_sale_manager` (`access_product_category_sale_manager`), and `group_dealflow_admin` implies `group_dealflow_sales_manager` implies `sales_team.group_sale_manager` (`dealflow_security.xml`). Confirmed live in an `odoo shell`: a fresh user in only `group_dealflow_admin` successfully wrote `df_max_discount` on the seeded Hardware category with zero DealFlow-specific ACL rows present. No new access row was needed or added — this is exactly the native-first outcome DEC-014 argues for, one layer further than the decision anticipated.

---

## DEC-015 — Pricelist price must be read via `pricelist._get_product_price()`

- **Date:** 2026-09-05
- **Decision:** Resolve a tier's pricelist-adjusted price with `pricelist._get_product_price(product, quantity, uom=..., date=...)`. Do **not** use `product.with_context(pricelist=...).price`.
- **Reason:** Found by Pam in DF-002-QA and independently confirmed against the installed Odoo 17 source: **there is no `price` field on `product.template` or `product.product`** — only `list_price` (template) and `lst_price` (product), neither of which is pricelist-aware. `product.pricelist._get_product_price()` is the supported API. The previous call raised `AttributeError: 'product.product' object has no attribute 'price'`, meaning the affected quotation line could not be saved at all.

  The bug was dormant only because no `product.pricelist` records exist yet. Seeding DEC-009's per-tier pricelists — an already-accepted decision — would have made **every quotation for every tier customer unsaveable**.

  DEC-009's *design* was never in question: comparing the rep's actual price against the pricelist-adjusted reference, so the pricelist's own reduction is never double-counted as rep discount, remains correct. This was a wrong-attribute-name defect inside a correct design.
- **Process note:** Michael reviewed this code and passed it, reasoning about the formula while assuming the attribute access was valid. Pam grepped the installed core source instead and was right. **Verify API surface against the installed version, not from memory** — the formula being right is not evidence that the field exists.
- **Status:** Accepted

---

## DEC-016 — `dealflow.negotiation` has no separate `.message` model; portal comments use native chatter

- **Date:** 2026-09-05
- **Decision:** `dealflow.negotiation` inherits `mail.thread` directly instead of pairing with a bespoke `dealflow.negotiation.message` model. Its `message_ids` is the native chatter field. Line-level comments/change requests (AT-08) post to the **quotation's own** chatter (`sale.order` already inherits `mail.thread`), with the target line named in the message body — no new comment model either.
- **Reason:** architecture.md §3.2's data-model table lists `dealflow.negotiation` with a `message_ids` field and no separate message-model row — that field name only makes sense as Odoo's own chatter mechanism, not a hand-rolled one (`docs/ui_spec.md` screen 11 mentions a `.message` model in passing, but the authoritative data-model table does not; this decision reconciles the two in favor of the table plus reuse). Reusing `mail.thread` gives per-message author/timestamp, portal-safe rendering, and backend visibility (reps see the same thread on the order) for free, instead of a parallel messaging system with none of that.
- **Alternatives considered:** *Custom `dealflow.negotiation.message` model* — rejected: duplicates `mail.message` for no capability gain and a second model to secure with its own record rule.
- **Status:** Accepted — binding on DF-014/DF-016.

---

## DEC-017 — Counter-discount is a single flat percentage applied to every discountable line

- **Date:** 2026-09-05
- **Decision:** `dealflow.negotiation.counter_discount` is one float percentage, written to every non-section/note line's `discount` field via a normal `write()` — never a per-line negotiation.
- **Reason:** architecture.md's data-model table gives `dealflow.negotiation` a single `counter_discount` field (not a one-to-many over lines), and the brief's negotiation flow (AT-08/AT-09) describes one customer-proposed discount per quotation. Writing through the native `discount` field means Atlas's existing DF-002/DF-003 compute chain (ceiling, excess, blended risk) recomputes automatically — this decision deliberately does not reimplement or duplicate that math anywhere in the portal layer.
- **Status:** Accepted — binding on DF-014. If per-line counter-offers are wanted later, that is a new field/UX on top of this model, not a replacement.

---

## DEC-018 — Amends DEC-012: a portal-group companion rule is required alongside the global rule

- **Date:** 2026-09-05
- **Decision:** Add `rule_dealflow_portal_sale_order_own_group` / `..._line_own_group` — the same `partner_id` domain as DEC-012's global rule, but scoped to `base.group_portal` (not global) — as companions to that global rule. Never modify or remove the native `sale` module rules.
- **Reason:** Live-verified in `tests/test_portal_isolation.py` under the real Odoo test runner: `sale`'s own portal rules (`sale_order_rule_portal`, `sale_order_line_rule_portal`, both in `odoo/addons/sale/security/ir_rules.xml`) are **follower-based** (`message_partner_ids child_of ...`), scoped to the portal *group*. Since group rules OR together but the resulting OR-set is still ANDed against DEC-012's global rule, a quotation whose customer was never added as a chatter follower (i.e. anything created via plain `create()` and never explicitly "sent") was unreadable **even to its own owner** — `test_portal_user_can_read_own_order` raised `AccessError` and `test_portal_user_search_excludes_other_customer` came back empty. Every cross-customer denial test still passed (no security regression), but the portal was a dead end for every legitimate customer.

  Adding our own rule to the *same* portal group changes the group-term from `(follower_domain)` to `(follower_domain OR partner_domain)`. Combined with the unchanged global rule: `partner_domain AND (follower_domain OR partner_domain)` reduces to exactly `partner_domain` (`A AND (B OR A) == A`) — provably no wider than the global rule already allows, it only stops the native rule's narrower OR-branch from being the sole gate.
- **Alternatives considered:**
  - *Make quotations auto-follow their customer on creation* — rejected for this pass: would require editing `sale_order.py` (Atlas's file under the concurrency lane rule) and conflates "who gets emailed" with "who has read access," which is exactly the coupling DEC-007/012 rejected in the first place.
  - *Modify/replace the native rule* — rejected, same reasoning as DEC-012.
- **Status:** Accepted — binding on DF-014/DF-016.

---

## DEC-019 — Portal status label is computed in the controller, not read from `df_pipeline_stage`

- **Date:** 2026-09-05
- **Decision:** `controllers/portal.py`'s `_dealflow_portal_status(order, has_negotiation)` derives the customer-facing status (Draft/Sent/Under Negotiation/Confirmed/Cancelled) from native `sale.order.state` plus whether any `dealflow.negotiation` exists for the order — it does not read or depend on `sale.order.df_pipeline_stage`.
- **Reason:** AT-08 requires the portal show "Sent / Under Negotiation / Confirmed." `df_pipeline_stage` (`models/sale_order.py`) is a different thing — its own docstring calls it "Mockup screen 3's Kanban grouping" for the *internal* workspace, its selection has no `sent` value at all, and today it only ever computes `draft`/`confirmed` (the `pending_approval`/`approved`/`negotiation` values are an explicit seam waiting on DF-004 and this task). Making the portal correct required a value this task's data (order.state + this model's own negotiation records) already fully determines — computing it here needed no change to `sale_order.py` (Atlas's lane) at all.
- **Status:** Accepted — binding on DF-014/DF-016. If Atlas's DF-004 later makes `df_pipeline_stage` cover `sent`/`negotiation` too, revisit whether the portal should switch to reading it instead of keeping a second definition — not urgent while the vocabularies differ (Kanban grouping vs. customer-facing status).

---

## DEC-020 — Seed/reference data that must reach already-installed databases belongs in a migration script, never `post_init_hook`

- **Date:** 2026-09-05
- **Decision:** `post_init_hook` (as used by `demo/demo_data.py`) only fires on module **install** (`-i`). Any new record this project wants present on a database that already has `dealflow360` installed — the curated `dealflow.upsell.rule` seed rows being the concrete case — must ship as a numbered **migration script** (`migrations/<version>/post-migrate.py` with a `migrate(cr, version)` function, module version bumped to match), guarded to be idempotent (skip records that already exist) so re-running or running against a manually-patched database is a no-op rather than an `IntegrityError`.
- **Reason:** DF-008's `_create_upsell_rules()` was added inside `post_init_hook` and passed its own install-time test cleanly, but `-u dealflow360` on every already-installed database (including the frozen demo db `dealflow360`) silently produced **zero** rows — caught only by god's post-integration integrity check expecting 3 rows and finding 0. A static XML `data/` file (Odoo's more common idempotent-seed idiom, keyed by xml-id) was considered but rejected for this specific case: the demo products these rules reference are created dynamically inside `post_init_hook` with no stable xml-id, so a data file loaded earlier in the manifest's `data` list has nothing to `ref()`. `odoo.conf` also sets `without_demo = all`, so routing this through the manifest's `demo` key (which would sidestep the missing-xmlid problem differently) never loads either. A migration script sidesteps both: it runs Python at the correct time (after the target records already exist in an upgrading database) and needs no xml-id, only a real-data lookup (`Product.search([("name", "=", ...)])`) matching how `post_init_hook` itself already identifies these products.
- **Alternatives considered:**
  - *Static XML data file with `ref()`* — rejected: demo products have no xml-id to reference (see above); would require first retrofitting xml-ids onto dynamically-created demo data, more invasive than the actual gap being fixed.
  - *Manifest `demo` key* — rejected outright: `without_demo = all` in `odoo.conf` means nothing there ever loads, on any database this project runs on.
  - *Leave it in `post_init_hook` and re-run `-i` (reinstall) whenever new seed data is added* — rejected: destructive/impractical against a frozen demo database that must never be dropped and recreated, and silently wrong for every other already-installed database (including every agent's own scratch db) with no error or warning.
- **Status:** Accepted. `migrations/17.0.1.1.0/post-migrate.py` (module version bumped `17.0.1.0.0` → `17.0.1.1.0`) is the first instance of this pattern; any future seed/reference data that must retroactively reach already-installed databases should follow the same shape rather than being added to `post_init_hook`.
