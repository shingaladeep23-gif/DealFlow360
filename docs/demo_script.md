# DealFlow360 — Five Minute Demo Script

**Setup before demoing:** stack running at `http://localhost:8069`, database `dealflow360` freshly seeded, three browser profiles ready (Rep, Manager, Customer).

**Seed facts the demo relies on**
- **Acme Corp** — Gold tier (15% general ceiling)
- Category ceilings: **Hardware 15%**, **Services 10%**
- Products: *ProBook Laptop* (Hardware), *Onsite Setup Service* (Services), *Core Plan* (recurring, yearly), *Docking Station* (Hardware, promoted upsell)
- Warehouses: **Main Warehouse** and **East Depot**, deliberately seeded so one laptop order must split

---

## FLOW 1 — Sales Rep: quote to fulfillment (≈3 min)

| # | Action | What the judge should see |
|---|---|---|
| 1 | Log in as the **sales rep**, open the Sales Workspace | Dashboard: pending approvals, open quotations, at-risk deals |
| 2 | Create a quotation for **Acme Corp** | Customer tier shows **Gold**, ceiling 15% |
| 3 | Add **ProBook Laptop**, discount **12%** | Line shows within limit — ceiling `min(15,15)=15`, 0 points over. Live margin indicator updates |
| 4 | Add **Onsite Setup Service**, discount **18%** | Line flags **8 points over** — ceiling is `min(15,10)=10`, not 15. *Say out loud: the customer is Gold, but Services are stricter* |
| 5 | Point at the **blended risk score** | Score **40 → MEDIUM**. Explain: revenue-weighted overshoot plus a worst-line term, so neither one bad line nor many small ones slip through |
| 6 | Accept an **upsell** suggestion (*Docking Station*, promoted) | Margin delta shown before adding; after adding, order total **and** margin update immediately — a real order line was written |
| 7 | Submit the quotation | It routes for approval **automatically** — the rep never clicked "request approval" |
| 8 | Switch to the **Sales Manager**, open Approvals | Approval detail: risk score, the offending line, approval timeline. Click **Approve** |
| 9 | Show the **audit trail** | User, timestamp and reason recorded for the approval |
| 10 | Open **Fulfillment** | Suggested split: e.g. 6 units from Main Warehouse, 4 from East Depot, with shipment count and cost. Click **Accept Suggested Split** → real stock pickings created; shortfall becomes a **backorder** |
| 11 | Open **Subscriptions / Billing** | One-time lines and the recurring *Core Plan* shown **separately** on the same order, with the upcoming billing schedule |

---

## FLOW 2 — Customer: portal negotiation to payment (≈2 min)

| # | Action | What the judge should see |
|---|---|---|
| 1 | Open the **customer portal** in a separate browser profile, log in as Acme Corp | A genuinely different, restricted UI — no internal menus, no margin, no risk score |
| 2 | **Security beat:** try to open another customer's quotation by ID | Access denied — blocked by an ORM record rule, not just a controller check |
| 3 | Open the quotation, add a **line-level comment** | Comment persists and is visible to the rep internally |
| 4 | Submit a **counter-discount** — push the Service line higher | Status becomes **Under Negotiation** |
| 5 | Back on the internal side, show the recalculated risk | Score recomputed; the order has **automatically re-entered the approval flow** — no one triggered it manually |
| 6 | As the **Sales Manager**, approve the renegotiated terms | New approval chain, new audit entry |
| 7 | As the **customer**, click **Confirm Quotation** | Order confirmed — a real sale order |
| 8 | Show the **invoice**, register a **payment** | `account.move` created; invoice status moves to **Paid** |
| 9 | Close on the **Deal Health dashboard** | Stalled deals, discount anomalies, approval delays, delivery slippage. Click an alert → opens the related quotation |

---

## Closing line (15 s)

> "Every number you saw came from application logic against real records — the risk score, the warehouse split, the billing schedule and the reapproval trigger are all computed, not staged. The formulas are documented in `docs/decisions.md`."

## What we'd build next

- Multi-currency and multi-company support (explicitly a bonus, not a requirement)
- Statistically-grounded anomaly detection once enough historical deal data exists
- Exact-optimisation warehouse allocation with real carrier rates
- Customer-facing negotiation history and quote versioning/diffs

---

## If something breaks mid-demo

- Approval didn't trigger → open the order form, the risk score field is computed and visible there
- Portal login issue → the internal Approvals list still proves routing and the audit trail
- Stack down → `docker compose up -d`, then re-seed
