"""Recompute the stored fields whose compute methods changed in 17.0.1.3.0.

Odoo only recomputes a stored computed field when its COLUMN is created or one
of its dependencies actually changes on a record. Changing the body of the
compute leaves every existing row holding the value the old code produced, so
without this an upgraded database keeps serving stale text and stages forever:

- df_risk_summary is displayed verbatim on the quotation and approval screens.
  Its wording was rewritten for salespeople, so existing rows would otherwise
  still read "... exceeds its 15.0% discount ceiling by 10.0 points (blended
  risk score 90.0)".
- df_pipeline_stage gained an "In negotiation" branch (it now depends on
  df_negotiation_ids). Existing negotiated-but-unconfirmed orders would stay
  parked in Draft on the Kanban board.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([])
    if not orders:
        return
    env.add_to_compute(orders._fields["df_risk_summary"], orders)
    env.add_to_compute(orders._fields["df_pipeline_stage"], orders)
    orders.flush_recordset(["df_risk_summary", "df_pipeline_stage"])
