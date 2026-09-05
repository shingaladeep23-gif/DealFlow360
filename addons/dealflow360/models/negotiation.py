from odoo import _, fields, models
from odoo.exceptions import UserError


class DealflowNegotiation(models.Model):
    _name = "dealflow.negotiation"
    _inherit = ["mail.thread"]
    _description = "Portal negotiation thread for a quotation (DF-014)"
    _order = "create_date desc"

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
            ("proposed", "Counter-Discount Proposed"),
            ("applied", "Applied - No Reapproval Needed"),
            ("requires_reapproval", "Applied - Requires Reapproval"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        required=True,
        default="proposed",
        tracking=True,
    )
    counter_discount = fields.Float(
        string="Proposed Discount (%)",
        required=True,
        help="Flat discount percentage the customer proposes, applied "
        "uniformly to every discountable line on the order.",
    )
    risk_level_before = fields.Selection(
        [("none", "None"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level Before",
    )
    risk_level_after = fields.Selection(
        [("none", "None"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level After",
    )
    applied_by_id = fields.Many2one("res.users", string="Applied By")

    def _apply(self):
        """Rewrite every discountable line's discount to the proposed value
        and let sale.order.line/sale.order's own compute methods (Atlas's
        risk engine, DF-002/DF-003) recompute ceilings, excess and blended
        risk - this never reimplements that math."""
        self.ensure_one()
        order = self.order_id
        risk_before = order.df_risk_level
        lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if not lines:
            raise UserError(_("This quotation has no lines to discount."))
        lines.write({"discount": self.counter_discount})
        risk_after = order.df_risk_level
        new_state = "requires_reapproval" if risk_after in ("medium", "high") else "applied"
        self.write(
            {
                "state": new_state,
                "risk_level_before": risk_before,
                "risk_level_after": risk_after,
                "applied_by_id": self.env.user.id,
            }
        )
        order.message_post(
            body=_(
                "Customer proposed a %(pct).2f%% counter-discount via the portal. "
                "Risk moved %(before)s -> %(after)s.%(reapproval)s"
            )
            % {
                "pct": self.counter_discount,
                "before": risk_before,
                "after": risk_after,
                "reapproval": _(
                    " This exceeds the approval threshold and requires manager "
                    "reapproval before it can be confirmed."
                )
                if new_state == "requires_reapproval"
                else "",
            }
        )
        return new_state
