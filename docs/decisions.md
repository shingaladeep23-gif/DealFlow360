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
- **Status:** Accepted

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
