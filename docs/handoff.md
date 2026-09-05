# DealFlow360 — Handoff Log

Newest entry first. **Every agent appends an entry here at the end of every task.**

Required fields: completed work · important files · current state · dependencies · known issues · remaining work · recommended next task · tests performed.

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
