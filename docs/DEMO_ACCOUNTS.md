# DealFlow360 — Demo Accounts

**URL:** http://localhost:8069 · **Database:** `dealflow360`

All accounts below were created and **verified by logging in over the real API**.
The "sees" column is what each account actually returned — not what it should
return in theory.

## Internal users

| Role | Login | Password | Sees quotations | Approvals | Tiers |
|---|---|---|---|---|---|
| Superuser / Administrator | `admin` | `admin` | 4 — all | 2 | 3 |
| DealFlow Admin — *Aditi Admin* | `df.admin` | `dealflow360` | 4 — all | 2 | 3 |
| Sales Manager — *Marcus Sales Mgr* | `df.manager` | `dealflow360` | 4 — all | 2 | 3 |
| Finance — *Fiona Finance* | `df.finance` | `dealflow360` | 4 — all | 2 | 3 |
| Sales Rep — *Riya Sales Rep* | `df.rep` | `dealflow360` | **3 — own only** (S00001, S00003, S00016) | 2 | 3 |

**The access model demonstrates itself.** Log in as `df.rep` and then as
`df.manager` on the same screen: the rep sees only the three deals they own,
the manager sees the whole pipeline including S00002 (owned by the manager).
That contrast is worth showing an evaluator — it is Odoo's native ownership
rule doing real work, not a cosmetic filter.

## Portal (customer) users

| Customer | Login | Password | Sees quotations |
|---|---|---|---|
| Acme Corp — *Acme Buyer* | `acme.customer` | `dealflow360` | **3** (S00001, S00002, S00016) |
| Beta Industries — *Beta Buyer* | `beta.customer` | `dealflow360` | **1** (S00003) |

Portal users are correctly **denied** access to approvals and discount tiers.
Cross-customer isolation is real: Acme cannot see Beta's deal and vice versa.

---

## Salesperson ownership (resolved)

`df.rep` originally saw **0** quotations: `group_dealflow_sales_rep` implies
`sales_team.group_sale_salesman`, whose native *Personal Orders* rule shows only
orders where the user is the salesperson — and every seeded order belonged to
`admin`. That was native Odoo behaviour, not a DealFlow360 bug.

Resolved as **demo data, not a security change**: the deals were assigned to
realistic owners.

| Order | Salesperson |
|---|---|
| S00001 | Riya Sales Rep |
| S00003 | Riya Sales Rep |
| S00016 | Riya Sales Rep |
| S00002 | Marcus Sales Mgr |

The record rule itself was left untouched, so the ownership model is still real.

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

Password for every seeded account is `dealflow360`.

These accounts are **seeded in code** (`addons/dealflow360/demo/demo_runtime.py`)
and are recreated automatically:

- on a fresh install, by `post_init_hook`
- on an upgrade of an existing database, by the `17.0.1.2.0` migration

The seed is idempotent, so re-running it is a no-op. The same file also creates
the worked demo quotations the flows below use.

This was previously not the case: the accounts had been created by hand through
the ORM in throwaway sessions and were documented as living "only in the
dealflow360 database". A database rebuild duly lost all of them along with every
demo quotation, which is why the product appeared to have no working features
when opened through the UI. Anything the demo depends on now lives in code.
