"""Repair what 17.0.1.6.0 could not, and backfill the billing drift.

1. Pending billing-schedule entries that had ALREADY drifted away from their
   order line before the re-sync existed. 17.0.1.6.0 stopped new drift, but a
   schedule only re-prices when its line is written, so an entry that went
   stale months ago stayed stale and the cron would still invoice the old
   figure. Found in the live database: S00183 queued to bill 300.00 for a line
   worth 1,200.00 - a 900.00 under-bill per cycle, sitting there waiting.

   Only PENDING, non-proration entries are touched. An invoiced entry is
   billing history and is never rewritten; a proration is a one-off settlement
   of a past delta, not a cycle.

2. The Home Action, which 17.0.1.6.0 wrote as a "model,id" reference string.
   res.users.action_id is a plain Many2one to ir.actions.actions, so that
   silently did nothing and everyone still landed on Discuss. Re-running the
   seed fixes it, and also archives the QA scratch products found alongside.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.dealflow360.demo.demo_runtime import seed_runtime_demo


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    seed_runtime_demo(env)

    schedules = env["dealflow.billing.schedule"].search(
        [("state", "=", "pending"), ("df_is_proration", "=", False)]
    )
    for schedule in schedules:
        line = schedule.order_line_id
        if line and abs(schedule.amount - line.price_subtotal) >= 0.005:
            schedule.amount = line.price_subtotal
