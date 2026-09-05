# DealFlow360 — Task Plan

**Legend:** ✅ done · 🔄 in progress · ⬜ todo · ⛔ blocked

## Phase 0 — Inspection & Architecture (Michael)
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-000 | Inspect repo, git identity, remote, tooling; read problem statement + mockup; author architecture, decisions, docs scaffold | Michael | ✅ |

## Phase 1 — Odoo Foundation
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-001 | Docker stack (Odoo 17 + PG 15), `dealflow360` addon skeleton, security groups, menus, seed data (customers/tiers/products/categories/warehouses/stock) | Atlas | 🔄 |

## Phase 2 — Quotation Core
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-002 | Extend `sale.order` / `sale.order.line`: tier + category ceilings, per-line excess, live margin | Atlas | ⬜ |

## Phase 3 — Discount / Risk / Approval  ← **vertical slice target**
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-003 | Blended risk scoring engine per DEC-003 + backend unit tests | Atlas | ⬜ |
| DF-004 | Approval chain (`dealflow.approval`, steps, routing) + audit log | Atlas | ⬜ |
| DF-005 | Sales Workspace: dashboard, quotation list/pipeline, quotation builder UI | Don | ⬜ |
| DF-006 | Approval list + approval detail UI with risk gauge and approval timeline | Don | ⬜ |
| DF-007 | QA the full slice: login → quote → over-limit discount → auto-routing → approve | Pam | ⬜ |

## Phase 4 — Upsell / Cross-sell
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-008 | Deterministic recommendation engine + `dealflow.upsell.rule` | Atlas | ⬜ |
| DF-009 | Upsell panel OWL component with live margin delta | Don | ⬜ |

## Phase 5 — Warehouse Fulfillment
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-010 | Allocation engine per DEC-006, split model, real pickings, backorders | Atlas | ⬜ |
| DF-011 | Fulfillment list + split detail UI, accept/override, consolidate backorder | Don | ⬜ |

## Phase 6 — Hybrid Billing / Subscriptions
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-012 | Recurring plans, billing schedule → real `account.move`, proration, credit notes | Atlas | ⬜ |
| DF-013 | Subscriptions list, billing detail, invoices list/detail UI | Don | ⬜ |

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
| DF-018 | Deal Health dashboard + reporting screen with filters and export | Don | ⬜ |

## Phase 9 — Integration & Final QA
| ID | Task | Agent | Status |
|---|---|---|---|
| DF-019 | Full end-to-end regression of both demo flows | Pam | ⬜ |
| DF-020 | Demo rehearsal, seed-data reset script, final polish | Michael + all | ⬜ |

## Current state

- **Current:** DF-001 (Atlas) — Odoo foundation
- **Next:** DF-002 → DF-003 → DF-004 (backend vertical slice), then Don picks up UI
- **Blocked:** none

## Acceptance criteria summary

Every task is done only when: implemented → module upgrades cleanly → tested → documented → committed → pushed to `main`.
