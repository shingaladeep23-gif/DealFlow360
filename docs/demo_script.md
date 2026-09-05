# DealFlow360 — Demo Script

**Every step below was executed against the live stack before being written down.**
Nothing here is aspirational. If a step is unverified it says so explicitly.

Last rehearsed: 2026-09-05, by Michael (integrator).

---

## 0. Environment

| | |
|---|---|
| URL | **http://localhost:8069** |
| Database | **`dealflow360`** |
| Login | **`admin` / `admin`** |
| Stack | `docker compose up -d` (Odoo 17 Community + PostgreSQL 15) |
| Module | `dealflow360` — installs clean, 58 modules, 0 errors |

If the stack is cold, `docker compose up -d` then wait for `/web/login` to answer.

---

## 1. Demo data already in the database

| Order | Deal | Total | Risk | Level | Stage |
|---|---|---|---|---|---|
| S00001 | Acme — standard refresh | 11,400.00 | **0** | none | draft |
| S00002 | Acme — Q4 expansion | 38,040.00 | **100** | high | **confirmed** |
| S00003 | Beta Industries — platform rollout | 26,148.60 | **52.8** | high | draft |
| S00016 | **Acme — Q1 fleet refresh (LIVE DEMO DEAL)** | 34,164.00 | **100** | high | **draft** |

Every risk number above is computed by the engine from line discounts against
category/tier ceilings. None are stored constants.

Supporting records: Acme Corp, Beta Industries · ProBook Laptop (1200),
Docking Station (150), Onsite Setup Service (300), Core Plan (999) ·
Main Warehouse, East Depot · Bronze / Silver / Gold discount tiers.

**S00002 is deliberately left confirmed** — it is the proof that the whole
approval cycle completes. **S00016 is the deal to drive live.**

---

## 2. FLOW 1 — the self-governing deal (primary wow moment)

**Verified end-to-end on 2026-09-05.**

1. Log in as `admin`. Click the **9-dot app-grid icon** (top-left) → the
   **DealFlow360** tile. It opens on the **Dashboard** by default.

   Three real stat cards — **Open Quotations / Pending Approvals / At Risk
   Deals** — each a `search_count` on `sale.order`, plus a Recent Quotations
   table from a real `search_read` ordered by `write_date`. No hardcoded
   numbers anywhere in `dashboard.js`.

   Top nav: Dashboard | Quotations | Invoices | Products | Configuration.

   *(Verified in a real Chrome session, zero console errors on every screen.)*

2. **Quotations** → kanban pipeline (Screen 3), grouped by
   `df_pipeline_stage`, with a table-view toggle. Open
   **S00016 — Acme Q1 fleet refresh**.
   Show the lines: ProBook ×35 at **30%**, Docking ×35 at **28%**,
   Setup ×4 at **18%** — all above the Gold/Hardware ceilings.

3. Point at the governance summary and risk gauge:
   **blended risk score 100, level `high`.** Compare with S00001 (10%
   discount → risk **0**, level `none`). Same engine, different inputs.

4. Press **Confirm**. The system refuses:

   > The following quotations exceeded their discount ceiling and have been
   > routed for approval instead of being confirmed: S00016

   The order stays in `draft`, `df_pipeline_stage` becomes
   **`pending_approval`**, and a real `dealflow.approval` chain is created
   with two steps: **sales_manager (pending) → finance (waiting)**.

   *This is the point of the product: the deal governed itself.*

5. **DealFlow360 › Approvals** — the deal is now queued for a manager.

6. Approve as Sales Manager, then as Finance. The chain moves
   `pending → approved`, each step flipping in order, and audit rows are
   written for every transition.

7. Press **Confirm** again — **it now succeeds**: order state `sale`,
   pipeline stage `confirmed`.

8. **Fulfillment happens automatically.** Confirming the approved deal
   creates a real warehouse split — for the demo deal, **2 shipments plus a
   backorder** — allocated from actual `stock.quant`. Open
   **DealFlow360 › Fulfillment** to show it. See §3b for the allocation
   detail.

> **Full rehearsal, run on a throwaway clone of S00016 so the live deal
> stays pristine:** risk 100 → confirm blocked → `pending_approval` with a
> 2-step chain → both steps approved → confirm succeeds (`state=sale`) →
> warehouse split auto-created with 2 shipments and a backorder. Every step
> above is therefore known-good on the exact record type you will demo.

**Role enforcement is real:** attempting to approve as a user who is not a
Sales Manager raises
`UserError: Only a Sales Manager may act on this approval step.`
Worth demonstrating — it proves the chain is not cosmetic.

---

## 3. FLOW 2 — customer negotiation (portal)

**VERIFIED END-TO-END as one continuous walk**, on real HTTP sessions
against a live server. Every state change below was confirmed in postgres,
not read off a screen.

1. Portal login as the customer → **200**.
2. Open own quotation → **200**, correct status.
3. Enter a **counter-discount of 40%** → risk flips to **HIGH**,
   `_df_trigger_reapproval` fires from the negotiation path and creates a
   real two-step chain (**sales_manager pending → finance waiting**).
   Status becomes **Under Negotiation**.
4. Customer tries to confirm while approval is pending → **correctly
   blocked**, order stays Draft.
5. *(Worth showing)* A superuser attempting the manager step is **refused**:
   `UserError: Only a Sales Manager may act on this approval step.`
6. Approve as a real **Sales Manager**, then as a real **Finance** user →
   chain reaches state `approved`.
7. Customer confirms from the portal → **succeeds**. `order.state == 'sale'`,
   `invoice_status == 'to invoice'` — a real state transition, verified in
   the database.

Security invariants re-proven after the record-rule change:
own quotation **200**, another customer's quotation **403**,
`test_portal_isolation` **9/9** green.

> **Bug found and fixed during this walk** (`c7ef60a`): the portal confirm
> route had its own pre-check gating on `df_risk_level != 'none'` and the
> negotiation's `state`. Neither ever resets once a chain is approved — risk
> level is inherent to the discount, and the negotiation state is an
> audit-trail marker, not a live gate. A flagged order could therefore
> **never** be confirmed from the portal even after full manager + finance
> approval, and it would have looked identical to "still pending" on screen.
> This is exactly the failure that would have broken the demo live.

---

## 3b. Multi-warehouse allocation (verified by the integrator)

**Real allocation, computed from real `stock.quant` — not a mock.**

Actual stock in the demo database:

| Warehouse | ProBook Laptop | Docking Station |
|---|---|---|
| Main Warehouse | 6 | 25 |
| East Depot | 4 | 15 |

**S00003** (Beta Industries) orders **15 ProBook** — more than either
warehouse holds, and more than both hold together. The engine produced
split **#2** (`shipment_count = 2`, `has_backorder = true`):

| Line | Warehouse | Qty | Backorder |
|---|---|---|---|
| ProBook Laptop | **Main Warehouse** | **6** | no |
| ProBook Laptop | **East Depot** | **4** | no |
| ProBook Laptop | — | **5** | **yes** |

It drained each warehouse to exactly its real on-hand quantity and turned
the genuine 5-unit shortfall into a real backorder line. Change the stock
and the split changes — there are no hardcoded quantities.

Accepting the split (`action_confirm` on the split) creates one real
`stock.picking` per warehouse with real moves, then reserves via
`action_assign()`.

**Demo it via DealFlow360 › Fulfillment**, opening the split on S00003.

---

## 4. Honest status — what to say if asked

**Working and demonstrable**
- Discount governance: configurable tier/category ceilings, excess points
- Blended risk scoring (DEC-003), configurable threshold (`dealflow.risk_high_min` = 40.0)
- Approval chain: auto-routing on ceiling breach, multi-step, role-enforced, audited
- Confirmation blocked while approval pending; succeeds once approved
- Customer portal: own-quotation access, cross-customer access denied, counter-discount
- Invoices screens (native `account.move`)
- Dashboard over real ORM aggregates

**Landed late in the sprint — verified by the integrator**
- **Warehouse allocation, split fulfillment and backorders (DF-010/011)** —
  implemented and working against real stock. See §3b below.
- **Hybrid recurring billing (DF-012)** — `dealflow.recurring.plan` and
  `dealflow.billing.schedule` models exist on `main` with a billing cron.
  *Models present and installing cleanly, but the billing cycle was NOT
  driven end-to-end by the integrator — do not demo it as proven.*

**Not implemented — say so, do not improvise**
- Deal-health scoring cron (DF-017) and the health dashboard (DF-018)

**Test status — the honest, evidenced version.**

A full `--test-enable` run on a fresh database produced **12 failures, and
every one of them is in Odoo's own core modules**: `spreadsheet_dashboard`
(9), `web` (2), `web_unsplash` (1). **Zero failures in `dealflow360`.**
Odoo's own `TestWebLogin.test_web_login` fails with
`404 on /web/session/check`.

That is conclusive: the **`HttpCase` test harness is broken in this
Docker/Odoo-17 container**, not the application. Behaviour those tests cover
was verified directly against a live running server with real HTTP sessions.

Earlier in the sprint an apparent "9 approval test failures" was traced to a
**same-path file collision** — two agents had independently created
`tests/test_approval.py`. The version on `main` is the correct one:
12 tests, all driving `action_confirm()`, all green.

*Odoo trap worth knowing:* `TransactionCase.assertRaises` wraps the call in a
savepoint that **rolls back the very records the call created**, so a test
asserting on state produced by a raising call will see nothing. Use a plain
`try/except`.

---

## 5. If something breaks mid-demo

- **Screens empty / AccessError on `sale.order`** — a record rule is hiding
  rows from internal users. The global rules in `security/dealflow_security.xml`
  must keep their `if user.share else [(1,'=',1)]` gate. Re-apply with
  `docker compose exec -T odoo odoo -u dealflow360 -d dealflow360 --stop-after-init --no-http`.
- **Stale permissions after a DB-level change** — fully recreate the web
  container (`docker compose stop odoo && docker compose up -d odoo`);
  a plain `restart` does not always clear the registry cache.
- **Module fails to load** — check the newest XML edit first; a malformed
  view aborts the whole module install.
