"""Bring an already-installed database up to 17.0.1.6.0.

Three things need doing that Odoo will not do on its own:

1. The runtime seed is re-run. It is idempotent, and it now also names and
   badges the company, retires the personal accounts left in the shared
   database by hand, seeds A2's catalogue (variants, taxes, descriptions,
   price lists, a second currency) and tops free stock back up.

2. df_estimated_cost is an EXISTING stored compute whose formula changed - it
   used to echo the warehouse's dimensionless tie-break weight and is now a
   real money figure that scales with quantity. Odoo only recomputes a stored
   field when its column is created or a dependency actually changes, so
   without this every existing allocation row keeps showing the old 1.00.
   (df_estimated_shipping_cost is new, so its column creation computes it.)

3. Existing quotations are re-scored, because the risk fields are stored
   computes and nothing else will touch them.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.dealflow360.demo.demo_runtime import seed_runtime_demo


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    seed_runtime_demo(env)

    lines = env["dealflow.warehouse.split.line"].search([])
    if lines:
        env.add_to_compute(lines._fields["df_estimated_cost"], lines)
        lines.flush_recordset(["df_estimated_cost"])

    splits = env["dealflow.warehouse.split"].search([])
    if splits:
        env.add_to_compute(
            splits._fields["df_estimated_shipping_cost"], splits
        )
        splits.flush_recordset(["df_estimated_shipping_cost"])

    # Deal health had only ever scored the handful of orders that existed when
    # the DF-017 cron last ran - live-found at 10 of 37. Give every open deal
    # a real pass through the same code path the cron uses.
    open_orders = env["sale.order"].search(
        [("state", "in", ("draft", "sent", "sale"))]
    )
    if open_orders:
        open_orders._compute_deal_health()

    # The health cron itself is noupdate="1", so an existing database keeps the
    # six-hour interval the XML no longer says. That interval IS the window in
    # which a new deal shows no score at all, so bring it down here too.
    health_cron = env.ref(
        "dealflow360.ir_cron_compute_deal_health", raise_if_not_found=False
    )
    if health_cron and health_cron.interval_type == "hours":
        health_cron.interval_number = 1
