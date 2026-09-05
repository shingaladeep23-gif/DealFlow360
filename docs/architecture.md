# DealFlow360 — Architecture

**Platform:** Odoo 17.0 Community · **Database:** PostgreSQL 15 · **Addon:** `addons/dealflow360/`

## 1. Runtime topology

```
docker compose
├── db     postgres:15          → volume postgres-data
└── odoo   odoo:17              → volume odoo-data, ./addons mounted at /mnt/extra-addons
          http://localhost:8069   database: dealflow360
```

## 2. Module layout

```
addons/dealflow360/
├── __manifest__.py          depends: base, mail, product, sale_management,
│                                     sale_stock, stock, account, portal
├── models/
│   ├── discount_tier.py     dealflow.discount.tier
│   ├── res_partner.py       + df_tier_id
│   ├── product.py           product.category + df_max_discount
│   │                        product.template + recurring/promo/margin fields
│   ├── sale_order.py        risk scoring, approval trigger, margin, deal health
│   ├── sale_order_line.py   per-line ceiling + excess + margin
│   ├── approval.py          dealflow.approval, dealflow.approval.step
│   ├── audit_log.py         dealflow.audit.log
│   ├── upsell.py            dealflow.upsell.rule + recommendation engine
│   ├── warehouse_split.py   dealflow.warehouse.split(.line) + allocation engine
│   ├── recurring.py         dealflow.recurring.plan, dealflow.billing.schedule
│   └── negotiation.py       dealflow.negotiation(.message)
├── controllers/portal.py    customer portal negotiation (restricted)
├── views/                   backend XML views + menus
├── static/src/              OWL components (upsell panel, risk gauge, dashboards)
├── security/                ir.model.access.csv + record rules + groups
├── data/                    default tiers, seed categories + ceilings, cron
├── demo/                    seed data (customers, products, warehouses, stock)
└── tests/                   Odoo unit tests
```

## 3. Data model

### 3.1 Extended native models

| Model | Added fields | Purpose |
|---|---|---|
| `res.partner` | `df_tier_id` → `dealflow.discount.tier`; native `property_product_pricelist` set from the tier (DEC-009) | customer tier + tier pricing |
| `product.category` | `df_max_discount` (float, %) | category discount ceiling |
| `product.template` | `df_is_recurring`, `df_recurring_plan_id` (added in DF-012), `df_is_promoted`, `df_min_margin` | subscription + upsell metadata |
| `sale.order` | `df_blended_risk_score`, `df_risk_level`, `df_approval_id`, `df_margin_pct`, `df_pipeline_stage`, `df_health_score`, `df_health_status`, `df_health_flags`, `df_health_reason`, `df_health_flagged_date`, `df_last_activity` | governance, pipeline, deal health (DEC-011) |
| `sale.order.line` | `df_effective_ceiling`, `df_excess_points`, `df_margin_pct`; subscription lifecycle `df_sub_state`, `df_sub_start_date`, `df_sub_next_bill_date`, `df_sub_end_date`, `df_mrr` (DEC-008) | per-line governance + subscription state |
| `stock.warehouse` | `df_shipping_cost_weight` (float) | DEC-006 allocation tie-break |

**Configuration (DEC-010):** `res.config.settings` + `ir.config_parameter` holds `dealflow.risk_high_min` (default 40) — the MEDIUM/HIGH routing boundary. The scoring formula stays in code; only the boundary is data.

**Pricing vs governance (DEC-009):** `product.pricelist` sets the *base price* per tier; the discount ceiling caps the *additional manual discount* on top of it. A line's `discount` is measured against the pricelist price — never double-count the pricelist reduction as rep discount when computing `excess_i`.

**Subscriptions (DEC-008):** there is no `dealflow.subscription` model. One recurring `sale.order.line` **is** one subscription; mockup screen 9 is an act_window over `sale.order.line` filtered on `df_is_recurring = True`.

### 3.2 Custom models

| Model | Key fields | Purpose |
|---|---|---|
| `dealflow.discount.tier` | `name`, `max_discount` | Bronze 5%, Silver 10%, Gold 15% |
| `dealflow.approval` | `order_id`, `state`, `risk_score`, `risk_level`, `step_ids` | approval chain per quotation |
| `dealflow.approval.step` | `approval_id`, `role`, `sequence`, `approver_id`, `state`, `reason`, `acted_on` | Sales Manager → Finance |
| `dealflow.audit.log` | `order_id`, `user_id`, `timestamp`, `action`, `detail` | immutable audit trail |
| `dealflow.upsell.rule` | `product_id`, `suggested_product_id`, `score`, `reason` | co-purchase pairing |
| `dealflow.warehouse.split` | `order_id`, `state`, `shipment_count`, `line_ids` | allocation plan |
| `dealflow.warehouse.split.line` | `split_id`, `order_line_id`, `warehouse_id`, `qty`, `is_backorder` | per-warehouse allocation |
| `dealflow.recurring.plan` | `name`, `interval` (monthly/quarterly/yearly), `proration`, `cancel_rule` | recurring plan |
| `dealflow.billing.schedule` | `order_id`, `order_line_id`, `date`, `amount`, `state`, `invoice_id` | billing timeline → `account.move` |
| `dealflow.negotiation` | `order_id`, `state`, `counter_discount`, `message_ids` | portal negotiation thread |

## 4. State machines

### Quotation (`sale.order`)
```
draft → (risk evaluated) ─┬─ risk NONE ──────────────→ approved/sale
                          └─ risk MEDIUM/HIGH → pending_approval
pending_approval → approved → sent → under_negotiation → confirmed(sale) → invoiced → paid
                 → rejected
                 → revision (back to draft)

under_negotiation → (terms changed beyond threshold) → pending_approval   [REAPPROVAL]
```

### Approval chain
```
MEDIUM: [Sales Manager]
HIGH:   [Sales Manager] → [Finance]
each step: pending → approved | rejected | revision
```

## 5. Backend / frontend boundary

- **Backend (Atlas):** all computation — risk scoring, ceilings, approval routing, allocation, billing schedule generation, health scoring, audit logging. Exposed as model fields + `@api.model` methods callable from ORM and RPC.
- **Frontend (Don):** XML views, menus, OWL components. Reads computed backend fields. **Never recomputes business logic client-side** — no duplicated formulas in JS.
- **Portal (Pam):** `controllers/portal.py`, separate templates under `/my/quotation/...`, guarded by record rules. Never renders internal-only fields.

## 6. Portal architecture

- Customers are `res.users` in group `base.group_portal`, linked to `res.partner`.
- Access via native Odoo portal (`portal` module) + access token on the order.
- **Record rule:** a portal user may only read `sale.order` where `partner_id` is their own partner (or a child contact). Enforced at ORM level, not in the controller.
- Controllers re-verify ownership/token before rendering. Defence in depth.
- Portal templates expose: lines, totals, status, comments, counter-discount field, confirm button. They must **not** expose margin, internal risk score, approval chain internals, or other customers' data.

## 7. Key controllers

| Route | Auth | Purpose |
|---|---|---|
| `/my/quotations` | user (portal) | list customer's own quotations |
| `/my/quotation/<id>` | user + token | quotation detail / negotiation screen |
| `/my/quotation/<id>/comment` | user | line-level comment / change request |
| `/my/quotation/<id>/counter` | user | counter-discount proposal → triggers re-evaluation |
| `/my/quotation/<id>/confirm` | user | customer confirmation → fulfillment or reapproval |

## 8. Major workflows

1. **Quote build** — rep adds lines → each line computes effective ceiling `min(tier, category)` and excess → order recomputes blended risk → routing decision.
2. **Approval** — risk MEDIUM/HIGH creates `dealflow.approval` with steps; every action writes `dealflow.audit.log`.
3. **Upsell** — deterministic ranking over `dealflow.upsell.rule` + co-purchase history + promotion flag, filtered by `df_min_margin`; adding a suggestion writes a real `sale.order.line` and margin recomputes.
4. **Fulfillment** — allocation engine reads live `stock.quant` per warehouse, greedily minimizes shipment count, produces a split plan; accepted plan generates real `stock.picking` records; shortfall → backorder.
5. **Hybrid billing** — one-time lines invoice natively; recurring lines generate `dealflow.billing.schedule` entries that materialize as real `account.move` invoices, with proration on mid-cycle change.
6. **Negotiation** — portal counter-discount rewrites line discounts → risk recomputed → if it now exceeds thresholds the order automatically re-enters the approval flow.
7. **Deal health** — scheduled cron + computed fields surface stalled deals, discount anomalies, approval delays, delivery slippage.

## 9. Integrations

Native Odoo only: `stock` (inventory/pickings), `account` (invoices/payments), `portal` (customer access), `mail` (chatter/audit context). No external services.
