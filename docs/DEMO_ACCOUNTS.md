# DealFlow360 — Demo Accounts

**URL:** http://localhost:8069 · **Database:** `dealflow360`

All accounts below were created and **verified by logging in over the real API**.
The "sees" column is what each account actually returned — not what it should
return in theory.

## Internal users

| Role | Login | Password | Sees quotations | Sees approvals | Sees tiers |
|---|---|---|---|---|---|
| Superuser / Administrator | `admin` | `admin` | 4 | 2 | 3 |
| DealFlow Admin — *Aditi Admin* | `df.admin` | `dealflow360` | 4 | 2 | 3 |
| Sales Manager — *Marcus Sales Mgr* | `df.manager` | `dealflow360` | 4 | 2 | 3 |
| Finance — *Fiona Finance* | `df.finance` | `dealflow360` | 4 | 2 | 3 |
| Sales Rep — *Riya Sales Rep* | `df.rep` | `dealflow360` | **0** ⚠️ | 2 | 3 |

## Portal (customer) users

| Customer | Login | Password | Sees quotations |
|---|---|---|---|
| Acme Corp — *Acme Buyer* | `acme.customer` | `dealflow360` | **3** (S00001, S00002, S00016) |
| Beta Industries — *Beta Buyer* | `beta.customer` | `dealflow360` | **1** (S00003) |

Portal users are correctly **denied** access to approvals and discount tiers.
Cross-customer isolation is real: Acme cannot see Beta's deal and vice versa.

---

## ⚠️ Known issue: Sales Rep sees 0 quotations

This is **native Odoo behaviour, not a DealFlow360 bug**. `group_dealflow_sales_rep`
implies `sales_team.group_sale_salesman`, whose record rule is *"Personal Orders"* —
a salesperson sees only orders where they are the `user_id`. All demo orders were
created by `admin`, so Riya legitimately sees none.

Two honest ways to fix it, depending on what you want to show:

1. **Assign demo deals to the rep** — set `user_id` on some orders to `df.rep`.
   Most realistic: the rep owns their pipeline.
2. **Grant `sales_team.group_sale_salesman_all_leads`** to the rep group — every
   rep sees all orders. Simpler, but weakens the ownership story.

I have **not** applied either, because it changes the security model and that is
your call.

---

## Roles: what actually exists

The problem statement (`DealFlow360.pdf` §3 "User Roles") defines **five** roles,
and the implementation matches them one-to-one:

| Problem statement role | Implemented group |
|---|---|
| Sales Rep | `dealflow360.group_dealflow_sales_rep` |
| Sales Manager / Approver | `dealflow360.group_dealflow_sales_manager` |
| Finance / Operations | `dealflow360.group_dealflow_finance` |
| Admin | `dealflow360.group_dealflow_admin` |
| Customer (Portal User) | `base.group_portal` |

There is **no 56-role model** anywhere in the codebase, the docs, or the problem
statement. If 56 roles are required they need to be specified before they can be
built — see the open question on the task board.

---

## Recreating these accounts

Password for every seeded account is `dealflow360`. They live only in the
`dealflow360` database (created via the ORM, not in module data), so a database
rebuild loses them.
