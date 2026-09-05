from odoo import fields, models


class DealflowAuditLog(models.Model):
    _name = "dealflow.audit.log"
    _description = "DealFlow360 Audit Log"
    _order = "timestamp desc, id desc"

    order_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, ondelete="cascade", index=True
    )
    user_id = fields.Many2one("res.users", string="User", required=True)
    timestamp = fields.Datetime(string="Timestamp", required=True)
    action = fields.Selection(
        [
            ("submitted", "Submitted for Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revision_requested", "Revision Requested"),
            ("reapproval", "Reapproval Triggered"),
        ],
        string="Action",
        required=True,
    )
    detail = fields.Text(string="Detail")

    def _log(self, order, action, detail):
        """Immutable append-only audit row. Always written via sudo() so a
        Sales Rep/Manager/Finance user acting on their own step can still
        write the log entry even though only Admin has create rights on
        this model per ir.model.access.csv - the log itself is never
        editable or deletable by anyone once written."""
        return self.sudo().create(
            {
                "order_id": order.id,
                "user_id": self.env.user.id,
                "timestamp": fields.Datetime.now(),
                "action": action,
                "detail": detail,
            }
        )
