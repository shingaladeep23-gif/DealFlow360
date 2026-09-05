"""Back-fill the approval-binding fields introduced in 17.0.1.4.0.

An approval is now a decision about a SPECIFIC set of lines, discounts and
customer tier, recorded as sale.order.df_governance_fingerprint and snapshotted
onto dealflow.approval.order_fingerprint (see the comments on both fields).

Odoo computes a newly added stored field for existing rows when it creates the
column, so df_governance_fingerprint arrives populated. dealflow.approval.
order_fingerprint is a PLAIN column though - every chain that predates this
version has it empty, and an empty fingerprint can never match its order. That
would supersede every live approval on the database the moment anyone touched
its quotation, and _df_covers() would refuse to confirm even a fully approved
one. So back-fill each existing chain from the order as it stands today: an
approval granted before this feature existed is grandfathered against the
current content rather than retroactively invalidated.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Defensive: the column is normally computed at creation time, but an
    # interrupted upgrade can leave rows empty, and a NULL fingerprint would
    # quietly disable the whole binding check.
    orders = env["sale.order"].search([("df_governance_fingerprint", "=", False)])
    if orders:
        env.add_to_compute(orders._fields["df_governance_fingerprint"], orders)
        orders.flush_recordset(["df_governance_fingerprint"])

    approvals = env["dealflow.approval"].search(
        [("order_fingerprint", "=", False)]
    )
    for approval in approvals:
        approval.order_fingerprint = approval.order_id.df_governance_fingerprint
