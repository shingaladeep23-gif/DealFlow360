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
| DF-003 | Blended risk scoring engine per DEC-003 + backend unit tests | Atlas | 🔄 engine committed (92993e8); **no risk unit tests exist**, never live-verified |
| DF-004 | Approval chain (`dealflow.approval`, steps, routing) + audit log | Atlas | ⬜ (blocked on DF-003b; no approval model exists yet — `df_pipeline_stage` has a `pending_approval` value but nothing routes into it) |
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

_Reconciled by Michael against the actual repository at `92993e8` on 2026-09-05 (resumption audit).
The previous status block was stale — it listed DF-003 as not started when the engine was already committed._

**Verified present on `main` (read from code, not from summaries):**
- `df_blended_risk_score`, `df_risk_level`, `df_risk_summary` on `sale.order` (`models/sale_order.py:54-75`), computed in `_compute_df_risk` as `min(100, 6*blended_excess + 3*max_excess)` with the high/medium cut-off read from `ir.config_parameter` key `dealflow.risk_high_min` (DEC-010). Weighting uses each line's **pre-discount** reference value, as DEC-003's worked example requires.
- DF-002 governance fields: `df_effective_ceiling`, `df_excess_points`, `df_margin_pct` on the line; `df_margin_pct`, `df_pipeline_stage` on the order.
- 12 unit tests (8 governance + 4 foundation), including both `min()` directions (`test_tier_stricter_than_category` / `test_category_stricter_than_tier`).

**Verified NOT done, despite historical claims:**
| Claim | Reality |
|---|---|
| DEC-015 fixed | ❌ `sale_order_line.py:43-47` still calls `product.with_context(pricelist=...).price`. DEC-015 records that this attribute **does not exist** on Odoo 17 — this raises `AttributeError` and the line cannot be saved. Only the *decision doc* was committed (`c7111d3`); no code changed. |
| DEC-014 done | ❌ `dealflow.category.limit` still exists in `models/discount_tier.py:27` and in `data/category_limit_data.xml`, `views/discount_tier_views.xml`, `views/dealflow_menus.xml`, `security/ir.model.access.csv` and `tests/test_discount_tier.py`. The desync Pam found is still live. |
| DF-003 complete | 🔄 Engine is committed but **zero tests reference any `df_*risk*` field**, and no live run has ever happened. |
| Approval consumes risk | ❌ DF-004 has not started. No `dealflow.approval` model exists. |
| "tests 12/12 passing" | ⚠️ Unproven. Handoff states the Odoo test runner was **never** run — only `py_compile` and XML well-formedness. The count is real; the pass result is not evidence. |
| Live install verified | ❌ Never. Every handoff entry cites the Docker stack being down. |

**Environment change that unblocks the project:** the Docker daemon is now **running** (`29.5.2`). The stack in `docker-compose.yml` (odoo:17 + postgres:15) has never been started — no DealFlow containers exist. This removes the constraint that blocked every previous live-verification step.

**Git:** clone lives at `/Users/jeelaghera/Documents/DEALFLOW360/DealFlow360`, on `main`, clean, remote `shingaladeep23-gif/DealFlow360`. Repo-local identity set to `shingaladeep23-gif <shingaladeep23@gmail.com>` to match all existing commits; credentials resolve via `osxkeychain`.

- **Next:** DF-003b (Atlas) — stand the stack up, fix DEC-015, add risk tests, live-verify. Then DF-003c (DEC-014 removal), then DF-004.
- **Blocked:** DF-004 and all UI work, on DF-003b.

## Acceptance criteria summary

Every task is done only when: implemented → module upgrades cleanly → tested → documented → committed → pushed to `main`.
