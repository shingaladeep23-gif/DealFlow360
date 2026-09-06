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

import base64

from odoo import fields
from odoo.tools import file_open

from .catalog_data import seed_catalog

DEMO_PASSWORD = "dealflow360"

COMPANY_NAME = "DealFlow360"
LOGO_PATH = "dealflow360/static/description/logo.png"

# Personal accounts that were created by hand during testing and left behind in
# the shared database as live customers and live logins. Archived rather than
# deleted: they may already be referenced by an order or a message, and
# unlinking a partner that is would fail or take real records with it.
PERSONAL_PARTNER_NAMES = ("jeel", "Jeel Aghera", "jeel aghera")
PERSONAL_LOGINS = ("Jeel Aghera", "jeel.aghera@gmail.com", "jeel")

# Free (unreserved) units each stockable product should have per warehouse.
#
# ProBook stays deliberately fragmented at 6 + 4: no single warehouse can fill
# a 10-unit order, which is the whole DF-010 split demonstration and must not
# be flooded away. Everything else simply needs enough headroom that a new
# quotation is not forced onto a backorder.
STOCK_TARGETS = {
    "ProBook Laptop": {"MAIN": 6.0, "EAST": 4.0},
    "Docking Station": {"MAIN": 25.0, "EAST": 15.0},
    "UltraWide Monitor": {"MAIN": 18.0, "EAST": 12.0},
    "Cable & Power Kit": {"MAIN": 60.0, "EAST": 40.0},
    "FieldPad Tablet": {"MAIN": 12.0, "EAST": 8.0},
    "Ergo Task Chair": {"MAIN": 20.0, "EAST": 10.0},
}

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


def _ensure_company_branding(env):
    """Name and badge the operating company.

    The company was still Odoo's out-of-the-box "My Company" with the default
    logo - and that default logo is base/static/img/res_company_logo.png, the
    placeholder that literally reads "Your Logo". It is what the login page
    renders, so the first screen anybody saw said "Your logo" above a company
    called "My Company".
    """
    company = env.ref("base.main_company", raise_if_not_found=False) or env.company
    if not company:
        return
    values = {}
    if company.name in ("My Company", "My Company (San Francisco)", False):
        values["name"] = COMPANY_NAME
    if not company.email:
        values["email"] = "hello@dealflow360.example"
    if not company.website:
        values["website"] = "https://dealflow360.example"
    if values:
        company.write(values)
    with file_open(LOGO_PATH, "rb") as logo:
        encoded = base64.b64encode(logo.read())
    if company.logo != encoded:
        company.logo = encoded


def _ensure_home_action(env, users):
    """Land people on the product, not on Discuss.

    With no home action set, Odoo drops the user on whatever root menu it
    resolves first, which in practice was Discuss - so every login opened a
    chat window instead of the sales workspace this application exists to be.
    Set explicitly on each role account, and on the template new users are
    copied from so a fresh signup gets the same landing.
    """
    workspace = env.ref(
        "dealflow360.action_dealflow_workspace", raise_if_not_found=False
    )
    if not workspace:
        return
    # res.users.action_id is a Many2one to ir.actions.actions, NOT a reference
    # field - ir.actions.client shares that table by inheritance, so the client
    # action's own id IS the right value. Writing the "model,id" reference
    # string that a reference field would take left the Home Action empty and
    # everyone still landing on Discuss.
    targets = env["res.users"].browse()
    for user in users.values():
        targets |= user
    template = env.ref("base.default_user", raise_if_not_found=False)
    if template:
        targets |= template
    for user in targets:
        if user.action_id.id != workspace.id:
            user.sudo().write({"action_id": workspace.id})


def _retire_personal_accounts(env):
    """Take the developer's own accounts out of the demo data.

    Live-found in the shared database: partners "jeel" and "Jeel Aghera" sat in
    the customer list as real customers, alongside portal logins "Jeel Aghera"
    (a login with a space in it) and jeel.aghera@gmail.com. None of them are
    created by this module - they were made by hand while testing and never
    cleaned up. Archiving keeps any history that already points at them intact.
    """
    partners = env["res.partner"].with_context(active_test=False).search(
        [("name", "in", list(PERSONAL_PARTNER_NAMES))]
    )
    users = env["res.users"].with_context(active_test=False).search(
        [("login", "in", list(PERSONAL_LOGINS))]
    )
    for user in users:
        if user.active:
            user.sudo().write({"active": False})
        partners |= user.partner_id
    for partner in partners:
        values = {}
        if partner.active:
            values["active"] = False
        if partner.customer_rank:
            values["customer_rank"] = 0
        if values:
            partner.sudo().write(values)


def _retire_qa_scratch_products(env):
    """Archive the throwaway products left behind by a manual QA session.

    Live-found: 16 templates named "ZZ Audit Widget A", "ZZ D backorder",
    "ZZ R monthly sub" and so on, all sitting in Odoo's default "All" category
    and all created inside one afternoon of hand-testing. They are not
    catalogue items - they outnumbered the real products two to one in the
    product list, and they are the reason two thirds of the catalogue had no
    description.

    The "ZZ " prefix is the marker the person doing that testing chose
    precisely so the rows would sort to the bottom and be identifiable later;
    matching on it is narrow and deliberate. Archived, never deleted: the
    quotations raised against them are real records with real history, and
    those keep working with an archived product.
    """
    scratch = env["product.template"].search([("name", "=like", "ZZ %")])
    if scratch:
        scratch.sudo().write({"active": False})


def _ensure_free_stock(env):
    """Guarantee every stockable product actually has unreserved stock.

    Live-found: AVAILABLE was 0 for every product in every warehouse, because
    the demo orders had confirmed and reserved the entire seeded quantity. Any
    new quotation could therefore only ever backorder, which makes the whole
    DF-010 allocation demo - and the "accept the suggested split" happy path -
    impossible to show. Tops FREE quantity up to the target, so it is a no-op
    on a database that already has headroom and never double-counts reserved
    units.
    """
    Quant = env["stock.quant"].sudo()
    warehouses = {
        wh.code: wh for wh in env["stock.warehouse"].search([])
    }
    for template_name, per_warehouse in STOCK_TARGETS.items():
        template = env["product.template"].search(
            [("name", "=", template_name)], limit=1
        )
        if not template or template.type != "product":
            continue
        variants = template.product_variant_ids
        if not variants:
            continue
        for code, target in per_warehouse.items():
            warehouse = warehouses.get(code)
            if not warehouse:
                continue
            # A template with variants holds the target PER VARIANT, so a
            # four-variant tablet does not quietly become four times the stock
            # of a single-variant monitor.
            for variant in variants:
                quants = Quant.search(
                    [
                        ("product_id", "=", variant.id),
                        ("location_id", "child_of", warehouse.lot_stock_id.id),
                    ]
                )
                free = sum(q.quantity - q.reserved_quantity for q in quants)
                shortfall = target - free
                if shortfall <= 1e-6:
                    continue
                existing = quants.filtered(
                    lambda q: q.location_id == warehouse.lot_stock_id
                )[:1]
                if existing:
                    existing.quantity += shortfall
                else:
                    Quant.create(
                        {
                            "product_id": variant.id,
                            "location_id": warehouse.lot_stock_id.id,
                            "quantity": shortfall,
                        }
                    )


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
    17.0.1.2.0 and 17.0.1.6.0 migrations."""
    _ensure_company_branding(env)
    _retire_personal_accounts(env)
    _retire_qa_scratch_products(env)
    users = _ensure_internal_users(env)
    _ensure_home_action(env, users)
    _ensure_portal_users(env)
    _ensure_core_plan_has_a_plan(env)
    # A2's catalogue before the deals, so a quotation raised below can see the
    # taxes and price lists it seeds.
    seed_catalog(env)
    _ensure_free_stock(env)
    orders = _ensure_demo_deals(env)
    _route_one_approval(env, orders)
    # Give the deal-health engine its first real pass, so DF-017's screen is
    # populated from the cron's own code path rather than left blank.
    env["sale.order"].search([("state", "in", ("draft", "sent", "sale"))])._compute_deal_health()
    return orders
