# DealFlow360 — UI Specification (DF-005a)

**Author:** Don · **Status:** Design-only, no code written · **Depends on:** `docs/architecture.md`, `docs/decisions.md`, `docs/task_plan.md`, `Mockup.jpeg` (18 screens)

This document maps every screen in `Mockup.jpeg` to a concrete Odoo implementation so that once Odoo is live (currently blocked — Docker/WSL2 down, see `docs/handoff.md`), implementation is fast and correct instead of designed at the keyboard.

For each screen: model, view type, fields (EXISTS / COMING `<task>` / MISSING), actions, menu, owner.

---

## Screen 1 — Login / Signup

- **Model:** `res.users` (native auth) — no custom model.
- **View type:** Native Odoo `/web/login` + `/web/signup`. Not a custom backend view.
- **Fields:** Email, Password — native, EXISTS. Company selector is native multi-company behavior and hides itself automatically since we run one `res.company`.
- **Actions:** Log In (native), Forgot Password (native reset flow), Login/Sign Up toggle (native `auth_signup`). "Sign Up" creates a `res.users` in `base.group_portal`; linking that user to the correct `res.partner` as a customer is Pam's concern (DF-014), not a view Don builds.
- **Menu:** none (pre-login).
- **Owner:** Don — trivial theming only (logo/title via `web.login` template inherit, no logic). Pam owns signup→partner linkage security.
- **Missing fields:** none.

---

## Screen 2 — Sales Dashboard / Home

- **Model:** aggregate — no single model.
- **View type:** OWL component registered as `ir.actions.client` (tag `dealflow_dashboard`), set as the action for the currently-placeholder `menu_dealflow_dashboard`, and as the app's root action.
- **Cards:**
  - "Pending Approvals" (count) — `dealflow.approval` count where `state='pending'`. Model/field EXISTS conceptually, engine — COMING DF-004.
  - "Open Quotations" (count) — `sale.order` count where `state in ('draft','sent')` — EXISTS today (native).
  - "At Risk Deals" (count) — `sale.order` count where `df_health_status` in the "at risk"/"critical" buckets — field named in architecture §3.1 — COMING DF-017.
- **Recent Activity feed** — latest N `dealflow.audit.log` entries (`action`, `detail`, `timestamp`) — model EXISTS — COMING DF-004. Note: a bullet like "East Depot stock updated for Order #2041" only appears if the warehouse-split acceptance flow (DF-010) also writes an audit log entry, not only approval actions — confirm with Atlas that DF-010 logs to `dealflow.audit.log` too.
- **Buttons:** "+ New Quotation" → new `sale.order` form (EXISTS, reuse existing action). "View Approvals" → Approvals list action (Screen 8, built in DF-006).
- **Menu:** Dashboard (placeholder today — this task assigns its action).
- **Owner:** Don.

---

## Screen 3 — Quotations (List / Pipeline)

- **Model:** `sale.order`.
- **View type:** Kanban grouped by pipeline stage as the primary view, with a "Switch to Table View" toggle to a tree view of the same action/domain (`view_mode="kanban,tree,form"`).
- **Columns:** Draft · Pending Approval · Approved · Negotiation · Confirmed.
  - **MISSING:** native `sale.order.state` (`draft/sent/sale/done/cancel`) cannot produce these 5 groups — "Pending Approval"/"Approved"/"Negotiation" don't exist on it. Need `sale.order.df_pipeline_stage` (Selection, stored, computed from `state` + `df_approval_id.state` + the negotiation record's state) purely for Kanban grouping/coloring.
- **Card content:** Customer (`partner_id.name`), Amount (`amount_total`) — EXISTS (native).
- **Actions:** "+ New Quotation" (new form). "Switch to Table View" (native view-mode toggle, no backend). Row/card click → Screen 4.
- **Menu:** Quotations — modifies the existing `action_dealflow_quotations` (currently `tree,form` only, built in DF-001) to add the kanban view and default to it.
- **Owner:** Don.

---

## Screen 4 — Quotation Detail: Q-1042 (Acme Corp)

- **Model:** `sale.order` form (inherits/reorganizes the native form; not a new model).
- **Header fields:** Customer (`partner_id`), Price List (`pricelist_id`) — EXISTS (native).
- **Line table:**
  | Column | Field | Status |
  |---|---|---|
  | Product | `product_id` | EXISTS |
  | Qty | `product_uom_qty` | EXISTS |
  | Price | `price_unit` | EXISTS |
  | Discount | `discount` | EXISTS (native) |
  | Limit | `sale.order.line.df_effective_ceiling` | COMING DF-002 |
  | Status (OK/Over Limit) | derived from `df_excess_points > 0` via view decoration | COMING DF-002 (no new field — presentation only) |
  | Margin % (goal: live margin) | `sale.order.line.df_margin_pct` | COMING DF-002 |
- **Order-level margin summary** (goal: live margin): `sale.order.df_margin_pct` — COMING DF-002.
- **Discount-risk badge** (goal: discount-risk info): `df_blended_risk_score` + `df_risk_level` — COMING DF-003. Compact reuse of the Screen 7/DF-006 risk gauge component.
- **Yellow flag banner** ("Discount exceeds category limit — flagged for approval"): composed from existing fields (offending product name + `df_excess_points` + `df_risk_level`) — pure string formatting, not a new business rule, so no field is strictly required. **Recommended MISSING (optional):** `sale.order.df_risk_summary` (Char, computed) so Atlas owns the exact wording/thresholds instead of Don guessing language tied to DEC-003.
- **Upsell and Cross-Sell Suggestions** (3-card teaser; full panel is DF-009 territory, this is the embedded summary): sourced from `dealflow.upsell.rule` + the recommendation engine — COMING DF-008. **MISSING:** an explicit callable, e.g. `sale.order.get_upsell_recommendations()` → `[{product_id, product_name, score, projected_margin_pct, reason}]`, ranked, filtered by `df_min_margin`. See summary list below — this is the single most important ask for DF-009.
- **Buttons:** "Save Draft" (native save). "Submit for Approval" → new method `sale.order.action_submit_for_approval()` — COMING DF-004 — runs DEC-003 routing and either auto-approves or creates `dealflow.approval` + steps.
- **Menu:** hangs off Quotations (Screen 3 row-click).
- **Owner:** Don.

---

## Screen 5 — Fulfillment Detail: Q-1042 (Acme Corp)

- **Model:** `dealflow.warehouse.split` (header) + `dealflow.warehouse.split.line` (rows).
- **View type:** form view, reached from Screen 6 row click.
- **Table columns:**
  | Column | Field | Status |
  |---|---|---|
  | Warehouse | `warehouse_id` | COMING DF-010 |
  | Qty Fulfilled | `qty` | COMING DF-010 |
  | Est. Shipments | split-level `shipment_count` (shown once in header, not per-row, to avoid inventing a per-line count) | COMING DF-010 |
  | Cost | **MISSING** — no cost field exists anywhere in the data model. DEC-006 mentions "configured shipping cost weight" as a tie-break input but it isn't modeled yet. |
- **MISSING field ask:** `stock.warehouse.df_shipping_cost_weight` (Float) and/or `dealflow.warehouse.split.line.df_estimated_cost` (Monetary, computed) — needed to render the "Cost" column and to make DEC-006's tie-break inspectable in the UI.
- **Yellow recommendation banner:** e.g. "Recommended 'Combine Shipments' strategy avoids extra cost/lead time." **Recommended MISSING (optional):** `dealflow.warehouse.split.df_recommendation_note` (Char, computed) so Atlas owns the rationale text.
- **Backorders:** `dealflow.warehouse.split.line.is_backorder` — COMING DF-010 — render as a badge.
- **Buttons:** "Accept Suggested Split" → `dealflow.warehouse.split.action_confirm()` (creates real `stock.picking`) — COMING DF-010. "Manual Override" → native editable line form (edit `warehouse_id`/`qty` per line before confirming), no extra backend beyond DF-010.
- **Menu:** Fulfillment (placeholder → this task assigns; list is Screen 6, detail here).
- **Owner:** Don.

---

## Screen 6 — Fulfillment and Stock (List)

- **View type:** OWL dashboard combining two read-only tables via RPC (`search_read`/`read_group`), same pattern as Screen 2 — a single Odoo tree view can't span two different models in one screen.
- **Table 1 "Live Stock":** Warehouse, Product, In Stock (`stock.quant.quantity`), Reserved (`reserved_quantity`), Available (computed) — ALL EXISTS natively on `stock.quant`. No new fields; group by warehouse+product.
- **Table 2 "Orders Awaiting Fulfillment":** Order (`sale.order.name`), Customer (`partner_id`), Status — reuse `dealflow.warehouse.split.state` (COMING DF-010) joined via `order_id`, no new field. Complexity/note (e.g. "dual-warehouse split", "backorder") — derived by aggregating `split.line_ids` (distinct warehouse count, any `is_backorder=True`) — presentation-only, no new field.
- **Yellow banner:** static guidance text.
- **Menu:** Fulfillment (this list is the landing screen for the menu; row click → Screen 5).
- **Owner:** Don.

---

## Screen 7 — Approval Detail: Q-1042 (Acme Corp)

- **Model:** `dealflow.approval` (header) + `dealflow.approval.step` (history table).
- **View type:** form view, opened from Screen 8 row click.
- **Top badges:** Risk badge ("Blended Risk: HIGH") from `dealflow.approval.risk_level` — COMING DF-004. "Recalculate Risk" button → confirm exact method name with Atlas (likely on `sale.order` or `dealflow.approval`) — COMING DF-003/DF-004.
- **"Why This Quote Was Flagged" table:** Line (`product_id.name`), Discount Given (`discount`), Line Allowed (`df_effective_ceiling`), Excess (`df_excess_points`) — ALL EXISTS by DF-002. (Mockup's 4th column was illegible in the source image; data-wise this is `df_excess_points` per DEC-003's per-line excess term — confirm wording with Michael.)
- **Yellow explanation banner:** composed from `risk_score` + the worst offending line per DEC-003's `max_excess`/`blended_excess` split. **Recommended MISSING (optional):** `dealflow.approval.explanation` (Text, computed) so Atlas owns the wording.
- **Approval chain stepper** (4 nodes: Submitted → Sales Manager → Finance → Confirmed, colored by state): driven by `step_ids` (`role`, `sequence`, `state`) — EXISTS by DF-004. Recommend a small custom OWL widget (not native `statusbar`) since chain length varies (MEDIUM = 1 step, HIGH = 2 steps) and role labels are dynamic.
- **History table:** Actor (`step.approver_id`), Action (`state`: Submitted/Approved/Rejected/Resubmitted), Date (`acted_on`), Note (`reason`) — ALL EXISTS on `dealflow.approval.step` (DF-004).
- **Buttons:** "Approve" / "Request Revision" / "Reject" → `dealflow.approval.step.action_approve()/action_revise()/action_reject()` — COMING DF-004. Confirm these also write `dealflow.audit.log` internally (Don just calls + refreshes).
- **Menu:** Approvals (list Screen 8 → row click).
- **Owner:** Don.

---

## Screen 8 — Approvals (List)

- **Model:** `dealflow.approval`, tree/list view.
- **Filter badges:** "N Pending" / "N Rejected" / "N Approved" — stat-filter buttons on `state` — COMING DF-004.
- **Table columns:** Quotation (`order_id.name`), Customer (`order_id.partner_id.name`), Risk Level (`risk_level`), Step (current pending step's role, e.g. "Sales Manager"/"Finance"/"Auto-Approved"), Pending/Approved By (`step.approver_id.name`) — ALL derivable from EXISTS fields by DF-004. **Recommended MISSING (optional):** `dealflow.approval.current_step_label` (Char, computed) so Don doesn't do multi-hop relational logic inside a list view.
- **Button:** "Filter: Pending Only" — native domain toggle, no backend.
- **Menu:** Approvals (placeholder → this task assigns the action; row click → Screen 7).
- **Owner:** Don.

---

## Screen 9 — Subscriptions (List)

- **MISSING (architecture gap):** there is no single "subscription" record in `docs/architecture.md` — only `dealflow.recurring.plan` and `dealflow.billing.schedule` (a schedule per invoice event, not per subscription). This screen needs a stable list of subscriptions with a lifecycle state (Active/Paused/Canceled), which neither existing model provides directly.
  - **Option A (recommended):** add a thin aggregate model `dealflow.subscription` (`order_id`, `plan_id`, `state`: active/paused/canceled, `next_bill_date`, `mrr`) computed/maintained alongside billing schedule generation.
  - **Option B:** Don aggregates `dealflow.billing.schedule` client-side via `read_group` (by `order_id`+plan) with no new model.
  - This is a decision Atlas/Michael need to make before DF-012/DF-013 — flagging as an open question, not proceeding on an assumption.
- **Filter badges:** "N Active" / "N Paused" / "N Canceled" — needs whichever state field results from the decision above.
- **Table columns:** Customer, Plan (`recurring_plan_id.name`), Cycle (`interval`) — EXISTS (DF-012 model); Next Bill (`dealflow.billing.schedule.date` where `state='pending'`) — EXISTS DF-012 (derivable); Status — per above.
- **Button label ambiguity:** the mockup's button reads "+ New Plan (Active)" but subscriptions originate from confirmed recurring order lines, not from a standalone "create subscription" action. Recommend treating this as an active-filter toggle rather than a create button — flagging for Michael to confirm the intended behavior.
- **Menu:** Subscriptions (placeholder → this task assigns the action).
- **Owner:** Don.

---

## Screen 10 — Billing Detail: Acme Corp - Care Plan 2yr

- **Model:** mixed — "One-Time Lines" reads `sale.order.line` where `product_id.df_is_recurring=False` on the originating order (EXISTS). "Recurring Lines" reads `dealflow.billing.schedule` rows: Plan (`recurring_plan_id.name`), Cycle (`interval`), Next Bill Date (`date`), Amount (`amount`) — ALL EXISTS/COMING DF-012.
- **Buttons:** "Modify Subscription" → triggers proration recompute — COMING DF-012, confirm exact method name. "Cancel Subscription" → applies `cancel_rule` (EXISTS field, DF-012) via a cancellation method — COMING DF-012, confirm method name.
- **Menu:** Subscriptions (Screen 9 row click → here).
- **Owner:** Don.

---

## Screen 11 — Customer Portal Negotiation Screen — **Pam's screen (not specified here)**

Per assignment, this is Pam's screen (DF-014). Internal touchpoint only: if Michael wants reps to see negotiation activity without leaving Screen 4, an optional read-only panel showing `dealflow.negotiation.state` and the latest `dealflow.negotiation.message` could be added to the Quotation Detail form — **not in DF-005/DF-006 scope unless explicitly requested**. Models `dealflow.negotiation` / `dealflow.negotiation.message` exist per architecture (owned by Pam, DF-014).

---

## Screen 12 — Invoices (List)

- **Model:** `account.move` (native), domain `move_type='out_invoice'`.
- **Filter badges:** "N Unpaid" / "N Paid" — native `payment_state` — EXISTS, zero custom work.
- **Table columns:** Invoice # (`name`), Customer (`partner_id`), Amount (`amount_total`), Status (`payment_state`), Due Date (`invoice_date_due`) — ALL EXISTS natively.
- **Menu:** Invoices (placeholder → this task assigns the action).
- **Owner:** Don. **Missing fields: none** — purely native `account.move`.

---

## Screen 13 — Invoice Detail: INV-1042 (Acme Corp)

- **Model:** `account.move` form (native, re-skinned to match mockup layout — not rebuilt).
- **Status stepper** (Sale Confirmed → Issued → Invoiced → Paid): doesn't map 1:1 to any single native field. Recommend a small presentational OWL stepper deriving its 4 positions from `(sale.order.state, account.move.state, account.move.payment_state)` — pure display logic over existing native fields, no new field.
- **Table:** Invoice #, Amount, Status, Due Date (same as Screen 12) plus a linked reversal row via native `reversed_entry_id`/`reversal_move_id` — ALL EXISTS.
- **Buttons:** "Confirm Payment" → native `action_register_payment` wizard. "Download Invoice" → native `account.report_invoice`. Both zero custom backend.
- **Menu:** Invoices (Screen 12 row click → here).
- **Owner:** Don. **Missing fields: none.**

---

## Screen 14 — Deal Health and Anomaly Dashboard

- **Model:** `sale.order` aggregate, OWL dashboard (same pattern as Screen 2).
- **Cards:** "Stalled Deals", "Discount Anomalies", "Delivery Slippage" — counts per DEC-005's four signals.
  - **MISSING (important — the load-bearing ask for DF-018):** DEC-005 defines four penalty *signals* (stalled / discount anomaly / approval delay / delivery risk) feeding one blended `df_health_score`/`df_health_status`, but architecture §3.1 only lists the blended outputs, not the individual signal breakdown. Need `sale.order.df_health_flags` (Selection or Many2many tags: `stalled`, `discount_anomaly`, `approval_delay`, `delivery_risk`) so each card can count/filter by signal without Don re-deriving DEC-005's thresholds client-side.
  - **MISSING:** `sale.order.df_health_reason` (Text, computed) — human-readable issue text (e.g. "Discount 22% vs avg 8%") for the table's "Issue" column, same treatment as the risk-explanation asks above.
  - **MISSING:** `sale.order.df_health_flagged_date` (Datetime) — when the issue was first detected, for the "Flagged" column.
- **Table columns:** Deal, Issue, Flagged, Action — Action label (e.g. "Nudge Rep"/"Escalate") can be a static per-flag-type lookup in the view, no new field needed.
- **Buttons:** "Escalate" / "Nudge Rep" — recommend native `mail.activity`/message post on the order rather than a new model (confirm with Michael that no dedicated escalation model is wanted).
- **Menu:** Deal Health (placeholder → this task assigns the action).
- **Owner:** Don.

---

## Screen 15 — Admin / Reporting Dashboard (Optional, lowest priority)

- Explicitly marked optional in the mockup.
- **Filters:** Date range, Sales Rep, Customer Tier, Product — all native (`date_order`, `user_id`, `partner_id.df_tier_id`, line `product_id`) — EXISTS, no missing fields.
- **Cards:** "Quotes Created" (native count), "Avg Approval Time" (derivable via `read_group` over `dealflow.approval.create_date`→last step `acted_on`; **optional MISSING**: a stored `dealflow.approval.duration_days` would speed this up but isn't required), "Top Discount Products" (native `read_group` on `sale.order.line`).
- **Buttons:** "Export CSV"/"Export PDF" — native Odoo list export / report action, zero custom backend.
- Recommend implementing as a native Odoo Pivot/Graph view rather than custom OWL, given its optional status and everything being natively derivable.
- **Menu:** Reports (placeholder → this task assigns the action, lowest priority).
- **Owner:** Don.

---

## Screen 16 — Product catalog

- **Model:** `product.template` — menu + action already exist from DF-001 (`menu_dealflow_products` → `action_dealflow_product_template`); this task only refines the view.
- **Stat cards:** Total Products, Promoted (`df_is_promoted=True`, EXISTS DF-001), Variants — all via `read_group`/count, no new fields.
- **Table columns:** Product Name, Category (`categ_id`... actually `category_id`), Variants, Price (`list_price`), Max Discount (`category_id.df_max_discount`, EXISTS DF-001), Tax, Status (`active`) — ALL EXISTS.
- **Buttons:** "+ New Product" → Screen 17 form. "Manage Price Lists" → native `product.pricelist` list action.
- **Menu:** Products (already wired; low priority, cosmetic refinement only).
- **Owner:** Don.

---

## Screen 17 — Product and price list (Product Detail form)

- **Model:** `product.template` form (DealFlow360 tab already exists per DF-001's `product_views.xml`).
- **Fields:** name, `category_id`, `list_price`, `uom_id`, `description_sale`, `taxes_id` — ALL EXISTS (native). Subscription Yes/No → `df_is_recurring` (EXISTS DF-001), with conditional visibility (`attrs`/`invisible`, native XML, no backend) revealing Recurring Cycle when true. Recurring Cycle → needs `product.template.df_recurring_plan_id` → `dealflow.recurring.plan.interval` — **per DF-001 handoff, this field was intentionally deferred until DF-012** (the plan model doesn't exist yet); confirm it lands with DF-012 before this form ships. Quantity on hand → native `qty_available` (EXISTS, read-only).
- **Variants table:** native `product.template.attribute.line`/`attribute.value` — EXISTS, zero custom fields.
- **Price Rules table** (Tier / Currency / "Price, no adjustment" / "Price minus 10 percent base"): **ARCHITECTURE QUESTION for Michael** — this implies a second, distinct pricing mechanism (automatic tier-based price adjustment) from the existing discount-tier *ceiling* system (`dealflow.discount.tier.max_discount` governs the maximum discount a rep may apply — it does not auto-adjust list price by tier). Recommend using native `product.pricelist` (one pricelist per tier, assigned via `res.partner.property_product_pricelist`) rather than inventing a new model. **Needs a decision before this panel is built.**
- **Yellow banner:** proration note, ties to `dealflow.recurring.plan.proration` (EXISTS DF-012 concept).
- **Menu:** Products (Screen 16 row click / "+ New Product").
- **Owner:** Don.

---

## Screen 18 — Discount tiers and approval chains (Admin config)

- **Model:** `dealflow.discount.tier` (left table) + `dealflow.category.limit` (right table) — BOTH EXIST, views already built in DF-001 (`discount_tier_views.xml`) under Configuration.
- **"Tier Discount Ceilings" routing table** (Within limit → No approval / Over limit + medium risk → Sales Manager / Over limit + high risk → Sales Manager then Finance): this is a **read-only reflection of DEC-003's routing thresholds** (the 40-point boundary, NONE/MEDIUM/HIGH), which are defined as **code constants**, not data records. **ARCHITECTURE QUESTION for Michael:** the mockup's "Save configuration" button implies this third table is editable, but nothing in `docs/decisions.md` proposes making DEC-003's thresholds admin-configurable. Recommend rendering this panel as static/read-only (sourced from a small constant, not a model) and keeping "Save configuration" scoped to the two real config tables only — unless Michael wants the threshold promoted to an `ir.config_parameter`.
- **Menu:** Configuration → Discount Tiers / Category Limits (already exist from DF-001). Low priority: may consolidate into one page matching the mockup, or leave as the two existing separate config menus — functionally already covered.
- **Owner:** Don, low priority.

---

## Summary 1 — Backend fields/methods I need (route to Atlas)

Ranked by how much they block the vertical slice (quotation builder → risk display → approval UI) vs. later phases.

**Blocks DF-005 (vertical slice, highest priority):**
1. `sale.order.df_pipeline_stage` (Selection: `draft`/`pending_approval`/`approved`/`negotiation`/`confirmed`, stored, computed) — Screen 3 Kanban grouping. Nothing today maps native `state` to these 5 buckets.
2. `sale.order.get_upsell_recommendations()` — callable returning `[{product_id, product_name, score, projected_margin_pct, reason}]`, ranked, filtered by `df_min_margin` — Screen 4's embedded upsell teaser and the full DF-009 panel.

**Blocks DF-006:**
3. (Optional but recommended) `dealflow.approval.explanation` (Text, computed) and/or `sale.order.df_risk_summary` (Char, computed) — human-readable "why flagged" wording per DEC-003, so Atlas owns the threshold language instead of Don guessing it.
4. (Optional) `dealflow.approval.current_step_label` (Char, computed) — Screen 8's "Step" column without multi-hop relational logic in a list view.

**Blocks DF-011:**
5. `stock.warehouse.df_shipping_cost_weight` (Float) and/or `dealflow.warehouse.split.line.df_estimated_cost` (Monetary, computed) — Screen 5's "Cost" column; also makes DEC-006's tie-break rule inspectable.
6. (Optional) `dealflow.warehouse.split.df_recommendation_note` (Char, computed) — Screen 5's recommendation banner text.

**Blocks DF-013:**
7. **Decision needed:** subscription lifecycle aggregate for Screen 9 — either a new `dealflow.subscription` model (`order_id`, `plan_id`, `state`, `next_bill_date`, `mrr`) or an explicit go-ahead for Don to aggregate `dealflow.billing.schedule` client-side via `read_group`. Recommend the new thin model.
8. Confirm `product.template.df_recurring_plan_id` still lands with DF-012 as planned (already flagged as intentionally deferred in the DF-001 handoff) — needed for Screen 17.

**Blocks DF-018 (lower priority — dashboards, built last):**
9. `sale.order.df_health_flags` (Selection or Many2many tags: `stalled`/`discount_anomaly`/`approval_delay`/`delivery_risk`) — itemizes DEC-005's four signals individually; architecture currently only exposes the blended `df_health_score`/`df_health_status`.
10. `sale.order.df_health_reason` (Text, computed) — human-readable issue text per flagged deal.
11. `sale.order.df_health_flagged_date` (Datetime) — when each issue was first detected.
12. (Optional, Screen 15 is itself optional) `dealflow.approval.duration_days` (computed) — speeds up an "Avg Approval Time" report card.

**Architecture questions for Michael (not field asks — decisions needed before implementation):**
- **Screen 17** "Price Rules" table implies automatic per-tier price adjustment, which is a different mechanism from the existing discount-tier *ceiling* system. Recommend native `product.pricelist` per tier; needs sign-off.
- **Screen 18** "Tier Discount Ceilings" bottom panel implies DEC-003's routing thresholds are admin-editable data; DEC-003 currently defines them as code constants. Recommend keeping them read-only/static unless Michael wants them promoted to configurable settings.
- **Screen 9** button labeled "+ New Plan (Active)" — likely a filter toggle, not a create action, since subscriptions originate from confirmed recurring order lines. Needs confirmation of intended behavior.

---

## Summary 2 — Proposed implementation order (Don's tasks)

Respecting: vertical slice first (quotation builder → risk display → approval UI), dashboards/reporting last.

1. **DF-005a** *(this document)* — done.
2. **DF-005b** — Quotation Detail (Screen 4): lines, discount/limit/status columns, live margin, risk badge, flag banner, Save Draft/Submit for Approval. This is the core builder everything else is tested against.
3. **DF-005c** — Quotations List/Pipeline (Screen 3): Kanban + table toggle. Needs `df_pipeline_stage` from Atlas first.
4. **DF-005d** — Sales Dashboard (Screen 2): can start with partial counts (Open Quotations works today) and backfill Pending Approvals / At Risk Deals as DF-004/DF-017 land.
5. **DF-006** — Approvals List + Detail (Screens 8, 7): risk gauge, approval chain stepper, approve/revise/reject. Depends on DF-004.
6. **DF-009** — Full upsell/cross-sell panel (extends Screen 4's teaser with margin delta detail). Depends on DF-008.
7. **DF-011** — Fulfillment List + Detail (Screens 6, 5): stock view, split acceptance, backorders. Depends on DF-010.
8. **DF-013** — Invoices List + Detail (Screens 12, 13) first (pure native `account.move`, no dependency on DF-012), then Subscriptions List + Billing Detail (Screens 9, 10) once DF-012 and the subscription-aggregate decision land.
9. **DF-018** — Deal Health dashboard (Screen 14), then optional Admin/Reporting (Screen 15) last. Depends on DF-017.
10. **Interleaved, low priority, whenever convenient:** Screens 16/17/18 (Products, Product detail, Discount tiers admin) — mostly already functional from DF-001; polish only, never blocking.
11. Screen 1 (Login theming) — trivial, no dependency, can slot in anytime.

---

## Mockup vs. architecture conflicts flagged for Michael

1. Screen 3's Kanban pipeline has no backing field today (`df_pipeline_stage` missing) — see Summary 1 #1.
2. Screen 9 (Subscriptions) has no backing "subscription" record — architecture only models plans and billing schedule *events* — see Summary 1 #7.
3. Screen 14 (Deal Health) needs per-signal breakdown fields that DEC-005 computes internally but doesn't expose individually — see Summary 1 #9–11.
4. Screen 17's per-tier "Price Rules" table describes automatic price adjustment, which is conceptually different from the discount-ceiling governance system already built — needs a native-pricelist-vs-new-model decision.
5. Screen 18's routing-table panel implies DEC-003's thresholds are editable data; DEC-003 defines them as code constants — needs a read-only-vs-configurable decision.
