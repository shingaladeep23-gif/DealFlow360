# DealFlow360 — Handoff Log

Newest entry first. **Every agent appends an entry here at the end of every task.**

Required fields: completed work · important files · current state · dependencies · known issues · remaining work · recommended next task · tests performed.

---

## DF-002 — Quotation Core: sale.order/sale.order.line governance fields — Atlas — 2026-09-05

**Completed work**
- `sale.order.line` extended (`models/sale_order_line.py`) with:
  - `df_effective_ceiling` (float, computed, stored) = `min(customer tier ceiling, product category ceiling)`.
  - `df_excess_points` (float, computed, stored) = points by which the rep's discount exceeds the ceiling, **measured against the pricelist price per DEC-009**, not the catalogue list price (see "Known issues" for exactly how).
  - `df_margin_pct` (float, computed, stored) = real live margin `(price_subtotal - qty*standard_price) / price_subtotal`.
- `sale.order` extended (`models/sale_order.py`) with:
  - `df_margin_pct` (float, computed, stored) = order-level aggregate margin across non-display-type lines.
  - `df_pipeline_stage` (Selection, computed, stored) = `draft`/`pending_approval`/`approved`/`negotiation`/`confirmed`, currently only distinguishing `confirmed` (state=`sale`) from `draft` (everything else) — a deliberate seam for DF-004 (approval → pending_approval/approved) and DF-014/015 (negotiation) to extend, per the task's explicit instruction not to invent those buckets early.
- **DEC-009 compliance (the subtle constraint):** `df_excess_points` is NOT computed as `discount - ceiling` against the catalogue price. Instead, `SaleOrderLine._df_reference_price()` independently resolves "what this tier should pay" via `product.with_context(pricelist=order.pricelist_id.id, ...).price` (falling back to `product.list_price` when no pricelist applies), then derives the rep's true additional discount as `(reference_price - actual_paid_unit_price) / reference_price * 100`, where `actual_paid_unit_price = price_unit * (1 - discount/100)`. This is policy-independent: it gives the correct answer regardless of whether a future pricelist is configured with `discount_policy='with_discount'` or `'without_discount'`, because it measures against the *reconstructed reference price*, never against whatever Odoo happened to split `price_unit`/`discount` into internally. No pricelist seed data was added (not required this task); the no-pricelist path degrades to exactly the catalogue-price behaviour and was verified against the worked examples.
- **DEC-010 compliance:** no routing threshold (e.g. `40`) appears anywhere in this task's code — DF-002 only produces the ceiling/excess/margin *inputs*; DF-003 will read `ir.config_parameter` key `dealflow.risk_high_min` for routing, not a constant.
- `views/sale_order_views.xml` (new): minimal field placement only, per task boundaries — adds the three line fields as extra (hidden-by-default, `optional="show"`) columns on the order line tree, and a "DealFlow360" notebook page on the order form showing `df_margin_pct` / `df_pipeline_stage`. Not the real quotation builder (Don owns that per `docs/ui_spec.md`).
- `tests/test_sale_order_governance.py` (new, 8 tests): both problem-statement worked examples, recompute-on-discount-change, recompute-on-quantity/price-change, tier-stricter-than-category (Beta/Silver + ProBook/Hardware), category-stricter-than-tier (Acme/Gold + Setup Service/Services), margin-is-real-not-placeholder, and draft/confirmed pipeline stage transition.

**Important files**
- `addons/dealflow360/models/sale_order_line.py`, `sale_order.py` (new)
- `addons/dealflow360/models/__init__.py` (updated import order)
- `addons/dealflow360/views/sale_order_views.xml` (new), `__manifest__.py` (registered)
- `addons/dealflow360/tests/test_sale_order_governance.py` (new), `tests/__init__.py` (updated)

**Current state**
- Verified live against Odoo 17.0 + PostgreSQL 15, three ways: (1) `-u dealflow360 --stop-after-init` upgrade on the existing DF-001 database — 0 errors, xpath targets (`sale.view_order_form`'s embedded order_line tree and notebook) resolved correctly on the first try; (2) a truly fresh `-i dealflow360 --stop-after-init` install from scratch (dropped the DB first) — 0 errors, confirming the post_init_hook + new fields coexist cleanly on a clean install, not just an upgrade path; (3) `-u dealflow360 --test-enable --stop-after-init` on top of that fresh install — **0 failed, 0 error(s) of 12 tests** (4 from DF-001 + 8 new).
- **Both problem-statement worked examples hold exactly, confirmed by passing tests, not just eyeballed:**
  - Acme Corp (Gold, 15%) + ProBook Laptop (Hardware, ceiling 15) at 12% → `df_effective_ceiling=15.0`, `df_excess_points=0.0` (within limit).
  - Acme Corp (Gold, 15%) + Onsite Setup Service (Services, ceiling 10) at 18% → `df_effective_ceiling=10.0`, `df_excess_points=8.0` (the spec's canonical "Gold customer, but Services are stricter" case).
- `docker compose ps` shows both containers healthy; this was all done in the same live session as DF-001c, no new blockers.

**Dependencies**
- DF-003 (blended risk engine) consumes `df_excess_points` and `df_effective_ceiling` per line directly — no further plumbing needed from DF-002's side.
- DF-005b/c (Don's quotation builder + pipeline Kanban) can now read real `df_effective_ceiling`/`df_excess_points`/`df_margin_pct`/`df_pipeline_stage` instead of placeholders.

**Known issues**
- `df_pipeline_stage` only distinguishes draft/confirmed today, as explicitly scoped — DF-004 and DF-014/015 must extend `_compute_df_pipeline_stage`'s `@api.depends` and logic when their fields exist; it is not a bug, it is the intended seam.
- The pricelist-aware reference price in `_df_reference_price()` is exercised in this task only via the no-pricelist degrade path (no tier pricelists exist yet — DEC-009 doesn't require seeding them for DF-002). Whoever seeds real tier pricelists (unassigned so far) should re-run `test_worked_example_probook_within_ceiling`/`test_worked_example_setup_service_over_ceiling` afterward to confirm the pricelist branch still gives the same answers, since that branch's exact behaviour under a configured pricelist wasn't separately exercised.
- `product.with_context(pricelist=...).price` is the standard, long-stable Odoo pattern for "resolve this product's price under this pricelist" (used by website_sale and others) — correct on 17.0, but flagging since it's the one part of this task not exercised under a real non-trivial pricelist rule (see above).

**Remaining work**
- DF-003 (blended risk scoring engine per DEC-003 + DEC-010's configurable threshold) is next.
- Tier pricelists (DEC-009) remain unseeded; not blocking, but should land before a demo that showcases pricelist + ceiling interacting.

**Recommended next task**
- DF-003, assigned to Atlas (per god's message, released together with DF-005b to Don once this report lands).

**Tests performed**
- `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --stop-after-init` — clean upgrade, 0 errors.
- `docker compose exec db psql ... DROP DATABASE dealflow360` + `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --stop-after-init` — clean fresh install, 0 errors.
- `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --test-enable --stop-after-init` on the fresh install — `0 failed, 0 error(s) of 12 tests`.
- `python -m py_compile` / `xml.dom.minidom.parse` on every changed `.py`/`.xml` file before the live run — all clean.

---

## DF-001c — Live install verification, one real bug found and fixed — Atlas — 2026-09-05

Docker Desktop's Linux engine came back after the human rebooted (root cause: `VirtualMachinePlatform` was stuck `EnablePending`, fixed by restart — not an Odoo/addon issue). This entry closes out DF-001's open verification with real results instead of speculation, and replaces the "Known issues" list in the DF-001 entry below (kept for history, but treat this entry as current truth).

**Completed work**
- `git pull origin main`, `docker compose up -d` — both containers came up healthy (`dealflow360-db-1`, `dealflow360-odoo-1`), port 8069 reachable.
- First install attempt failed on a **stale `dealflow360` database left over from before the Docker outage** (`duplicate key value violates unique constraint "pg_type_typname_nsp_index"` in Odoo's own base SQL bootstrap) — unrelated to our module; fixed by terminating the stale connection and `DROP DATABASE dealflow360`, not a code change.
- Second install attempt found one real bug: **`product.template.is_storable` does not exist on Odoo 17.0** — confirmed by the traceback itself (`ValueError: Invalid field 'is_storable' on model 'product.template'`) when `demo/demo_data.py` tried to create ProBook Laptop / Docking Station. God's suspicion was correct: **Odoo 17.0 Community uses `type='product'`** for storable goods; `is_storable` (as a field alongside `type='consu'`) is an Odoo 18 concept. Fixed both product creations in `demo/demo_data.py` to use `type='product'` and dropped the `is_storable` key entirely.
- Reinstalled into a clean database — **module loads with zero errors**: `Module dealflow360 loaded in 3.03s`, full stack `60 modules loaded in 69.52s ... Registry loaded in 88.820s`, no `ERROR`/`CRITICAL` lines anywhere in the log (the only log noise — a docutils `Unexpected indentation` / `Block quote` notice — happens during core `mail` module loading, before `dealflow360` even starts, and is pre-existing Odoo-core RST-description noise unrelated to our module).
- Ran `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --test-enable --stop-after-init`: **`0 failed, 0 error(s) of 4 tests`** — all four tests in `tests/test_discount_tier.py` pass.
- Also ran `-u dealflow360` (the upgrade path from CLAUDE.md's dev loop, not just fresh `-i` install) on the already-installed database — clean, no errors, `Registry loaded in 8.256s`. Both install and upgrade paths are confirmed clean.
- Verified the four seeded facts directly with `psql`, not just "install succeeded":
  - Tiers: `Bronze=5, Silver=10, Gold=15` ✅
  - Category limits: `Hardware=15, Services=10` ✅
  - `Acme Corp` → `Gold` ✅
  - ProBook Laptop `stock.quant`: `Main Warehouse=6, East Depot=4` — **confirmed no single warehouse can cover a 10-unit order** ✅ (this is the DF-010 fulfillment demo precondition)

**Verification of every item from the previous "Known issues" list** (item-by-item, against the real Odoo 17.0 install, not source-grepping — the live installer settled these faster than reading source would have):
1. `product.template.is_storable` — **WRONG, FIXED.** Odoo 17.0 has no such field; storable goods use `type='product'` (the three `type` values on 17.0 are `'product'`, `'consu'`, `'service'` — `'consu'` on 17.0 means non-stock-tracked "Consumable", not "Goods" as it does on 18). Fixed in `demo/demo_data.py`.
2. `post_init_hook(env)` single-arg signature — **CONFIRMED CORRECT.** The hook ran and executed (`getattr(py_module, post_init)(env)` in the traceback shows Odoo itself calling it with one arg); had the signature been wrong we'd have seen a `TypeError` before ever reaching our code, and we didn't.
3. View inheritance xmlids (`product.product_template_form_view`, `product.product_category_form_view`, `base.view_partner_form` + its `category_id` anchor) — **CONFIRMED CORRECT.** All of `dealflow360/views/*.xml` loaded without error; an inherited view with a bad `inherit_id` or a missing xpath target raises a hard `ValueError` at load time, and none did.
4. Group `implied_ids` (`sales_team.group_sale_salesman`, `sales_team.group_sale_manager`, `account.group_account_invoice`) — **CONFIRMED CORRECT.** `security/dealflow_security.xml` loaded without error; a bad `ref()` raises immediately.
5. `depends` list (`base, mail, product, sale_management, sale_stock, stock, account, portal`) — **CONFIRMED CORRECT.** The full dependency graph resolved and all 60 modules (our addon plus its transitive dependencies) loaded in the correct order.
6. `ir.model.access.csv` column header format — **CONFIRMED CORRECT.** Loaded without error; a malformed CSV header raises at load time.
7. `warehouse.lot_stock_id` + direct `stock.quant.create({'quantity': ...})` pattern — **CONFIRMED CORRECT.** The `psql` verification above shows exactly the intended 6/4 split against each warehouse's real stock location, and this is the same mechanism the DF-010 allocation engine will read from.

So: **one real bug (`is_storable`), everything else in the original guess-list held.** Odoo's own installer was in fact faster than source-grepping would have been — it named the exact wrong field on the first failing run.

**Important files**
- `addons/dealflow360/demo/demo_data.py` — the only file changed (two `type='consu'`+`is_storable=True` pairs → `type='product'`).
- `docs/task_plan.md` — DF-001 row flipped to ✅.

**Current state**
- DF-001 is now genuinely done: code, install, upgrade, tests and the four seed facts are all verified against a live Odoo 17.0 + PostgreSQL 15 instance. `docker compose ps` shows both containers `Up`/healthy.
- Nothing under `D:\odoo-source` was created or used this round (Docker came back before source-grepping was needed) and nothing from outside the repo was committed.

**Dependencies**
- None outstanding for DF-001 itself. DF-002 is unblocked in every sense (code and verified runtime) and can start immediately.

**Known issues**
- None outstanding for the DF-001 scope. Whoever builds DF-012 (recurring billing) should remember `product.template.df_recurring_plan_id` was intentionally left out (see the DF-001 entry below) and needs adding once `dealflow.recurring.plan` exists.
- Cosmetic-only: a docutils RST parser notice (`Unexpected indentation` / `Block quote ends without a blank line`) appears during core `mail` module loading on every install of this Odoo image, regardless of our addon — pre-existing Odoo-core behavior, not actionable.

**Remaining work**
- DF-002 (extend `sale.order`/`sale.order.line` with tier + category ceilings, per-line excess, live margin) is next per `docs/task_plan.md`.

**Recommended next task**
- DF-002, assigned to Atlas. Foundation-wise nothing about DF-001 changes how it should be built — the `type='product'` correction only affects demo data, not the model/field design DF-002 will extend.

**Tests performed**
- `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --stop-after-init` — clean install, 0 errors, twice (once failing on `is_storable`, once clean after the fix).
- `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --test-enable --stop-after-init` — `0 failed, 0 error(s) of 4 tests`.
- `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --stop-after-init` — clean upgrade path, 0 errors.
- Direct `psql` queries against `dealflow_discount_tier`, `dealflow_category_limit`, `res_partner`/`df_tier_id`, and `stock_quant`/`stock_location`/`stock_warehouse` confirming the four seeded facts exactly as specified.

---

## DF-005a — UI specification: 18 mockup screens → Odoo views — Don — 2026-09-05

**Completed work**
- `docs/ui_spec.md`: a screen-by-screen specification for all 18 `Mockup.jpeg` screens. Cropped and upscaled each screen from the mockup individually (via PIL) to read fine text that wasn't legible at full-image resolution. For each screen: model, view type + rationale, every field with EXISTS / COMING `<task-id>` / MISSING status, actions/buttons and what they trigger, owning menu, and owner (Don vs. Pam for the portal screen).
- Two summary sections: (1) a precise, ranked list of backend fields/methods needed from Atlas that don't exist in `docs/architecture.md` yet, (2) a proposed implementation order for Don's own tasks (DF-005, DF-006, DF-009, DF-011, DF-013, DF-018) respecting the vertical-slice priority (quotation builder → risk display → approval UI) before dashboards/reporting polish.
- Flagged 5 mockup-vs-architecture conflicts for Michael, most notably: Screen 3's Kanban pipeline has no backing field (needs new `sale.order.df_pipeline_stage`); Screen 9 (Subscriptions) has no backing "subscription" aggregate model; Screen 14 (Deal Health) needs DEC-005's four signals exposed individually, not just the blended score; Screen 17's per-tier "Price Rules" table implies a second pricing mechanism distinct from the existing discount-ceiling system; Screen 18's routing-table panel implies DEC-003's thresholds are editable data when they're currently code constants.
- This was a **design-only task** per explicit instruction from god — Odoo/Docker is still down on this machine (see DF-001 entry below), so no XML/OWL/JS was written; writing unverifiable view code would risk stacking up install failures.

**Important files**
- `docs/ui_spec.md` (new) — the full specification, the durable output of this task.
- `docs/task_plan.md` — annotated DF-005/006/009/011/013/018 rows with "design spec ready" notes and their specific blockers/field asks, without changing their ⬜ status (no code was written).

**Current state**
- Committed and pushed to `main`: `2de1e10` (ui_spec.md), plus this handoff/task_plan update.
- No `addons/` files were touched, per task boundaries.

**Dependencies**
- DF-005/006/009/011/013/018 implementation depends on: this spec (done) + the corresponding Atlas backend tasks (DF-002/003/004/008/010/012/017) + a working Docker/Odoo instance (currently blocked, see DF-001 entry) + resolution of the open architecture questions listed in `docs/ui_spec.md` Summary 1 and "Mockup vs. architecture conflicts".

**Known issues**
- Two mockup table cells (Screen 7's 4th "why flagged" column header, Screen 9's create-button label) were only partially legible even after upscaling — documented as best-guess with an explicit note to confirm wording with Michael/Atlas rather than asserting them as fact.
- Screen 11 (Customer Portal Negotiation) was deliberately not specified beyond a one-paragraph note — it's Pam's screen (DF-014).

**Remaining work**
- Route `docs/ui_spec.md` Summary 1's field list to Atlas so DF-002/003/004/008/010/012/017 can include the needed fields as they're built, rather than Don discovering gaps mid-implementation.
- Get Michael's decisions on the 3 open architecture questions (subscription aggregate, tiered pricing mechanism, DEC-003 threshold configurability) before DF-013/017 land, since they change what Don builds for Screens 9, 17, 18.
- Once Docker/Odoo is live and DF-002/003/004 exist, implement DF-005b (Quotation Detail) first per the proposed order in `docs/ui_spec.md` Summary 2.

**Recommended next task**
- Atlas: DF-002 (sale.order/line governance fields) is still the critical path — nothing in DF-005 can be implemented (only specified) until it lands. Michael: resolve the 3 flagged architecture questions whenever convenient, ideally before DF-012/017.

**Tests performed**
- None applicable (documentation-only task, no code). Verified `docs/ui_spec.md` covers all 18 screens against the mockup crops and cross-referenced every field name against `docs/architecture.md` §3 for accuracy before marking EXISTS/COMING.

---

## DF-001 — Phase 1: Odoo Foundation — Atlas — 2026-09-05

**Completed work**
- `docker-compose.yml` (odoo:17 + postgres:15, named volumes `odoo-data`/`postgres-data`, `./addons` mounted at `/mnt/extra-addons`, port 8069) and `odoo.conf` (addons_path includes `/mnt/extra-addons`, `db_name=dealflow360`, `without_demo=all`).
- `addons/dealflow360/` addon skeleton per `docs/architecture.md` §2: manifest (depends: base, mail, product, sale_management, sale_stock, stock, account, portal), models/, views/, security/, data/, demo/, tests/.
- Security: module category + 4 groups (`group_dealflow_sales_rep`, `group_dealflow_sales_manager`, `group_dealflow_finance`, `group_dealflow_admin`) with sensible `implied_ids` onto native sales/accounting groups, plus `ir.model.access.csv` for the two new models.
- Models (this task's scope only): `dealflow.discount.tier`, `dealflow.category.limit`, `res.partner.df_tier_id`, `product.category.df_max_discount`, `product.template.{df_is_recurring, df_is_promoted, df_min_margin}`.
- Menu skeleton matching the mockup nav (Dashboard, Quotations, Approvals, Fulfillment, Subscriptions, Invoices, Deal Health, Reports, Products) under a `DealFlow360` root app menu, plus an admin-only Configuration submenu (Discount Tiers, Category Limits) so DF-001 records are verifiable. Quotations and Products menus point at real `sale.order` / `product.template` act_windows; the six not-yet-built areas are placeholder menu items only (no action) — Don owns their real screens.
- Minimal tree/form views for `dealflow.discount.tier` and `dealflow.category.limit`; inherited form views adding `df_tier_id` to `res.partner`, and a new "DealFlow360" notebook page on `product.template` plus a field on `product.category`.
- Seed data via `demo/demo_data.py` registered as `post_init_hook` (see "Known issues" for why this is Python, not XML): Bronze/Silver/Gold tiers (5/10/15%) and Hardware/Services category limits (15/10%) load as normal `data/` XML (survive `without_demo=all`); Acme Corp (Gold) and Beta Industries (Silver) partners; ProBook Laptop + Docking Station (Hardware, storable), Onsite Setup Service (Services), Core Plan (Services, `df_is_recurring=True`); Main Warehouse (MAIN) and East Depot (EAST); `stock.quant` seeded 6 ProBook units at Main + 4 at East (10 total, no single warehouse can cover a 10-unit order) and Docking Station stock at both.
- `tests/test_discount_tier.py`: asserts the three seeded tiers and their ceilings, the two category limits, Acme Corp → Gold, and that ProBook stock is genuinely split (each warehouse < 10 units, combined ≥ 10).
- Verified locally (Docker unavailable, see below): every `.py` file compiles (`py_compile`), every `.xml` file is well-formed.

**Important files**
- `docker-compose.yml`, `odoo.conf`
- `addons/dealflow360/__manifest__.py`, `__init__.py`
- `addons/dealflow360/models/discount_tier.py`, `res_partner.py`, `product.py`
- `addons/dealflow360/security/dealflow_security.xml`, `ir.model.access.csv`
- `addons/dealflow360/data/discount_tier_data.xml`, `category_limit_data.xml`
- `addons/dealflow360/views/discount_tier_views.xml`, `res_partner_views.xml`, `product_views.xml`, `dealflow_menus.xml`
- `addons/dealflow360/demo/demo_data.py` (post_init_hook seed data)
- `addons/dealflow360/tests/test_discount_tier.py`

**Current state**
- All DF-001 code is committed and pushed to `main` (commits `5022c3b`, `cb4bf89`, `8a71d58`).
- **The module has NOT been installed/upgraded against a live Odoo instance.** Docker Desktop's Linux engine will not come up on this machine: `docker info`/`docker ps` return `500 Internal Server Error ... dockerDesktopLinuxEngine`, and `wsl -l -v` shows no `docker-desktop` / `docker-desktop-data` distro registered at all (only pre-existing `Ubuntu` and `nh-dev`, both Stopped). This was flagged as a known risk at task dispatch; per instructions I did not stall on it, did not switch away from Docker (DEC-001 stands), and completed all filesystem work instead.
- Escalating this to Michael/human now via hive message — needs a human to repair Docker Desktop's WSL2 backend (e.g. `wsl --shutdown` + relaunch Docker Desktop, or reinstalling the WSL2 backend) since this agent cannot repair OS-level virtualization state.

**Dependencies**
- DF-002 onward (sale.order/sale.order.line extensions) depends on the models in this task and is otherwise unblocked code-wise, but **should not be declared "done" for DF-001 until someone runs the install** once Docker is available: `docker compose up -d` then `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --stop-after-init`, and `-i dealflow360 --test-enable` to run `tests/test_discount_tier.py`.

**Known issues**
- **Install unverified (blocker above).** The following are correct to the best of my Odoo 17.0 knowledge but were written without a live instance to confirm against, so re-check the server log on first install:
  - `product.template.is_storable` (Boolean) is the Odoo 17 replacement for the old `type='product'` storable flag; used with `type='consu'` for ProBook Laptop / Docking Station.
  - `post_init_hook` uses the Odoo 17 single-argument `(env)` signature (not the older `(cr, registry)`).
  - View inheritance targets `product.product_template_form_view` (adds a new notebook page, not assumed page names) and `product.product_category_form_view`, and `base.view_partner_form`'s `category_id` field as the anchor — all standard, long-stable xmlids, but unverified live.
  - Group `implied_ids` reference `sales_team.group_sale_salesman`, `sales_team.group_sale_manager`, `account.group_account_invoice` — standard Odoo 17 groups, unverified live.
- Seed data (customers/products/warehouses/stock) is implemented as a `post_init_hook` Python function in `demo/demo_data.py` rather than declarative XML in `demo/*.xml` as architecture.md's folder listing might imply literally. Reason: creating `stock.quant` records against warehouse-specific stock locations needs each warehouse's auto-generated `lot_stock_id`, which has no stable external ID to `ref()` from plain XML; Python lets us read `warehouse.lot_stock_id` directly after `create()`. The folder (`demo/`) and content (customers, products, warehouses, stock) match architecture.md exactly — only the file format differs. Flagging per CLAUDE.md's "propose deviations, don't silently change them" rule; not an architecture change, an implementation detail. `data/discount_tier_data.xml` and `data/category_limit_data.xml` stayed as plain XML in `data/` (no cross-location referencing needed there) and are loaded via the manifest's `data` key rather than `demo`, so they (and the seed hook) survive `odoo.conf`'s `without_demo=all` — deliberate, so the demo dataset is deterministic regardless of the `--without-demo` flag.
- `product.template.df_recurring_plan_id` from architecture.md §3.1's field list was **intentionally omitted** — it would point at `dealflow.recurring.plan`, which doesn't exist until DF-012, and a `Many2one` to a non-existent model would break install. DF-012 should add that field when the model exists.

**Remaining work**
- Run the install/upgrade + test suite once Docker works; fix anything the live log surfaces (see Known issues list above).
- Everything in DF-002 through DF-020 per `docs/task_plan.md` (sale.order/line governance fields, risk engine, approvals, upsell, fulfillment, billing, portal, deal health, UI).

**Recommended next task**
- Human/Michael: repair Docker Desktop's Linux engine, then have Atlas (or whoever picks up next) run the install/test verification for DF-001 before starting DF-002, since DF-002 builds directly on these models.

**Tests performed**
- `python -m py_compile` on every `.py` file under `addons/dealflow360/` — all pass.
- `xml.dom.minidom.parse` on every `.xml` file under `addons/dealflow360/` — all well-formed.
- Could **not** run: module install/upgrade, `tests/test_discount_tier.py` under the Odoo test runner, or any UI/browser verification — all require the Docker stack, which is down (see Known issues).

---

## DF-000 — Phase 0: Inspection & Architecture — Michael — 2026-09-05

**Completed work**
- Inspected repository, tooling and git configuration.
- Extracted and read the full problem statement (`DealFlow360.pdf`, 13 pages) and the mockup (`Mockup.jpeg`, 18 screens).
- Initialized the git repository on `main` with the user's identity and the correct remote.
- Authored the architecture, the decision record (including the blended risk formula), and the documentation scaffold.

**Important files**
- `CLAUDE.md` — engineering contract; **every agent reads this first**
- `docs/architecture.md` — module layout, data model, state machines, boundaries
- `docs/decisions.md` — DEC-001..007, notably **DEC-003 (risk formula)** and **DEC-005 (health scoring)**
- `docs/acceptance_tests.md` — the problem statement turned into explicit tests
- `docs/task_plan.md` — phases and assignments

**Current state**
- Repository initialized on `main`; remote `shingaladeep23-gif/DealFlow360` exists and was **empty**.
- Git identity verified: `shingaladeep23-gif <shingaladeep23@gmail.com>`.
- **No application code exists yet.** Odoo is not yet installed or running.
- Tooling present: git, Python 3.10, Docker (Desktop starting). No `gh` CLI, no local `psql`.

**Dependencies**
- Docker Desktop must be running before the stack can start.

**Known issues**
- `gh` CLI is unavailable — use `git` directly for all repository operations.
- PDF text extraction requires `pypdf` (present); `poppler` is absent so PDF page *rendering* is unavailable.

**Remaining work**
- All of Phases 1–9.

**Recommended next task**
- **DF-001 (Atlas)** — Docker stack + `dealflow360` addon skeleton + security + seed data.

**Tests performed**
- Verified `git branch --show-current` → `main`
- Verified `git config user.name` / `user.email` → user's identity
- Verified `git remote -v` → correct repository
- Verified remote had no refs (empty repo), so the first push to `main` is clean
