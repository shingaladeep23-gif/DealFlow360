# DealFlow360 — Acceptance Tests

Derived directly from the problem statement (§9 "Quick Test Flow" and §10 "Blended Discount Risk Score") and the mockup. Each test must produce a **visible, correct result** backed by a real database record — not a demo-only value.

Status: ⬜ not yet verified · ✅ passing · ❌ failing

---

## AT-01 — Authentication and backend setup
⬜ An internal user can sign up / log in and reach the sales workspace.
⬜ A customer can log in to the portal and sees **only** the portal, never internal screens.
⬜ Admin can create: a discount tier, a warehouse, and a subscription plan, and each persists as a real record.

## AT-02 — Discount governance: per-line ceilings
⬜ Customer tier ceilings exist and are configurable: Bronze 5%, Silver 10%, Gold 15%.
⬜ Category ceilings exist and are configurable: Hardware 15%, Services 10%.
⬜ Effective ceiling for a line = `min(tier ceiling, category ceiling)`.
⬜ **Spec worked example:** Gold customer, Laptop (Hardware) at 12% → within limit, no flag.
⬜ **Spec worked example:** Gold customer, Setup Service at 18% vs 10% allowed → 8 points over → the **whole quotation** is flagged for approval.

## AT-03 — Blended risk score (DEC-003)
⬜ All lines within ceilings → risk level **NONE**, no approval required.
⬜ Spec example (Laptop 12%/1000 + Setup Service 18%/500) → score **40** → **MEDIUM** → Sales Manager.
⬜ Many small violations (2, 3, 2 points over) → score **23** → **MEDIUM** → approval still required (must not slip through).
⬜ Severe overshoot → score **> 40** → **HIGH** → Sales Manager **then** Finance.
⬜ Score is recomputed automatically whenever a line's discount, quantity or price changes.

## AT-04 — Automatic approval routing
⬜ Confirming an over-limit quotation routes it for approval **automatically** — the rep never requests approval manually.
⬜ MEDIUM risk creates exactly one step: Sales Manager.
⬜ HIGH risk creates two ordered steps: Sales Manager → Finance; Finance only becomes actionable after the manager approves.
⬜ Approve / Reject / Return-for-revision each work and move the order to the correct state.
⬜ Every approval, rejection and edit is logged with **user, timestamp and reason**.

## AT-05 — Upsell / cross-sell
⬜ While building a quote, a ranked suggestion panel is shown alongside the cart.
⬜ Each suggestion displays the product, the **margin delta if added**, and a promotion tag where applicable.
⬜ Suggestions below the configured minimum margin threshold are excluded.
⬜ "Add to Quote" writes a **real** `sale.order.line`; order total and margin indicator update immediately.
⬜ "Dismiss" removes the suggestion without altering the order.

## AT-06 — Multi-warehouse fulfillment
⬜ Stock levels come from real `stock.quant` records — no hardcoded availability anywhere.
⬜ The engine proposes a split showing warehouse name, quantity from each, and estimated shipment count/cost.
⬜ An order that cannot be filled from one warehouse splits across two.
⬜ The split minimizes the number of shipments (DEC-006).
⬜ "Accept Suggested Split" generates real `stock.picking` records.
⬜ "Manual Override" lets a user reassign quantities and the result is honoured.
⬜ Unfulfillable quantity becomes a **backorder**; a "Consolidate Remaining Backorder" prompt appears when stock arrives.

## AT-07 — Hybrid billing
⬜ A single order mixes one-time product lines and recurring subscription lines.
⬜ One-time and recurring lines are displayed **separately** on the same order.
⬜ An upcoming billing schedule is shown for recurring lines.
⬜ Recurring lines generate **real `account.move` invoices** on schedule — not a display-only table.
⬜ A mid-cycle quantity change produces correct **proration**.
⬜ Cancelling/modifying a subscription triggers a partial refund or credit note where applicable.

## AT-08 — Customer portal negotiation
⬜ The portal is a genuinely separate, restricted view — not an internal screen relabelled.
⬜ Customer sees quotation details and current status (Sent / Under Negotiation / Confirmed).
⬜ Customer can leave a **line-level** comment or change request.
⬜ Customer can submit a **counter-discount** proposal.
⬜ **Security:** a customer requesting another customer's quotation receives 403/404 — never the document. Verified at the ORM record-rule level, not only in the controller.
⬜ **Security:** a portal user cannot reach internal Odoo backend screens.
⬜ **Security:** the portal never exposes margin, internal risk score, or approval-chain internals.

## AT-09 — Automatic reapproval after negotiation
⬜ A customer counter-discount that pushes terms beyond thresholds **automatically** re-enters the approval flow.
⬜ A counter-discount that stays within thresholds moves the order directly to fulfillment.
⬜ Reapproval creates a fresh approval chain and a new audit entry.
⬜ "Confirm Quotation" from the portal confirms the real order.

## AT-10 — Invoice and payment
⬜ Confirming the order produces a real invoice (`account.move`).
⬜ Recording a payment updates the invoice status correctly (e.g. to Paid).

## AT-11 — Deal health and anomalies
⬜ Stalled deals (inactive beyond a configured number of days) are surfaced.
⬜ Discount anomalies (well above the rep's historical average) are surfaced.
⬜ Delivery promise slippage indicators are surfaced.
⬜ Clicking an alert opens the related quotation directly.
⬜ A nudge/escalation action can be triggered from an alert.
⬜ The scoring methodology is documented (DEC-005).

## AT-12 — Reporting
⬜ Reports filter by Period, Sales Team / Rep, Approval Status, and Product / Category.
⬜ Export to PDF / XLS works.

## AT-13 — End-to-end demo flows
⬜ **Flow 1:** login → quotation → over-limit discount → risk detection → automatic routing → manager approval → upsell → margin update → warehouse split → hybrid billing.
⬜ **Flow 2:** portal → view quotation → counter discount → risk recalculation → automatic reapproval → manager approval → customer confirmation → invoice/payment → deal health.
⬜ Both flows demonstrate **actual system state changes** in the database.

## AT-14 — Engineering hygiene
⬜ The module upgrades cleanly with no errors in the server log.
⬜ No errors in the browser console during either demo flow.
⬜ Backend unit tests pass.
⬜ Seed data loads reproducibly from scratch.
