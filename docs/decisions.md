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
