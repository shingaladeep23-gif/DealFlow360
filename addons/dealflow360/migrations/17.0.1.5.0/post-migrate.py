"""Recompute the governance ceilings changed in 17.0.1.5.0.

An unset tier or category ceiling used to read as a hard 0% limit, because both
fields default to 0.0 and the effective ceiling was min() of the two. That made
every line whose customer had no tier - or whose product sat in Odoo's stock
"All"/"Saleable" categories - permanently over its limit, so ordinary
quotations were routed for approval on a 2% discount.

_compute_df_governance now treats 0 as UNSET and falls back to the
dealflow.default_max_discount parameter. Odoo only recomputes a stored computed
field when its column is created or a dependency actually changes, so without
this every existing line keeps the ceiling and excess the old formula produced,
and the order-level risk score derived from them stays wrong too.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    lines = env["sale.order.line"].search([("product_id", "!=", False)])
    if lines:
        for fname in ("df_effective_ceiling", "df_excess_points"):
            env.add_to_compute(lines._fields[fname], lines)
        lines.flush_recordset(["df_effective_ceiling", "df_excess_points"])

    # The order-level score/level/summary are derived from the line values
    # above, so they have to follow - a stale df_risk_level is what decides
    # whether a quotation needs approval at all.
    orders = env["sale.order"].search([])
    if orders:
        for fname in (
            "df_blended_risk_score",
            "df_risk_level",
            "df_risk_summary",
        ):
            env.add_to_compute(orders._fields[fname], orders)
        orders.flush_recordset(
            ["df_blended_risk_score", "df_risk_level", "df_risk_summary"]
        )
