# DealFlow360 — Handoff Log

Newest entry first. **Every agent appends an entry here at the end of every task.**

Required fields: completed work · important files · current state · dependencies · known issues · remaining work · recommended next task · tests performed.

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
