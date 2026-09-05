# DealFlow360 — Architecture (one page)

Deliverable 3: the data model, and how the major modules connect.

Everything is one Odoo 17 addon, `addons/dealflow360/`. Native models are
**extended**, never replaced; new models are namespaced `dealflow.*`. Native
models are shaded in the diagrams below by naming convention: `sale.order`,
`product.*`, `stock.*`, `account.move`, `res.partner` are Odoo's own.

## Data model

```mermaid
erDiagram
    res_partner ||--o| dealflow_discount_tier : "df_tier_id"
    product_category ||--o{ product_template : "categ_id"
    product_template ||--o| dealflow_recurring_plan : "df_recurring_plan_id"

    sale_order ||--o{ sale_order_line : "order_line"
    sale_order }o--|| res_partner : "partner_id"
    sale_order_line }o--|| product_template : "product_id"

    sale_order ||--o| dealflow_approval : "df_approval_id"
    dealflow_approval ||--o{ dealflow_approval_step : "step_ids"
    sale_order ||--o{ dealflow_audit_log : "df_audit_log_ids"
    sale_order ||--o{ dealflow_negotiation : "df_negotiation_ids"

    sale_order ||--o{ dealflow_warehouse_split : "df_split_ids"
    dealflow_warehouse_split ||--o{ dealflow_warehouse_split_line : "line_ids"
    dealflow_warehouse_split_line }o--|| stock_warehouse : "warehouse_id"
    dealflow_warehouse_split ||--o{ stock_picking : "picking_ids"

    sale_order_line ||--o{ dealflow_billing_schedule : "billing_schedule_ids"
    dealflow_billing_schedule ||--o| account_move : "invoice_id"

    product_product ||--o{ dealflow_upsell_rule : "trigger / suggestion"
    sale_order }o--o{ dealflow_health_flag : "df_health_flags"
```

### The fields that carry the business rules

| Where | Field | What it decides |
|---|---|---|
| `product.category` | `df_max_discount` | Category ceiling. **0 means unset**, not 0%. |
| `dealflow.discount.tier` | `max_discount` | Tier ceiling, same convention. |
| `sale.order.line` | `df_effective_ceiling` | Strictest configured axis, else `dealflow.default_max_discount`. |
| `sale.order.line` | `df_excess_points` | Points past that ceiling, measured against the **pricelist** price (DEC-009), so a pricelist reduction is never double-counted as rep discount. |
| `sale.order` | `df_blended_risk_score` | `min(100, 6·blended_excess + 3·max_excess)`, weighted by each line's **pre-discount** value. |
| `sale.order` | `df_risk_level` | `none` is structural (no line over its ceiling); `medium`/`high` split at `dealflow.risk_high_min`. |
| `sale.order` | `df_governance_fingerprint` | Digest of tier + every line's product/qty/price/discount. **This is what an approval is bound to.** |
| `dealflow.approval` | `order_fingerprint` | The fingerprint as it stood when approvers were shown the deal. |
| `stock.warehouse` | `df_shipping_cost_weight` | Tie-break when two warehouses could source equally. |

## How the modules connect

```mermaid
flowchart TD
    subgraph Config["Configuration (A2-A6)"]
        TIER[dealflow.discount.tier]
        CAT[product.category.df_max_discount]
        PLAN[dealflow.recurring.plan]
        RULE[dealflow.upsell.rule]
        WH[stock.warehouse + weight]
    end

    QUOTE["Quotation<br/>sale.order + lines"]
    RISK{{"Risk engine<br/>_compute_df_governance<br/>_compute_df_risk"}}
    UPSELL["Upsell panel<br/>get_upsell_recommendations"]
    APPROVAL["Approval chain<br/>dealflow.approval + steps"]
    CONFIRM{{"action_confirm<br/>_df_covers gate"}}
    SPLIT["Allocation engine<br/>dealflow.warehouse.split"]
    BILLING["Billing engine<br/>dealflow.billing.schedule"]
    PORTAL["Customer portal<br/>/my/quotation"]
    NEGO["dealflow.negotiation"]
    HEALTH["Deal health<br/>4 signals + cron"]
    AUDIT[("dealflow.audit.log")]

    TIER --> RISK
    CAT --> RISK
    RULE --> UPSELL
    UPSELL -->|adds a real line| QUOTE
    QUOTE --> RISK
    RISK -->|medium / high| APPROVAL
    RISK -->|none| CONFIRM
    APPROVAL -->|every step approved<br/>AND fingerprint matches| CONFIRM
    CONFIRM --> SPLIT
    CONFIRM --> BILLING
    WH --> SPLIT
    PLAN --> BILLING
    SPLIT --> PICK[stock.picking per warehouse]
    BILLING --> INV[account.move]
    QUOTE --> PORTAL
    PORTAL -->|counter-discount| NEGO
    NEGO -->|rep accepts| QUOTE
    QUOTE --> HEALTH
    HEALTH -->|nudge / escalate| ACT[mail.activity]
    APPROVAL --> AUDIT
    NEGO --> AUDIT
    QUOTE -->|edit voids a decision| AUDIT
```

## The seam that matters most

An approval is a decision about a **specific** set of lines, not a permanent
licence for the quotation to confirm:

```mermaid
sequenceDiagram
    participant Rep
    participant Order as sale.order
    participant Chain as dealflow.approval
    participant Mgr as Manager / Finance

    Rep->>Order: Confirm at 20% discount
    Order->>Chain: _create_for_order (snapshots fingerprint)
    Note over Chain: state=pending
    Rep->>Order: edits the line to 60%
    Order->>Chain: _df_invalidate_stale_approvals
    Note over Chain: fingerprint no longer matches<br/>state=superseded + audit row
    Mgr->>Chain: Approve
    Note over Chain: acts on a retired chain
    Rep->>Order: Confirm
    Order-->>Rep: refused - routed afresh at the new numbers
```

Confirmation requires **all three**: the chain approved, *every* step approved,
and the fingerprint still matching. Each was independently exploitable before.

## Enforcement layers

Governance is enforced in the model, not in the UI:

| Layer | Mechanism |
|---|---|
| ACL | `ir.model.access.csv` — approver roles are read-only on approval models |
| Record rule | Global `user.share` rule scopes portal users to their own partner |
| Model guard | `create`/`write` on `dealflow.approval[.step]` refuse decision fields outside the engine context — binds admin and dev mode too |
| Gate | `action_confirm` → `_df_covers()` |
| Controller | Portal confirm/counter re-check server-side, never trusting a disabled button |

## Scheduled work

| Cron | Does |
|---|---|
| `_cron_generate_recurring_invoices` | Bills due schedule entries, queues the next cycle. Skips orders that are not confirmed. |
| `_cron_compute_deal_health` | Re-scores open deals; two of the four signals are functions of elapsed time and cannot be `@api.depends`. |
