# DealFlow360 — Task Plan

**Legend:** ✅ done · 🔄 in progress · ⬜ todo · ⛔ blocked

## Phase 0 — Inspection & Architecture (Michael)
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-000 | Inspect repo, git identity, remote, tooling; read problem statement + mockup; author architecture, decisions, docs scaffold | Michael | ✅ |

## Phase 1 — Odoo Foundation
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-001 | Docker stack (Odoo 17 + PG 15), `dealflow360` addon skeleton, security groups, menus, seed data (customers/tiers/products/categories/warehouses/stock) | Atlas | ⛔ (code complete, install unverified — Docker Desktop Linux engine down) |

## Phase 2 — Quotation Core
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-002 | Extend `sale.order` / `sale.order.line`: tier + category ceilings, per-line excess, live margin | Atlas | ⬜ |

## Phase 3 — Discount / Risk / Approval  ← **vertical slice target**
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-003 | Blended risk scoring engine per DEC-003 + backend unit tests | Atlas | ⬜ |
| DF-004 | Approval chain (`dealflow.approval`, steps, routing) + audit log | Atlas | ⬜ |
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

- **Current:** DF-001 (Atlas) — Odoo foundation code complete, pushed to `main`; install/upgrade **not yet verified** because Docker Desktop's Linux (WSL2) engine is not coming up on this machine (`docker info` returns 500; `wsl -l -v` shows no `docker-desktop` distro registered at all). Escalated to Michael/human.
- **Next:** Verify DF-001 installs cleanly once Docker is fixed, then DF-002 → DF-003 → DF-004 (backend vertical slice), then Don picks up UI
- **Blocked:** DF-001 install verification — needs Docker Desktop's Linux engine working (human/infra action, not an architecture issue)

## Acceptance criteria summary

Every task is done only when: implemented → module upgrades cleanly → tested → documented → committed → pushed to `main`.
