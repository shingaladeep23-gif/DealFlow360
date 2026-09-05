# DealFlow360 — Task Plan

**Legend:** ✅ done · 🔄 in progress · ⬜ todo · ⛔ blocked

## Phase 0 — Inspection & Architecture (Michael)
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-000 | Inspect repo, git identity, remote, tooling; read problem statement + mockup; author architecture, decisions, docs scaffold | Michael | ✅ |

## Phase 1 — Odoo Foundation
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-001 | Docker stack (Odoo 17 + PG 15), `dealflow360` addon skeleton, security groups, menus, seed data (customers/tiers/products/categories/warehouses/stock) | Atlas | ✅ |

## Phase 2 — Quotation Core
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-002 | Extend `sale.order` / `sale.order.line`: tier + category ceilings, per-line excess, live margin | Atlas | ✅ |

## Phase 3 — Discount / Risk / Approval  ← **vertical slice target**
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-003 | Blended risk scoring engine per DEC-003 + backend unit tests | Atlas | ✅ engine (92993e8) + DEC-015 fix + 7 risk tests (DF-003b); 19/19 passing under the real Odoo test runner, live-verified against a cold-started stack |
| DF-004 | Approval chain (`dealflow.approval`, steps, routing) + audit log | Atlas | ⬜ (unblocked — DF-003 is done and live-verified; `df_pipeline_stage` has a `pending_approval` value but nothing routes into it yet) |
| DF-005 | Sales Workspace: dashboard, quotation list/pipeline, quotation builder UI | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; code blocked on DF-002/003/004 + Docker) |
| DF-006 | Approval list + approval detail UI with risk gauge and approval timeline | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; blocked on DF-004) |
| DF-007 | QA the full slice: login → quote → over-limit discount → auto-routing → approve | Pam | ⬜ |

## Phase 4 — Upsell / Cross-sell
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-008 | Deterministic recommendation engine + `dealflow.upsell.rule` | Atlas | ⬜ |
| DF-009 | Upsell panel OWL component with live margin delta | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; blocked on DF-008) |

## Phase 5 — Warehouse Fulfillment
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-010 | Allocation engine per DEC-006, split model, real pickings, backorders | Atlas | ⬜ |
| DF-011 | Fulfillment list + split detail UI, accept/override, consolidate backorder | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; blocked on DF-010; needs new shipping-cost field, see spec Summary 1 #5) |

## Phase 6 — Hybrid Billing / Subscriptions
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-012 | Recurring plans, billing schedule → real `account.move`, proration, credit notes | Atlas | ⬜ |
| DF-013 | Subscriptions list, billing detail, invoices list/detail UI | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; Invoices screens are pure-native and can start before DF-012; Subscriptions list needs a subscription-aggregate decision, see spec Summary 1 #7) |

## Phase 7 — Customer Portal / Negotiation
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-014 | Portal controllers, negotiation model, counter-discount, record rules | Pam | ⬜ |
| DF-015 | Automatic reapproval on renegotiated terms + customer confirmation | Pam | ⬜ |
| DF-016 | Portal authorization/isolation test suite (cross-customer access must fail) | Pam | ⬜ |

## Phase 8 — Deal Health / Reporting
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-017 | Health scoring per DEC-005, anomaly detection, cron | Atlas | ⬜ |
| DF-018 | Deal Health dashboard + reporting screen with filters and export | Don | ⬜ (design spec ready, see `docs/ui_spec.md`; blocked on DF-017; needs per-signal health fields, see spec Summary 1 #9-11) |

## Phase 9 — Integration & Final QA
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-019 | Full end-to-end regression of both demo flows | Pam | ⬜ |
| DF-020 | Demo rehearsal, seed-data reset script, final polish | Michael + all | ⬜ |

## Current state

_Updated by Atlas on 2026-09-05 after DF-003b: stack stood up (cold first start), DEC-015 fixed at the root, risk engine tests added, real live verification performed._

**Verified present on `main` (read from code and confirmed live, not from summaries):**
- `df_blended_risk_score`, `df_risk_level`, `df_risk_summary` on `sale.order` (`models/sale_order.py:54-75`), computed in `_compute_df_risk` as `min(100, 6*blended_excess + 3*max_excess)` with the high/medium cut-off read from `ir.config_parameter` key `dealflow.risk_high_min` (DEC-010). Weighting uses each line's **pre-discount** reference value, as DEC-003's worked example requires — now under explicit test (`test_risk_weighting_uses_pre_discount_reference_value`).
- DF-002 governance fields: `df_effective_ceiling`, `df_excess_points`, `df_margin_pct` on the line; `df_margin_pct`, `df_pipeline_stage` on the order.
- `_df_reference_price()` (`sale_order_line.py:31-48`) now calls `pricelist._get_product_price(...)`, confirmed against the installed Odoo 17 container source. A quotation line under a real `product.pricelist` saves and computes correctly — live-tested in `test_reference_price_with_pricelist_is_not_double_counted`.
- 19 unit tests (8 governance + 4 foundation + 7 risk engine), **0 failed, 0 error(s)** under the real Odoo test runner (`--test-enable`), run twice including once against Kevin's concurrent DF-005b/c UI push.
- Kevin's DF-005b/c landed concurrently on `main` (risk gauge OWL field, quotation kanban) with zero conflicts against this task's backend-only lane.

**Resolved from the previous audit:**
| Claim | Now |
|---|---|
| DEC-015 fixed | ✅ Fixed at the root in `sale_order_line.py`; live-verified with a real pricelist record, not just compiled. |
| DF-003 complete | ✅ Engine + 7 tests + live run, 19/19 passing. |
| "tests passing" | ✅ Now backed by an actual `--test-enable` run: `0 failed, 0 error(s) of 19 tests when loading database 'dealflow360'`. |
| Live install verified | ✅ Docker stack cold-started, module installs cleanly (60 modules, 0 errors) and upgrades cleanly. |

**Still open (unchanged, explicitly out of scope for DF-003b):**
- DEC-014 — `dealflow.category.limit` still shadows `product.category.df_max_discount` (DF-003c).
- DF-004 (approval chain) has not started. No `dealflow.approval` model exists yet.

**Git:** clone lives at `/Users/jeelaghera/Documents/DEALFLOW360/DealFlow360`, on `main`, remote `shingaladeep23-gif/DealFlow360`. Commit identity changed mid-project to `Jeel1210 <jeel.aghera@gmail.com>` (see `CLAUDE.md` §2/2c/2d, commit `807ef7f`) — every commit from `807ef7f` onward, including this task's, uses that identity; history before it is left as-is per the no-rewrite rule.

- **Next:** DF-003c (Atlas, DEC-014 removal), then DF-004 (Atlas, approval chain — now unblocked).
- **Blocked:** nothing load-bearing remains blocked on DF-003b.

## Acceptance criteria summary

Every task is done only when: implemented → module upgrades cleanly → tested → documented → committed → pushed to `main`.
