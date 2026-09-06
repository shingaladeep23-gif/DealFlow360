"""Customer portal negotiation (DF-014).

A counter-discount is a REQUEST. It is recorded when the customer submits it
and changes nothing until someone on the sales side accepts it.

That is not how this started. controllers/portal.py used to call _apply()
inline, so submitting the form rewrote the order's prices there and then, with
nobody in the loop. Reproduced live: a portal user gave themselves 15% and
confirmed their own order. The problem statement's roles (§3) say the customer
"requests changes ... or counters a discount" and the rep "responds to customer
negotiation requests" - before this there was no responder, no accept, no
reject, and no internal screen; 'proposed' and 'rejected' were unreachable
states that the portal nonetheless rendered labels for.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DealflowNegotiation(models.Model):
    _name = "dealflow.negotiation"
    _inherit = ["mail.thread"]
    _description = "Portal negotiation thread for a quotation (DF-014)"
    _order = "create_date desc"
    # Same defect as dealflow.approval and dealflow.warehouse.split: with no
    # name field the label falls back to "dealflow.negotiation,7", which is
    # what a breadcrumb and any many2one to this record would have shown.
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("order_id.name", "counter_discount")
    def _compute_display_name(self):
        for negotiation in self:
            negotiation.display_name = _(
                "%(order)s - customer asked for %(pct).2f%%"
            ) % {
                "order": negotiation.order_id.name or _("Quotation"),
                "pct": negotiation.counter_discount or 0.0,
            }

    order_id = fields.Many2one(
        "sale.order",
        string="Quotation",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id", string="Customer", store=True
    )
    state = fields.Selection(
        [
            ("proposed", "Awaiting your response"),
            ("applied", "Accepted"),
            ("requires_reapproval", "Accepted - needs reapproval"),
            ("rejected", "Declined"),
        ],
        string="Status",
        required=True,
        default="proposed",
        tracking=True,
    )
    counter_discount = fields.Float(
        string="Proposed Discount (%)",
        required=True,
        help="Discount percentage the customer is asking for. On acceptance "
        "it is applied to every line that is not already discounted at least "
        "that deeply - see _apply().",
    )
    currency_id = fields.Many2one(related="order_id.currency_id", store=True)
    amount_before = fields.Monetary(
        string="Current Total",
        related="order_id.amount_total",
        currency_field="currency_id",
        help="What the order is worth right now, so a reviewer can see what "
        "accepting this request would cost without opening the quotation.",
    )
    risk_level_before = fields.Selection(
        [("none", "None"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level Before",
        readonly=True,
    )
    risk_level_after = fields.Selection(
        [("none", "None"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level After",
        readonly=True,
    )
    applied_by_id = fields.Many2one("res.users", string="Responded By", readonly=True)
    responded_on = fields.Datetime(string="Responded On", readonly=True)
    response_reason = fields.Text(
        string="Response",
        # NOT readonly on the model: the rep types this on the form before
        # pressing Decline, and a readonly field is never sent by the web
        # client, so declining could never record its reason. The form makes
        # it readonly once the request has been answered instead.
        help="What the rep told the customer when declining, shown to them on "
        "the portal. Required on a decline - a customer who asked for a "
        "discount is owed a reason, not a silent 'no'.",
    )

    # -- responding ------------------------------------------------------

    def _check_respondable(self):
        self.ensure_one()
        if self.state != "proposed":
            raise UserError(
                _("This request has already been answered.")
            )
        if self.order_id.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "%s is no longer open for negotiation."
                )
                % self.order_id.name
            )

    def action_accept(self):
        """Apply the customer's counter-discount, then let the governance
        engine decide whether that needs signing off again."""
        for negotiation in self:
            negotiation._check_respondable()
            negotiation._apply()
        return True

    def action_reject(self):
        """Decline without changing a single price. response_reason must
        already be set on the record - the form collects it before the button
        fires, and the check below is what makes that non-optional."""
        for negotiation in self:
            negotiation._check_respondable()
            if not negotiation.response_reason:
                raise UserError(
                    _("Give the customer a reason before declining their request.")
                )
            negotiation.write(
                {
                    "state": "rejected",
                    "applied_by_id": self.env.user.id,
                    "responded_on": fields.Datetime.now(),
                }
            )
            negotiation.order_id.message_post(
                body=_(
                    "Counter-discount of %(pct).2f%% declined by %(user)s: "
                    "%(reason)s"
                )
                % {
                    "pct": negotiation.counter_discount,
                    "user": self.env.user.name,
                    "reason": negotiation.response_reason,
                },
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    def _apply(self):
        """Write the accepted discount onto the order, then let
        sale.order.line/sale.order's own computes (the DF-002/DF-003 risk
        engine) recompute ceilings, excess and blended risk. This never
        reimplements that math.

        max(), not a flat overwrite. The old code wrote counter_discount onto
        EVERY line uniformly, which meant a counter could RAISE the price:
        reproduced live, a rep had given 14% and the customer's 3% counter took
        the total from 1032 up to 1164. A counter-discount is a request for a
        BIGGER discount; it can never reduce one the rep already granted.
        """
        self.ensure_one()
        order = self.order_id
        risk_before = order.df_risk_level
        lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if not lines:
            raise UserError(_("This quotation has no lines to discount."))
        for line in lines:
            if (line.discount or 0.0) < self.counter_discount:
                line.discount = self.counter_discount
        risk_after = order.df_risk_level
        new_state = (
            "requires_reapproval" if risk_after in ("medium", "high") else "applied"
        )
        if new_state == "requires_reapproval":
            # DF-004/AT-09: automatically re-enters the approval flow - a
            # fresh dealflow.approval chain, not a manual request. (Stage 1's
            # fingerprint check has already superseded whatever chain was
            # standing, because the lines just changed.)
            order._df_trigger_reapproval(self)
            self.env["dealflow.audit.log"]._log(
                order,
                "reapproval",
                _(
                    "Accepted the customer's %(pct).2f%% counter-discount, "
                    "which takes the quotation past its limit again - routed "
                    "for approval automatically."
                )
                % {"pct": self.counter_discount},
            )
        self.write(
            {
                "state": new_state,
                "risk_level_before": risk_before,
                "risk_level_after": risk_after,
                "applied_by_id": self.env.user.id,
                "responded_on": fields.Datetime.now(),
            }
        )
        order.message_post(
            body=_(
                "Counter-discount of %(pct).2f%% accepted by %(user)s. "
                "Risk moved %(before)s -> %(after)s.%(reapproval)s"
            )
            % {
                "pct": self.counter_discount,
                "user": self.env.user.name,
                "before": risk_before,
                "after": risk_after,
                "reapproval": _(
                    " This exceeds the approval threshold and requires manager "
                    "reapproval before it can be confirmed."
                )
                if new_state == "requires_reapproval"
                else "",
            },
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        return new_state

    @api.model
    def _open_for_order(self, order):
        """The outstanding request on an order, if any. One at a time: a
        customer cannot stack proposals while the first is unanswered."""
        return self.search(
            [("order_id", "=", order.id), ("state", "=", "proposed")], limit=1
        )
