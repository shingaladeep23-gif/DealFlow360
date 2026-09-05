"""Hybrid one-time + recurring billing (DF-012).

DEC-004: no sale_subscription dependency (Enterprise-only, unavailable on
Odoo 17 Community) - recurring behaviour is native dealflow.recurring.plan +
dealflow.billing.schedule generating REAL account.move invoices.
DEC-008: one recurring sale.order.line IS one subscription - lifecycle
fields live on the line itself (df_sub_*), never on a new aggregate model.

Every subscription-lifecycle / product-link field here is added by
extending sale.order.line / product.template from THIS file, never by
editing sale_order_line.py or product.py directly, since those files sit
in Atlas's lane (see docs/task_plan.md DF-010/DF-012 dispatch). Odoo merges
multiple `_inherit` classes for the same model across files in the
addon's models/__init__.py import order - this is the standard way large
addons split one model's logic without two agents fighting over one file.
"""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Approximate day-length of one billing cycle, used only to compute a
# proration FRACTION (remaining days / cycle length) - not for scheduling
# the next bill date, which uses calendar-correct relativedelta below.
DAYS_PER_INTERVAL = {"monthly": 30, "quarterly": 91, "yearly": 365}
MONTHS_PER_INTERVAL = {"monthly": 1.0, "quarterly": 3.0, "yearly": 12.0}


def _add_interval(date, interval):
    if interval == "monthly":
        return date + relativedelta(months=1)
    if interval == "quarterly":
        return date + relativedelta(months=3)
    return date + relativedelta(years=1)


class DealflowRecurringPlan(models.Model):
    _name = "dealflow.recurring.plan"
    _description = "Recurring billing plan (DF-012)"
    _order = "name"

    name = fields.Char(required=True)
    interval = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        required=True,
        default="monthly",
    )
    proration = fields.Boolean(
        string="Prorate Mid-Cycle Changes",
        default=True,
        help="When set, a quantity change to an active subscription line "
        "between bill dates produces an immediate prorated billing-schedule "
        "entry for the remainder of the current cycle, instead of only "
        "showing up correctly at the next full-cycle invoice.",
    )
    cancel_rule = fields.Selection(
        [
            ("no_refund", "No Refund - Stop Future Billing Only"),
            ("prorate_refund", "Credit Note for Unused Period"),
        ],
        required=True,
        default="prorate_refund",
        help="What happens to the current, already-invoiced period when a "
        "subscription line on this plan is cancelled mid-cycle.",
    )
    active = fields.Boolean(default=True)


class ProductTemplateRecurringPlan(models.Model):
    _inherit = "product.template"

    df_recurring_plan_id = fields.Many2one(
        "dealflow.recurring.plan",
        string="Recurring Plan",
        help="Billing plan governing this product's recurring lines. Only "
        "meaningful when df_is_recurring is set (DEC-004/DF-012); omitted "
        "from DF-001 until this model existed.",
    )


class SaleOrderRecurringBilling(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()
        # ONLY orders that actually confirmed. Three overrides of
        # action_confirm() stack on sale.order (models/sale_order.py, then
        # warehouse_split.py, then this one, in models/__init__.py import
        # order). The governance override in sale_order.py confirms only the
        # subset that passed its checks and leaves an over-ceiling quotation
        # in 'draft', routed for approval - but this loop used to run over
        # ALL of `self` regardless. Reproduced live: a draft quotation blocked
        # pending manager AND finance approval had its subscription activated
        # and a billing schedule written, and the daily cron then posted a real
        # 999.00 customer invoice against it. `res` is not usable as the
        # filter here - it is a notification action when anything was routed.
        for order in self.filtered(lambda o: o.state in ("sale", "done")):
            recurring_lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id.df_is_recurring
            )
            recurring_lines._df_start_subscription()
        return res

    df_billing_schedule_ids = fields.One2many(
        "dealflow.billing.schedule", "order_id", string="Billing Schedule"
    )
    df_one_time_line_ids = fields.One2many(
        "sale.order.line",
        compute="_compute_df_line_split",
        string="One-time lines",
    )
    df_recurring_line_ids = fields.One2many(
        "sale.order.line",
        compute="_compute_df_line_split",
        string="Recurring lines",
    )

    @api.depends("order_line.product_id.df_is_recurring", "order_line.display_type")
    def _compute_df_line_split(self):
        # DF-012/B7 asks for one-time and recurring lines shown SEPARATELY
        # within the same order. A view cannot filter a one2many by a related
        # field, so the split is computed here rather than faked with two
        # identical tables.
        for order in self:
            lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id
            )
            recurring = lines.filtered(lambda l: l.product_id.df_is_recurring)
            order.df_recurring_line_ids = recurring
            order.df_one_time_line_ids = lines - recurring

    def _get_invoiceable_lines(self, final=False):
        """A recurring line is billed by its dealflow.billing.schedule, on its
        own cycle - never by the order's native Create Invoice button.

        Without this the two billing paths overlap and the customer is charged
        twice for the same subscription: the schedule raises the cycle's
        invoice, and the order still reports the line as waiting to be
        invoiced, so pressing Create Invoice bills it again. One-time lines on
        the same order are untouched, which is the whole point of DF-012's
        hybrid order.
        """
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: not l.product_id.df_is_recurring)


class SaleOrderLineSubscription(models.Model):
    _inherit = "sale.order.line"

    df_sub_state = fields.Selection(
        [
            ("active", "Active"),
            ("paused", "Paused"),
            ("cancelled", "Cancelled"),
        ],
        string="Subscription State",
        help="DEC-008: lifecycle state of the ONE subscription this "
        "recurring line represents. Empty for non-recurring lines.",
    )
    df_sub_start_date = fields.Date(string="Subscription Start")
    df_sub_next_bill_date = fields.Date(string="Next Bill Date")
    df_sub_end_date = fields.Date(string="Subscription End")
    df_mrr = fields.Monetary(
        string="MRR",
        compute="_compute_df_mrr",
        store=True,
        currency_field="currency_id",
        help="Monthly recurring revenue contributed by this line: its "
        "billing amount normalized to a 30-day month via the plan's "
        "interval. Zero for non-recurring, paused or cancelled lines.",
    )
    billing_schedule_ids = fields.One2many(
        "dealflow.billing.schedule", "order_line_id", string="Billing Schedule"
    )

    @api.depends(
        "price_subtotal",
        "df_sub_state",
        "product_id.df_is_recurring",
        "product_id.df_recurring_plan_id.interval",
    )
    def _compute_df_mrr(self):
        for line in self:
            plan = line.product_id.df_recurring_plan_id
            if (
                line.df_sub_state == "active"
                and line.product_id.df_is_recurring
                and plan
            ):
                line.df_mrr = line.price_subtotal / MONTHS_PER_INTERVAL.get(
                    plan.interval, 1.0
                )
            else:
                line.df_mrr = 0.0

    def _df_start_subscription(self):
        """Activate lifecycle state + write the first billing schedule
        entry for a newly confirmed recurring line. Idempotent - a line
        that already carries schedule rows is left untouched, so calling
        this again on an already-started order is harmless."""
        # sudo(): schedule rows are produced by the billing engine when an
        # order is confirmed. Only Finance/Admin may create them by hand (see
        # ir.model.access.csv), but a Sales Rep or Manager confirming an order
        # that happens to contain a recurring line must not hit an AccessError.
        Schedule = self.env["dealflow.billing.schedule"].sudo()
        today = fields.Date.context_today(self)
        for line in self:
            if not line.product_id.df_is_recurring or line.billing_schedule_ids:
                continue
            if line.order_id.state not in ("sale", "done"):
                # A subscription starts when its order is CONFIRMED. Callers
                # already filter for that; this is the second lock, because
                # the cost of getting it wrong is billing a customer for a
                # quotation nobody accepted.
                continue
            line.write(
                {
                    "df_sub_state": "active",
                    "df_sub_start_date": today,
                    "df_sub_next_bill_date": today,
                }
            )
            Schedule.create(
                {
                    "order_id": line.order_id.id,
                    "order_line_id": line.id,
                    "date": today,
                    "amount": line.price_subtotal,
                    "state": "pending",
                }
            )

    def _df_schedule_next_bill(self, from_date):
        """Called after a regular (non-proration) schedule entry invoices,
        to queue the following cycle's entry."""
        self.ensure_one()
        plan = self.product_id.df_recurring_plan_id
        if not plan or self.df_sub_state != "active":
            return
        next_date = _add_interval(from_date, plan.interval)
        self.df_sub_next_bill_date = next_date
        self.env["dealflow.billing.schedule"].sudo().create(
            {
                "order_id": self.order_id.id,
                "order_line_id": self.id,
                "date": next_date,
                "amount": self.price_subtotal,
                "state": "pending",
            }
        )

    def _df_prorate_quantity_change(self, old_qty, new_qty):
        """AT-07: a mid-cycle quantity change produces correct proration.
        Bills (or credits) only the remaining fraction of the current
        cycle for the quantity delta, as an immediate extra schedule entry
        - the next full-cycle invoice already reflects the new quantity via
        price_subtotal, so this never double-bills the delta."""
        self.ensure_one()
        plan = self.product_id.df_recurring_plan_id
        if (
            not plan
            or not plan.proration
            or not self.df_sub_next_bill_date
            or self.df_sub_state != "active"
        ):
            return
        today = fields.Date.context_today(self)
        next_bill = self.df_sub_next_bill_date
        if today >= next_bill:
            return  # the next invoice will already reflect the new quantity
        cycle_days = DAYS_PER_INTERVAL.get(plan.interval, 30)
        remaining_days = (next_bill - today).days
        remaining_fraction = min(1.0, max(0.0, remaining_days / float(cycle_days)))
        unit_price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        delta_amount = unit_price * (new_qty - old_qty) * remaining_fraction
        if abs(delta_amount) < 0.005:
            return
        self.env["dealflow.billing.schedule"].sudo().create(
            {
                "order_id": self.order_id.id,
                "order_line_id": self.id,
                "date": today,
                "amount": delta_amount,
                "state": "pending",
                "df_is_proration": True,
            }
        )
        self.order_id.message_post(
            body=_(
                "Mid-cycle quantity change on %(product)s (%(old)s -> "
                "%(new)s): prorated %(amount).2f for the remaining "
                "%(days)d day(s) of the current cycle."
            )
            % {
                "product": self.product_id.display_name,
                "old": old_qty,
                "new": new_qty,
                "amount": delta_amount,
                "days": remaining_days,
            }
        )

    def write(self, vals):
        old_qty = {}
        if "product_uom_qty" in vals:
            old_qty = {
                line.id: line.product_uom_qty
                for line in self
                if line.df_sub_state == "active"
            }
        res = super().write(vals)
        for line in self:
            if line.id in old_qty and line.product_uom_qty != old_qty[line.id]:
                line._df_prorate_quantity_change(
                    old_qty[line.id], line.product_uom_qty
                )
        return res

    def action_pause_subscription(self):
        """Stop billing without ending the subscription. 'paused' has been a
        selection value and a filter card on the Subscriptions screen since
        DF-012, but nothing could ever set it - the count was permanently
        zero. Pending schedule entries are cancelled by _df_process_due_entry
        while paused, and resuming queues the next cycle again."""
        for line in self:
            if not line.product_id.df_is_recurring or line.df_sub_state != "active":
                continue
            line.df_sub_state = "paused"
            line.order_id.message_post(
                body=_("Subscription for %s paused.") % line.product_id.display_name
            )
        return True

    def action_resume_subscription(self):
        for line in self:
            if line.df_sub_state != "paused":
                continue
            line.df_sub_state = "active"
            if not line.billing_schedule_ids.filtered(
                lambda s: s.state == "pending"
            ):
                line._df_schedule_next_bill(fields.Date.context_today(line))
            line.order_id.message_post(
                body=_("Subscription for %s resumed.") % line.product_id.display_name
            )
        return True

    def action_cancel_subscription(self):
        """Cancel future billing for a recurring line per its plan's
        cancel_rule; on prorate_refund, credits the unused remainder of
        the most recently invoiced period (AT-07)."""
        for line in self:
            if not line.product_id.df_is_recurring or line.df_sub_state == "cancelled":
                continue
            plan = line.product_id.df_recurring_plan_id
            today = fields.Date.context_today(self)
            line.billing_schedule_ids.filtered(
                lambda s: s.state == "pending"
            ).write({"state": "cancelled"})
            if plan and plan.cancel_rule == "prorate_refund":
                last_invoiced = line.billing_schedule_ids.filtered(
                    lambda s: s.state == "invoiced"
                    and not s.df_is_proration
                    and s.invoice_id
                    and s.invoice_id.state == "posted"
                ).sorted("date", reverse=True)[:1]
                if last_invoiced:
                    last_invoiced._create_proration_credit_note(today)
            line.write({"df_sub_state": "cancelled", "df_sub_end_date": today})
            line.order_id.message_post(
                body=_("Subscription for %s cancelled.") % line.product_id.display_name
            )
        return True


class DealflowBillingSchedule(models.Model):
    _name = "dealflow.billing.schedule"
    _description = (
        "One scheduled recurring billing event, materializing as a real "
        "account.move invoice (DF-012)"
    )
    _order = "date"

    order_id = fields.Many2one(
        "sale.order", required=True, ondelete="cascade", index=True
    )
    order_line_id = fields.Many2one(
        "sale.order.line", required=True, ondelete="cascade", index=True
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id", string="Customer", store=True
    )
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    date = fields.Date(required=True, index=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("invoiced", "Invoiced"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="pending",
    )
    invoice_id = fields.Many2one("account.move", string="Invoice", readonly=True)
    df_is_proration = fields.Boolean(
        string="Is Proration",
        help="True for an extra entry raised by a mid-cycle quantity "
        "change rather than a regular full-cycle bill.",
    )

    def action_invoice_now(self):
        """Manually force a pending entry to invoice immediately, ahead of
        the daily cron - used by the 'Generate Invoice Now' button and by
        tests. Goes through the SAME entry point as the cron: this used to
        call _create_invoice() directly and skip _df_schedule_next_bill(),
        so a subscription invoiced from the UI silently stopped renewing -
        no following cycle was ever queued and df_sub_next_bill_date never
        advanced, while the identical action run by the cron renewed
        correctly."""
        for schedule in self.filtered(lambda s: s.state == "pending"):
            schedule._df_process_due_entry()
        return True

    def _df_process_due_entry(self):
        """Invoice one pending entry and queue the cycle that follows it.

        Single source of truth for what "billing an entry" means, shared by
        the daily cron and the manual button. A line paused or cancelled
        after its entry was queued is cancelled rather than invoiced; a
        proration entry is one-off and never queues a successor."""
        self.ensure_one()
        line = self.order_line_id
        if self.order_id.state not in ("sale", "done"):
            # Left PENDING on purpose, not cancelled: an order sitting in an
            # approval queue may well be approved tomorrow, and its schedule
            # should then bill normally. What must never happen is invoicing
            # it in the meantime.
            return False
        if line.df_sub_state != "active":
            self.write({"state": "cancelled"})
            return False
        self._create_invoice()
        if not self.df_is_proration:
            line._df_schedule_next_bill(self.date)
        return True

    def _create_invoice(self):
        self.ensure_one()
        line = self.order_line_id
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.order_id.partner_id.id,
                "invoice_origin": self.order_id.name,
                "invoice_date": self.date,
                "currency_id": self.currency_id.id,
                # Explicit, so the journal is resolved against the ORDER's
                # company rather than whatever env the cron happens to run in.
                "company_id": self.order_id.company_id.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": line.product_id.id,
                            "name": _("%(product)s - %(plan)s (%(date)s)")
                            % {
                                "product": line.product_id.display_name,
                                "plan": line.product_id.df_recurring_plan_id.name
                                or "",
                                "date": self.date,
                            },
                            "quantity": 1,
                            "product_uom_id": line.product_uom.id,
                            "price_unit": self.amount,
                            "tax_ids": [(6, 0, line.tax_id.ids)],
                            # sale.order.invoice_ids is derived from
                            # order_line.invoice_lines.move_id, so without
                            # this link every subscription invoice was
                            # orphaned from the order that generated it:
                            # invisible on the Invoices smart button, and
                            # invoice_status stuck at 'no' forever. The quick
                            # test's "record a payment and check the invoice
                            # status updates" could not pass for a
                            # subscription. See _compute_invoice_status below
                            # for what this link must NOT be allowed to imply.
                            "sale_line_ids": [(6, 0, [line.id])],
                        },
                    )
                ],
            }
        )
        move.action_post()
        self.write({"state": "invoiced", "invoice_id": move.id})
        return move

    def _create_proration_credit_note(self, today):
        """cancel_rule=prorate_refund: credit the unused remainder of this
        (already invoiced, posted) period."""
        self.ensure_one()
        if not self.invoice_id or self.invoice_id.state != "posted":
            return False
        plan = self.order_line_id.product_id.df_recurring_plan_id
        cycle_days = DAYS_PER_INTERVAL.get(plan.interval if plan else "monthly", 30)
        elapsed = (today - self.date).days if self.date else cycle_days
        unused_fraction = min(1.0, max(0.0, (cycle_days - elapsed) / float(cycle_days)))
        if unused_fraction <= 0:
            return False
        credit_amount = self.amount * unused_fraction
        if credit_amount < 0.005:
            return False
        credit_note = self.invoice_id._reverse_moves(
            default_values_list=[
                {
                    "invoice_date": today,
                    "ref": _(
                        "Prorated credit - subscription cancelled mid-cycle"
                    ),
                }
            ],
            cancel=False,
        )
        # A straight reversal credits the FULL invoiced amount; scale every
        # line down to the unused fraction so the credit matches the unused
        # remainder of the cycle, not the whole period.
        if unused_fraction < 1.0:
            for cline in credit_note.invoice_line_ids:
                cline.quantity = cline.quantity * unused_fraction
        credit_note.action_post()
        self.order_id.message_post(
            body=_(
                "Credit note %(name)s issued for the unused portion of the "
                "current billing cycle."
            )
            % {"name": credit_note.display_name}
        )
        return credit_note

    @api.model
    def _cron_generate_recurring_invoices(self):
        """Daily cron: invoice every pending entry whose date has arrived,
        for lines still active, and queue the following cycle's entry.
        A line paused/cancelled after its schedule was created has that
        entry cancelled instead of invoiced."""
        today = fields.Date.context_today(self)
        due = self.search([("state", "=", "pending"), ("date", "<=", today)])
        for schedule in due:
            schedule._df_process_due_entry()
