# DealFlow360

An intelligent, self-governing B2B sales operations platform built on **Odoo 17 Community**.

Most sales tools handle the basics: create a quote, confirm an order, invoice it. Real B2B teams operate in messier conditions — multi-level discount approvals, partial stock spread across warehouses, subscriptions bundled with one-time hardware, customers who want to negotiate in a portal instead of over email, and managers who discover a deal is stuck only after it has lost momentum.

DealFlow360 goes beyond a quote-to-invoice form and becomes a **self-governing deal engine**: it enforces pricing discipline, reacts to inventory reality in real time, keeps subscriptions and one-time sales reconciled on a single order, and gives reps and customers a living, negotiable document instead of a static PDF.

## Capabilities

- **Multi-tier discount governance** — ceilings per customer tier *and* per product category; the effective limit on any line is the stricter of the two
- **Blended discount risk scoring** — catches both a single badly over-limit line and many small violations accumulating across an order
- **Automatic approval routing** — Sales Manager, escalating to Finance on high risk, with no manual request step
- **Live upsell / cross-sell** — ranked, deterministic suggestions with real-time margin impact
- **Multi-warehouse fulfillment** — live stock-driven splitting that minimizes shipments, with manual override and backorders
- **Hybrid billing** — one-time products and recurring subscription lines on one order, with proration
- **Customer portal negotiation** — a genuinely restricted customer view with counter-discounts and automatic reapproval
- **Deal health and anomaly detection** — stalled deals, discount anomalies, approval delays, delivery slippage
- **Full audit trail** — every approval, rejection and edit logged with user, timestamp and reason

## Quick start

**Prerequisites:** Docker Desktop running.

```bash
git clone https://github.com/shingaladeep23-gif/DealFlow360.git
cd DealFlow360
docker compose up -d
```

Open <http://localhost:8069> and select the `dealflow360` database.

Useful commands:
```bash
docker compose logs -f odoo     # server logs
# upgrade the module after code changes:
docker compose exec odoo odoo -d dealflow360 -u dealflow360 --stop-after-init
```

## Business logic highlights

### Effective discount ceiling

A line's ceiling is `min(customer tier ceiling, product category ceiling)`.

A Gold customer is allowed 15% generally — but Services are capped at 10% because their margins are thin. So an 18% discount on a setup service is **8 points over its limit**, and the whole quotation is flagged for approval even though "15%" sounded fine on paper.

### Blended risk score

```
excess_i   = max(0, discount_i − min(tier_ceiling, category_ceiling))
weight_i   = line_subtotal_i / order_subtotal

risk_score = min(100, 6 × Σ(excess_i × weight_i) + 3 × max(excess_i))
```

| Risk | Condition | Approval chain |
|---|---|---|
| NONE | every line within its ceiling | none |
| MEDIUM | `0 < score ≤ 40` | Sales Manager |
| HIGH | `score > 40` | Sales Manager → Finance |

The weighted term accumulates many small overshoots; the max term ensures one badly over-limit line always trips approval on its own. Full rationale and worked examples in [`docs/decisions.md`](docs/decisions.md) (DEC-003).

## Architecture

Single Odoo addon at `addons/dealflow360/`, extending native models (`sale.order`, `sale.order.line`, `res.partner`, `product.template`, `product.category`, `stock.*`, `account.move`) and adding `dealflow.*` models for governance, approvals, allocation, billing schedules and negotiation.

See [`docs/architecture.md`](docs/architecture.md) for the data model, state machines and module boundaries.

## Documentation

| Document | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Engineering contract and git rules |
| [`AGENTS.md`](AGENTS.md) | Team roles and working agreement |
| [`docs/architecture.md`](docs/architecture.md) | Architecture, data model, workflows |
| [`docs/decisions.md`](docs/decisions.md) | Architectural decision record |
| [`docs/task_plan.md`](docs/task_plan.md) | Phases, status, assignments |
| [`docs/handoff.md`](docs/handoff.md) | Rolling engineering handoff log |
| [`docs/acceptance_tests.md`](docs/acceptance_tests.md) | Problem statement as explicit tests |
| [`docs/demo_script.md`](docs/demo_script.md) | Five-minute demo walkthrough |

## Source material

- `DealFlow360.pdf` — problem statement
- `Mockup.jpeg` — product flow and UI reference ([Excalidraw](https://app.excalidraw.com/l/65VNwvy7c4X/7Fb5SR3WKu2))
