# DealFlow360 — Handoff Log

Newest entry first. **Every agent appends an entry here at the end of every task.**

Required fields: completed work · important files · current state · dependencies · known issues · remaining work · recommended next task · tests performed.

---

## DF-005b/c — Quotation Detail governance summary + risk gauge, Quotations Kanban pipeline — Kevin — 2026-09-05

**Completed work**
- Screen 4 (Quotation Detail): `views/sale_order_views.xml` now adds Limit (`df_effective_ceiling`), Excess (`df_excess_points`) and Margin (`df_margin_pct`) columns to the order line tree, with row/cell decoration turning red when `df_excess_points > 0`. An order-level summary box shows live margin and a reusable OWL `dealflow_risk_gauge` field widget bound to `df_blended_risk_score` (reads sibling `df_risk_level`/`df_risk_summary` off the same record). `df_risk_summary` is rendered as-is in a yellow flag banner, per the DF-005 brief (not re-derived). A labeled placeholder panel states the upsell/cross-sell teaser is not shown because DF-008 doesn't exist yet — no fabricated recommendation data.
- Screen 3 (Quotations List/Pipeline): new `views/sale_order_kanban_views.xml` adds a kanban view grouped by `df_pipeline_stage` (cards show customer, margin, risk-level badge, amount) and extends `action_dealflow_quotations`'s `view_mode`/`views` to `kanban,tree,form` — done from a **separate file**, not by editing `views/dealflow_menus.xml` (Atlas's DF-003c carve-out), so the action record is updated without touching the locked file.
- New reusable OWL widget: `static/src/fields/risk_gauge/{risk_gauge.js,risk_gauge.xml}` + `static/src/scss/dealflow.scss`, registered under `web.assets_backend` in `__manifest__.py`. Intended for reuse on Screen 7 (DF-006) per the UI spec.
- Deliberately NOT built: "Submit for Approval" button (DF-004's `action_submit_for_approval()` doesn't exist) and the real upsell panel (DF-008 doesn't exist) — see CLAUDE.md's "no faking business logic" rule.

**Important files**
- `addons/dealflow360/views/sale_order_views.xml`
- `addons/dealflow360/views/sale_order_kanban_views.xml` (new)
- `addons/dealflow360/static/src/fields/risk_gauge/risk_gauge.js`, `risk_gauge.xml` (new)
- `addons/dealflow360/static/src/scss/dealflow.scss` (new)
- `addons/dealflow360/__manifest__.py` (appended `data`/new `assets` key)

**Current state**
- Pushed to `main` (`8b4ff6c`). XML-validated (`xmllint --noout`) and manifest-literal-checked; not yet a full Odoo test-runner concern since this task adds no Python/tests.
- **Browser/console verification is incomplete** — see Known issues. `docker compose exec odoo odoo -d df_kevin -i dealflow360 --stop-after-init` installs cleanly (60 modules, 0 errors, includes both new view files loading without error) — that much is live-verified. Full interactive click-through (open a real quotation, see the gauge/banner/kanban render, check browser console) is not done yet.

**Dependencies**
- DF-006 (Approvals) can reuse `dealflow_risk_gauge` once DF-004 lands.
- DF-005d (Sales Dashboard) is still open — not started this task.

**Known issues**
- **Found a real blocker while trying to browser-test df_kevin, reported to Michael separately (see hive outbox `stack-dbfilter-and-registry-issue`):** the shared stack's `odoo.conf` has `db_name = dealflow360` and no `dbfilter`, which makes Odoo's HTTP layer (`/web/database/list`, `/web/session/authenticate`, and silently `/web/login?db=<anything>`) resolve to `dealflow360` only — `df_kevin`/`df_pam` are real Postgres databases (confirmed via `psql -l`) and reachable via the Odoo CLI (`-d df_kevin -i dealflow360`), but not through a browser session. This means the OWL widget, kanban rendering and browser-console check for this task are still outstanding, through no code issue found so far — need `dbfilter` added to `odoo.conf` (Atlas's stack) before I can complete manual verification. Everything up to "module installs cleanly" is confirmed; visual/interactive confirmation is not.
- Also observed (while briefly and unintentionally on `dealflow360` itself, due to the above dbfilter behavior): `sale.order` raised `KeyError` from the live registry for several requests around 07:39-07:41. No writes were made. Likely transient, coinciding with Atlas's concurrent DF-003b/DEC-015 work at that time; not chased further since it's not my lane and Atlas's own DF-003b entry above claims a clean, tested state as of this same day.

**Remaining work**
- Finish manual browser verification of Screen 3/4 (kanban render, risk gauge visual, flag banner, console-clean) once `df_kevin` is reachable via the web client.
- DF-005d (Sales Dashboard, Screen 2) — not started.
- DF-006 once DF-004 lands.

**Recommended next task**
- DF-005d (Sales Dashboard) can start now with partial counts (Open Quotations works today); Pending Approvals/At Risk Deals backfill when DF-004/DF-017 land.

**Tests performed**
- `xmllint --noout` on both changed/added XML view files — pass.
- `python3 -m py_compile` on `__manifest__.py` — pass; manifest literal round-tripped via `ast.literal_eval` to confirm `data`/`assets` are well-formed.
- `docker compose exec odoo odoo -d df_kevin -i dealflow360 --stop-after-init` — 60 modules loaded, 0 errors, both new view files load cleanly.
- Not yet performed: interactive browser click-through and browser-console check (blocked on the dbfilter issue above).

---

## DF-014/DF-016 (live-verified) — Pam — 2026-09-05

**Completed work**
- Live-tested the first-pass portal work (below) against my own database `df_pam`, via `docker exec` into Atlas's already-running containers (never touched his compose lifecycle). First run: **1 failed, 1 error of 30 tests** — both about a portal user reading their *own* order, not cross-customer leakage (every isolation-specific test passed clean: search excludes other customer, search_read excludes, browse+read raises AccessError, write attempt raises AccessError, two portal users' results disjoint, cross-customer negotiation read excluded — 5/5 for the actual security requirement).
- Root-caused and fixed the failure: `sale`'s own native portal rule on `sale.order`/`sale.order.line` (`sale_order_rule_portal` / `sale_order_line_rule_portal` in `odoo/addons/sale/security/ir_rules.xml`) is **follower-based** (`message_partner_ids`), scoped to `base.group_portal`. Group rules OR together, but that OR-set still ANDs against DEC-012's global partner_id rule — so any quotation nobody had explicitly "sent" (no chatter follower yet) was unreadable **even to its own owner**. Fixed via DEC-018: a same-domain rule added to the *same* portal group so the OR-set becomes `(follower OR partner_id)`, which reduces to exactly the global rule's boundary (`A AND (B OR A) == A`) — cannot widen access, never touches/replaces the native rule.
- Also found and fixed (DEC-019): `sale.order.df_pipeline_stage` has no `sent` value and today only computes `draft`/`confirmed` (see its own docstring in `models/sale_order.py`) — so the portal's status badge was silently wrong for a "sent" or negotiated quotation, even though AT-08 explicitly wants Sent/Under Negotiation/Confirmed. Computed a portal-specific label instead (`controllers/portal.py::_dealflow_portal_status`) from `order.state` + whether a `dealflow.negotiation` exists — no change to `sale_order.py` needed.
- Re-ran the full suite once Atlas's tree (which the shared container's `/mnt/extra-addons` bind-mounts) picked up the DEC-018 fix: **0 failed, 0 error(s) of 30 tests** (11 of mine — 5 portal-status + 7 isolation... see exact count in `tests/`, plus 4 negotiation — + Atlas's 19).
- Manually grepped `views/portal_templates.xml` and `controllers/portal.py` for every internal field named in the DF-014 task brief (`df_effective_ceiling`, `df_excess_points`, `df_margin_pct`, `df_blended_risk_score`, `df_risk_level`, `df_risk_summary`): zero occurrences in the template; the two controller references to `df_risk_level` are server-side only (deciding whether to block portal confirm), never rendered to the customer.

**Important files**
- `addons/dealflow360/security/dealflow_security.xml` (DEC-018 rules)
- `addons/dealflow360/controllers/portal.py` (`_dealflow_portal_status`)
- `addons/dealflow360/views/portal_templates.xml`
- `addons/dealflow360/tests/test_portal_status.py` (new)
- `docs/decisions.md` (DEC-018, DEC-019)

**Current state**
- All pushed to `main` (`51c8e49`, `8f79ca9`). Live-verified against the shared stack under my own database `df_pam` — first genuine (not py_compile-only) verification of this task's code.

**Dependencies**
- DF-015 still blocked on Atlas's DF-004 (`dealflow.approval`) — unchanged from the previous entry.

**Known issues**
- Same as the previous entry: portal-mediated `action_confirm()` runs under `sudo()`, so there's no distinct "confirmed by customer" identity in the audit trail yet.
- Not yet done: a real browser click-through (only ORM/controller-method level tests exist so far) and a check of browser console / server log during that click-through, per the standing acceptance criteria.

**Remaining work**
- Browser-based click-through of `/my/quotations` and `/my/quotation/<id>` as two different seeded portal users, watching server log + browser console.
- DF-015's real reapproval-chain hook once DF-004 lands.

**Recommended next task**
- Once Atlas's DF-004 lands: wire `requires_reapproval` into a real `dealflow.approval` record (DF-015), then DF-007's full vertical-slice QA.

**Tests performed**
- `docker exec dealflow360-odoo-1 odoo -d df_pam -i dealflow360 --stop-after-init` — clean install, 60 modules, 0 errors (includes `views/portal_templates.xml` loading without error).
- `docker exec dealflow360-odoo-1 odoo -d df_pam -u dealflow360 --test-enable --stop-after-init`, run twice: first **1 failed, 1 error of 30** (DEC-018 bug found), second (after the fix propagated into Atlas's tree) **0 failed, 0 error(s) of 30 tests**.

---

## DF-003b — Stack up, DEC-015 fixed at the root, real risk tests, first live verification — Atlas — 2026-09-05

**Completed work**
- **Docker stack, cold first start.** The Docker daemon came up mid-project; no DealFlow containers had ever existed. `docker compose up -d` pulled `odoo:17` + `postgres:15` fresh and started `dealflow360-db-1` / `dealflow360-odoo-1`. No compose/config file changes were needed — `docker-compose.yml` and `odoo.conf` were already correct, just never run.
- **DEC-015 fixed at the root** (`addons/dealflow360/models/sale_order_line.py:41-48`, `_df_reference_price`). Replaced `product.with_context(pricelist=...).price` (no such attribute on Odoo 17 — confirmed) with `pricelist._get_product_price(self.product_id, self.product_uom_qty or 1.0, uom=self.product_uom or self.product_id.uom_id, date=self.order_id.date_order)`. Per the task's own instruction not to code from memory, I grepped the **installed** container source before writing this: `/usr/lib/python3/dist-packages/odoo/addons/product/models/product_pricelist.py` inside `dealflow360-odoo-1`. Confirmed signature: `_get_product_price(self, product, *args, **kwargs)` forwards to `_compute_price_rule(self, products, quantity, currency=None, uom=None, date=False, compute_price=True, **kwargs)`. DEC-015's prescribed API was exactly right; only the code implementing it was still broken.
- **New tests**, `addons/dealflow360/tests/test_risk_engine.py` (registered in `tests/__init__.py`), 7 tests — the first coverage of any `df_*risk*` field:
  - `test_worked_example_scores_exactly_40_and_routes_medium` — reproduces DEC-003's own worked example (Gold customer; Hardware line list_price 1000 @ 12% given/15% allowed; Services line list_price 500 @ 18% given/10% allowed) and asserts the score is **exactly** 40.0 and routes MEDIUM.
  - `test_risk_weighting_uses_pre_discount_reference_value` — same pair; independently computes what the score *would* be under post-discount weighting (~39.26, matching the warning comment in `sale_order.py`) and asserts the real engine's answer is the pre-discount one (40.0), not that.
  - `test_risk_score_caps_at_100` — a zero-ceiling test category + 90% discount pushes the raw formula to 810; asserts the stored value clips at exactly 100.0.
  - `test_risk_level_none_when_every_line_within_ceiling` — discount exactly at the ceiling → score 0.0, level `none`, no summary.
  - `test_risk_level_boundary_against_configurable_threshold` — sets `dealflow.risk_high_min` to a **non-default** 27 via `ir.config_parameter`, and proves score==27 stays MEDIUM while score==36 (after a `write()` on the same line, re-read) flips to HIGH — this is the DEC-010 configurability itself under test, not just the default-40 boundary.
  - `test_reference_price_without_pricelist_uses_list_price` / `test_reference_price_with_pricelist_is_not_double_counted` — pricelist reference pricing in **both directions**. The pricelist test creates a real `product.pricelist` with a 10%-global percentage item, asserts Odoo actually priced the line at 900 (not just that the formula compiles), asserts zero excess at zero extra rep discount (proving DEC-009's no-double-count rule against a **real** pricelist record — exactly the case DEC-015 said was previously unsaveable), then asserts a further 20% rep discount on top of that pricelist price yields 5 excess points against the 15% ceiling.
- **First real live verification of the project.** Ran `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --test-enable --stop-after-init` twice (once right after my changes, once again after pulling Kevin's concurrent DF-005b/c UI push to confirm nothing regressed). Actual result line both times: **`0 failed, 0 error(s) of 19 tests when loading database 'dealflow360'`** (4 discount-tier + 8 governance + 7 new risk-engine). Module also installs cleanly from scratch: `-i dealflow360 --stop-after-init` loaded 60 modules, 0 errors.

**Important files**
- `addons/dealflow360/models/sale_order_line.py` — the DEC-015 fix.
- `addons/dealflow360/tests/test_risk_engine.py` — new.
- `addons/dealflow360/tests/__init__.py` — registers it.

**Current state**
- The stack is up and left running (`docker compose ps` shows both containers `Up`). Module `dealflow360` is installed in the `dealflow360` database with demo data seeded via `post_init_hook`.
- Exact commands for the next agent:
  ```bash
  docker compose up -d
  docker compose exec odoo odoo -d dealflow360 -u dealflow360 --stop-after-init          # upgrade after code changes
  docker compose exec odoo odoo -d dealflow360 -u dealflow360 --test-enable --stop-after-init   # run the full suite
  docker compose logs -f odoo                                                             # server logs
  ```
- Mid-task, the human changed the required commit identity from `shingaladeep23-gif` to `Jeel1210 <jeel.aghera@gmail.com>` (see `807ef7f`, `CLAUDE.md` §2/2c/2d). I verified this was a deliberate, documented change (not a stray `git config --global` from another agent) before committing under it — everything in this entry is pushed as `Jeel1210`.
- Concurrent working is now live: Kevin pushed DF-005b/c (risk gauge, quotation kanban) to `main` while this task was running with zero conflicts, since we stayed in our separate lanes (models/tests vs. views/static).

**Dependencies**
- None blocking. DF-004 (approval chain) can now start for real — DF-003's risk engine is tested and live-verified, so approval routing has a trustworthy signal to key off.

**Known issues**
- DEC-014 (`dealflow.category.limit` still shadows `product.category.df_max_discount`) is still live — explicitly out of scope for this task (DF-003c), untouched here.
- A harmless `OSError: [Errno 98] Address already in use` prints on stderr from a background `httpd` thread every time you run a one-off `odoo` exec while the main container's own `entrypoint.sh` is already bound to :8069. Cosmetic — it does not affect test execution or exit codes; both are separate processes inside the same container racing for the same port, and only one needs it.

**Remaining work**
- DF-003c (DEC-014 removal — `dealflow.category.limit` cleanup), then DF-004 (approval chain: `dealflow.approval` model, Sales Manager → Finance routing keyed off `df_risk_level`, audit trail).

**Recommended next task**
- DF-003c (Atlas), then DF-004 (Atlas).

**Tests performed**
- `docker compose exec odoo odoo -d dealflow360 -i dealflow360 --stop-after-init` — clean install, 60 modules, 0 errors.
- `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --test-enable --stop-after-init` — **0 failed, 0 error(s) of 19 tests** (real Odoo test runner, run twice, including once after Kevin's concurrent UI push).
- Manually confirmed via `docker compose exec db psql` that the `dealflow360` module row was `uninstalled` before the first install and that the test run above was against the genuinely upgraded module.

---

## DF-014 / DF-016 (first pass) — Portal foundation, negotiation model, isolation tests — Pam — 2026-09-05

**Completed work**
- `dealflow.negotiation` model (`models/negotiation.py`): `order_id`, `state` (proposed/applied/requires_reapproval/rejected), `counter_discount`, `risk_level_before/after`, `applied_by_id`; inherits `mail.thread` directly instead of a separate `.message` model (DEC-016 - `message_ids` in architecture.md's table is native chatter, not a bespoke model). `_apply()` writes the flat counter-discount % onto every discountable line via a plain `write()` and reads back `order.df_risk_level` — it never reimplements Atlas's DF-002/DF-003 ceiling/excess/risk math (DEC-017).
- DEC-012's portal isolation rule, implemented: a **global** `ir.rule` on `sale.order` (`partner_id child_of user.commercial_partner_id`, read-only) plus the same pattern on `dealflow.negotiation`. Explicit portal-group ACL rows added for both models (read-only) and full/appropriate CRUD for the internal DealFlow groups.
- `controllers/portal.py` (`DealflowPortal(CustomerPortal)`): genuinely separate routes (not the native sale-portal quote/order screens) — `/my/quotations` (list), `/my/quotation/<id>` (detail), and POST `/comment`, `/counter`, `/confirm`. Every route re-resolves the record through the *non-sudo* env first (`check_access_rights`/`check_access_rule`) so the DEC-012 rule is actually exercised per request, sudo-ing only after that check passes — mirrors Odoo's own `_document_check_access` pattern. The detail GET route deliberately lets `AccessError`/`MissingError` propagate (→ 403/404) rather than redirecting, per AT-08's literal wording.
- `views/portal_templates.xml`: bespoke Bootstrap templates for the list/detail screens (status badge, line table, counter-discount form, negotiation history, comment form with a line picker) — exposes only lines/totals/status/comments/counter-discount/confirm, never margin/risk score/approval internals (AT-08).
- Comments/change-requests use the **order's own native chatter** (`sale.order` already has `mail.thread`), tagged with the target line's name in the body — no new model needed for this either.
- Confirm route blocks portal confirmation whenever `df_risk_level != 'none'` or an open `requires_reapproval` negotiation exists, posting an audit note; this is an interim gate until Atlas's DF-004 approval chain exists to hook into properly (DF-015 is `⛔`, tracked in `docs/task_plan.md`).
- Tests: `tests/test_portal_isolation.py` (DF-016) proves cross-customer denial **at the ORM level** — `search`, `search_read`, `browse().read()`, and a write attempt — for two portal users linked to the seeded Acme/Beta partners, per DEC-012's explicit requirement not to rely on the HTTP route alone. `tests/test_negotiation.py` (DF-014) covers the within-ceiling and over-ceiling (`requires_reapproval`) counter-discount paths against the real Setup-Service worked example, the chatter audit post, and the no-lines guard.
- DEC-016 (chatter instead of a separate message model) and DEC-017 (single flat counter-discount %, not per-line) added to `docs/decisions.md`.

**Important files**
- `addons/dealflow360/models/negotiation.py`, `models/__init__.py`
- `addons/dealflow360/controllers/__init__.py`, `controllers/portal.py`
- `addons/dealflow360/views/portal_templates.xml`
- `addons/dealflow360/security/dealflow_security.xml`, `security/ir.model.access.csv`
- `addons/dealflow360/tests/test_portal_isolation.py`, `tests/test_negotiation.py`
- `docs/decisions.md` (DEC-016, DEC-017)

**Current state**
- Committed and pushed to `main` (`fefe9fc`, `34be97b`). Concurrent-mode lane note: `dealflow.negotiation` sits in `models/` (nominally Atlas's lane under the new CONCURRENT WORKING rule) but was pre-assigned to Pam in architecture.md/ui_spec.md/task_plan.md before that rule existed; flagged to Michael via hive message before touching it, proceeded since it's a net-new file with a single appended import line and no edits to Atlas's existing model files. Same reasoning for `views/portal_templates.xml` (new file, not touching Kevin's existing views).
- **Not verified live.** Docker's daemon socket is not reachable from this agent's sandbox (`permission denied` on `unix:///Users/jeelaghera/.docker/run/docker.sock`) and Atlas owns the shared stack lifecycle per the concurrency rules, so no live install/upgrade or portal click-through has been run yet. Verified statically only: `py_compile` on every new/changed `.py` file, `xml.dom.minidom.parse` on the new XML, and manual review of the CSV column count.

**Dependencies**
- DF-015 (automatic reapproval + full customer confirmation) needs Atlas's DF-004 (`dealflow.approval`) to exist — the portal-side interim gate here should be replaced with a real reapproval-chain trigger once DF-004 lands, not layered on top of it.
- DF-007 (end-to-end QA of the vertical slice) still lists DF-014 as a dependency; this pass should unblock that once DF-004 also lands.

**Known issues**
- `action_confirm()` in the confirm route runs under `sudo()` (as is standard for portal-mediated native workflow actions), so the resulting `sale.order` state change is attributed to whichever user's session performed the sudo call, not a distinct "confirmed by customer" record — there is no field for that in the current schema. Acceptable for now; flagging in case DF-015/DF-020 want an explicit "customer-confirmed" audit trail.
- Live server-log/browser-console verification (module upgrade, `/my/quotations` and `/my/quotation/<id>` click-through, counter-discount submit, isolation attack via URL manipulation) is still outstanding — first thing to do once the shared Odoo stack is available and DF-014 is picked back up.

**Remaining work**
- Live verification once Docker/Atlas's stack is reachable: install/upgrade, run the full test suite (`test_portal_isolation.py`, `test_negotiation.py`) under the Odoo test runner, and a manual portal click-through as two different portal users to confirm the 403/404 behavior in the browser, not just the ORM.
- DF-015's real reapproval-chain hook once DF-004 lands.
- Line-level comments currently tag the line in the chatter message body only — consider a dedicated `dealflow.negotiation`-linked comment view in the backend (Screen 11's "optional read-only panel" in `docs/ui_spec.md`) if Michael wants reps to see this without opening chatter — not required by AT-08 as written.

**Recommended next task**
- Once Atlas's DF-004 lands: wire `dealflow.negotiation`'s `requires_reapproval` state into a real `dealflow.approval` record (completes DF-015), then run DF-007's full vertical-slice QA pass, which also re-verifies the still-open DEC-014/DEC-015 findings.

**Tests performed**
- `python -m py_compile` on every new/changed `.py` file under `addons/dealflow360/` — all pass.
- `xml.dom.minidom.parse` on `security/dealflow_security.xml` and `views/portal_templates.xml` — both well-formed.
- Manual column-count check on `security/ir.model.access.csv` (8 columns per row, matches header) after appending new rows.
- Could **not** run: module install/upgrade, the new Odoo test suites under the real test runner, or any browser-based check — all require the shared Docker stack, unreachable from this sandbox (see Known issues).

---

## DF-000b — Resumption audit: repository state vs. previous-team claims — Michael — 2026-09-05

**Completed work**
- Re-cloned `main` at `92993e8` and audited the actual code against the inherited summaries. Findings are recorded claim-by-claim in `docs/task_plan.md` -> *Current state*; the short version is that **both QA bugs Pam found are still live in the code** — only their decision records were committed.
- Reconciled `docs/task_plan.md`, whose status block was stale (it listed DF-003 as not started although the risk engine is committed).
- Set the repo-local git identity to `shingaladeep23-gif <shingaladeep23@gmail.com>`, matching every existing commit. A fresh clone otherwise inherits a different global identity, which would have broken the account rule on the first push.

**Important files**
- `docs/task_plan.md` — the verification table; read it before trusting any older status text.
- `addons/dealflow360/models/sale_order_line.py:31-48` — `_df_reference_price`, still on the broken pre-17 API.
- `addons/dealflow360/models/sale_order.py:90-145` — `_compute_df_risk`, the committed DEC-003 engine.

**Current state**
- DF-001, DF-001e and DF-002 land as described. DF-003's engine is committed but untested and unproven live.
- DEC-014 and DEC-015 are **documented but not implemented**.

**Dependencies**
- The Docker daemon is now running (`29.5.2`) — the constraint that blocked every previous live-verification attempt. The `odoo:17` + `postgres:15` stack has still never been started; no DealFlow containers exist.

**Known issues**
- `product.with_context(pricelist=...).price` in `_df_reference_price` raises `AttributeError` on Odoo 17, so a quotation line under a pricelist cannot be saved. Demo-stopping, and currently on `main`.
- `dealflow.category.limit` still shadows `product.category.df_max_discount`; the admin-facing Category Limits screen still has no effect on quotation behaviour.
- The `gh` CLI holds an invalid keyring token. Irrelevant to the work — use plain `git`, whose osxkeychain credentials are valid.

**Remaining work**
- DF-003b (next), DF-003c, DF-004, then Phases 4-9.

**Recommended next task**
- **DF-003b (Atlas)** — start the stack, fix DEC-015 at the root, add the missing risk tests, and produce the project's first live verification.

**Tests performed**
- `git log`, `git status`, full file-tree inspection, and targeted greps for every field and model named in the resumption brief. No code was executed and nothing was installed — this entry reports only what was read.

---

## DF-001e — Security cleanup from Pam's DF-001d smoke test — Atlas — 2026-09-05

**Completed work**
- **Menu scoping (finding 1):** all 13 `dealflow360` menus (root + 9 top-level children + Configuration + its 2 children) now carry `groups`, where previously only Configuration did. `menu_dealflow_root` and the general-purpose children (Dashboard, Approvals, Subscriptions, Invoices, Deal Health, Reports) are scoped to `group_dealflow_sales_rep,group_dealflow_finance`; Quotations/Fulfillment/Products (rep-only work) to `group_dealflow_sales_rep`; Approvals to `group_dealflow_sales_manager,group_dealflow_finance` (the two approver roles). `group_dealflow_sales_manager`/`group_dealflow_admin` imply `group_dealflow_sales_rep` (see `dealflow_security.xml`), so listing `sales_rep` already covers Manager and Admin — Finance is listed separately everywhere it needs access since Finance does not imply `sales_rep`.
- **Menu cascade (finding 2):** `Discount Tiers` and `Category Limits` now each carry their own `groups="group_dealflow_admin"` — confirmed Odoo does not inherit a parent's `groups_id` to children, so the Configuration folder being admin-only did not previously protect its two child menu items from being individually navigable.
- **DEC-013 (finding 3):** added `access_dealflow_discount_tier_finance` / `access_dealflow_category_limit_finance` rows to `ir.model.access.csv` granting Finance **read-only** access to both models (write/create/unlink remain Admin-only, unchanged) — Finance previously had zero access to the ceilings it needs to see when approving a HIGH-risk quotation.
- Added a one-line XML comment on `group_dealflow_sales_manager`'s `implied_ids` noting `sales_team.group_sale_manager` is the Sales app's own "Administrator" level, not `base.group_system` — so the bare word doesn't misread as an escalation in a future diff review.

**Important files**
- `addons/dealflow360/views/dealflow_menus.xml` (all `groups` attributes added)
- `addons/dealflow360/security/ir.model.access.csv` (2 new Finance rows)
- `addons/dealflow360/security/dealflow_security.xml` (comment only)

**Current state**
- Verified live: `-u dealflow360 --test-enable --stop-after-init` — 0 errors, all 12 existing tests still pass (no regression).
- Verified the fix actually took effect, not just "installed without error" — queried `ir_model_access` directly: Finance now has `perm_read=t, perm_write=f` on both `dealflow.discount.tier` and `dealflow.category.limit`. Queried `ir_ui_menu`/`ir_ui_menu_group_rel` via each menu's xmlid and confirmed the exact group set on all 13 menus matches what was written (e.g. `menu_dealflow_discount_tiers` → `{Admin}` only, `menu_dealflow_root` → `{Sales Rep, Finance}`, `menu_dealflow_approvals` → `{Sales Manager, Finance}`).

**Dependencies**
- None. This was a standalone fix requested ahead of DF-003.

**Known issues**
- None found. This closes all three DF-001d findings; Pam's underlying report already confirmed the ACL write-block was sound (Rep/Manager could not write ceilings) — these were navigation/visibility and read-access gaps only.

**Remaining work**
- None for this task. DF-003 (blended risk engine) is next.

**Recommended next task**
- DF-003, per god's release.

**Tests performed**
- `docker compose exec odoo odoo -d dealflow360 -u dealflow360 --test-enable --stop-after-init` — 0 errors, 12/12 tests pass (no new tests needed — this is a data/security fix, not new business logic).
- Direct `psql` verification of `ir_model_access` (Finance read-only rows) and `ir_ui_menu`/`ir_ui_menu_group_rel` (exact group set per menu via xmlid) — both confirmed as specified above.

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
