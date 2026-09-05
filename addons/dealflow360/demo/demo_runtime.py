"""Runtime demo seed: role users and worked demo deals.

Why this file exists
--------------------
docs/DEMO_ACCOUNTS.md documented five internal logins and two portal logins,
and docs/demo_script.md walked through a set of quotations - but none of that
was ever *code*. The accounts and orders had been created by hand through the
ORM in throwaway sessions, so the file itself admitted "they live only in the
dealflow360 database ... a database rebuild loses them". A rebuild duly
happened: the shared demo database ended up with the partners, products,
warehouses and stock that demo_data.py seeds, and zero users and zero
quotations. Every documented demo flow was unreproducible, which is most of
why the product "did not work" when opened through the UI.

Everything here is therefore idempotent and re-runnable: it is called from
post_init_hook on a fresh install AND from a migration for databases that are
already installed, and running it twice is a no-op. Nothing is hardcoded that
the engines are supposed to derive - the deals below set only inputs
(products, quantities, discounts, owners) and let the real governance, risk,
approval, fulfillment and billing code produce every result.
"""

from odoo import fields

DEMO_PASSWORD = "dealflow360"

# Every user needs a real email. Odoo resolves the chatter author's email as
# the sender for message_post(), and raises "Unable to send message, please
# configure the sender's email address" when it cannot - which took down any
# flow that posts to the chatter. Live-verified: accepting a warehouse split
# as df.rep failed outright, because dealflow.warehouse.split.action_confirm()
# posts a note on the order. Portal comments and negotiation notes sit behind
# the same call.
INTERNAL_USERS = [
    ("df.admin", "Aditi Admin", "dealflow360.group_dealflow_admin"),
    ("df.manager", "Marcus Sales Mgr", "dealflow360.group_dealflow_sales_manager"),
    ("df.finance", "Fiona Finance", "dealflow360.group_dealflow_finance"),
    ("df.rep", "Riya Sales Rep", "dealflow360.group_dealflow_sales_rep"),
]


def _ensure_internal_users(env):
    """One user per implemented role. Each gets exactly its own DealFlow
    group - deliberately NOT stacked - so cross-role visibility differences
    in the UI are real access control, not a cosmetic filter."""
    users = {}
    for login, name, group_xmlid in INTERNAL_USERS:
        user = env["res.users"].with_context(active_test=False).search(
            [("login", "=", login)], limit=1
        )
        group = env.ref(group_xmlid)
        if user:
            # Repair rather than duplicate: an existing account keeps its id
            # (and anything pointing at it) but is re-armed with the known
            # demo password and its role group.
            user.write(
                {
                    "active": True,
                    "password": DEMO_PASSWORD,
                    "groups_id": [(4, group.id)],
                }
            )
            if not user.email:
                user.email = "%s@dealflow360.example" % login
        else:
            user = env["res.users"].create(
                {
                    "name": name,
                    "login": login,
                    "password": DEMO_PASSWORD,
                    "email": "%s@dealflow360.example" % login,
                    "groups_id": [(6, 0, [env.ref("base.group_user").id, group.id])],
                }
            )
        users[login] = user
    return users


def _ensure_portal_users(env):
    """Portal logins for the two demo customers. The contact is created as a
    CHILD of the company partner, which is what makes the portal isolation
    rule ('partner_id child_of commercial_partner') meaningful: the customer
    sees their company's quotations and no one else's."""
    portal_group = env.ref("base.group_portal")
    users = {}
    for login, name, company_name in [
        ("acme.customer", "Acme Buyer", "Acme Corp"),
        ("beta.customer", "Beta Buyer", "Beta Industries"),
    ]:
        company = env["res.partner"].search(
            [("name", "=", company_name), ("is_company", "=", True)], limit=1
        )
        if not company:
            continue
        user = env["res.users"].with_context(active_test=False).search(
            [("login", "=", login)], limit=1
        )
        if user:
            user.write({"active": True, "password": DEMO_PASSWORD})
            if not user.email:
                user.email = "%s@example.com" % login
            users[login] = user
            continue
        contact = env["res.partner"].search(
            [("name", "=", name), ("parent_id", "=", company.id)], limit=1
        ) or env["res.partner"].create(
            {
                "name": name,
                "parent_id": company.id,
                "email": "%s@example.com" % login,
            }
        )
        users[login] = env["res.users"].create(
            {
                "name": name,
                "login": login,
                "password": DEMO_PASSWORD,
                "partner_id": contact.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )
    return users


def _ensure_core_plan_has_a_plan(env):
    """The 'Core Plan' product was seeded with df_is_recurring=True but no
    df_recurring_plan_id (the plan model did not exist yet when demo_data.py
    was written). A recurring line with no plan half-works: confirming it
    does start a subscription, but _compute_df_mrr and _df_schedule_next_bill
    both bail out without a plan - so the Subscriptions screen showed MRR 0
    and the cron never queued a second cycle. Attach the monthly plan."""
    core_plan = env["product.template"].search([("name", "=", "Core Plan")], limit=1)
    if core_plan and not core_plan.df_recurring_plan_id:
        core_plan.df_recurring_plan_id = env.ref(
            "dealflow360.recurring_plan_monthly"
        ).id


def _line(product, qty, discount=0.0):
    return (0, 0, {
        "product_id": product.product_variant_id.id,
        "product_uom_qty": qty,
        "discount": discount,
    })


def _ensure_demo_deals(env):
    """Four worked quotations, each chosen to exercise a different engine.

    Ceilings in play (min(customer tier, product category)):
      Acme = Gold 15%, Beta = Silver 10%; Hardware 15%, Services 10%.

    The discounts below are inputs only - risk score, risk level, routing,
    margin, allocation and health are all produced by the real engines.
    """
    Order = env["sale.order"]
    if Order.search_count([]):
        return Order.browse()  # already seeded; never duplicate deals

    partners = {
        p.name: p
        for p in env["res.partner"].search(
            [("name", "in", ["Acme Corp", "Beta Industries"]), ("is_company", "=", True)]
        )
    }
    products = {
        p.name: p
        for p in env["product.template"].search(
            [("name", "in", [
                "ProBook Laptop", "Onsite Setup Service", "Core Plan", "Docking Station",
            ])]
        )
    }
    if len(partners) < 2 or len(products) < 4:
        return Order.browse()

    users = {
        u.login: u
        for u in env["res.users"].search([("login", "in", ["df.rep", "df.manager"])])
    }
    rep = users.get("df.rep")
    manager = users.get("df.manager")

    orders = Order.create([
        {
            # Within every ceiling -> risk NONE, confirmable directly. 10 units
            # of ProBook against 6 at Main + 4 at East is the DF-010 split.
            "partner_id": partners["Acme Corp"].id,
            "user_id": rep.id if rep else False,
            "order_line": [_line(products["ProBook Laptop"], 10, 10.0)],
        },
        {
            # Services ceiling is 10% for Acme; 25% overshoots by 15 points ->
            # the risk engine flags it and routing sends it for approval.
            "partner_id": partners["Acme Corp"].id,
            "user_id": rep.id if rep else False,
            "order_line": [
                _line(products["Onsite Setup Service"], 4, 25.0),
                _line(products["Docking Station"], 5, 5.0),
            ],
        },
        {
            # Beta is Silver (10%): 18% on hardware overshoots by 8 points.
            "partner_id": partners["Beta Industries"].id,
            "user_id": rep.id if rep else False,
            "order_line": [_line(products["ProBook Laptop"], 2, 18.0)],
        },
        {
            # Hybrid: a one-time hardware line plus a recurring plan line, so
            # DF-012's subscription/billing path has something real to run on.
            "partner_id": partners["Acme Corp"].id,
            "user_id": manager.id if manager else False,
            "order_line": [
                _line(products["ProBook Laptop"], 2),
                _line(products["Core Plan"], 1),
            ],
        },
    ])
    return orders


def _route_one_approval(env, orders):
    """Put one deal into a genuinely pending approval chain so the Approvals
    screen has real work on it and a manager can act in the demo. Uses the
    real routing entry point - no hand-built approval rows."""
    if not orders:
        return
    risky = orders.filtered(lambda o: o.df_risk_level in ("medium", "high"))
    if not risky:
        return
    order = risky[0]
    if order.df_approval_id:
        return
    order.df_approval_id = env["dealflow.approval"]._create_for_order(order).id


def seed_runtime_demo(env):
    """Idempotent entry point, called from post_init_hook and from the
    17.0.1.2.0 migration."""
    _ensure_internal_users(env)
    _ensure_portal_users(env)
    _ensure_core_plan_has_a_plan(env)
    orders = _ensure_demo_deals(env)
    _route_one_approval(env, orders)
    # Give the deal-health engine its first real pass, so DF-017's screen is
    # populated from the cron's own code path rather than left blank.
    env["sale.order"].search([("state", "in", ("draft", "sent", "sale"))])._compute_deal_health()
    return orders
