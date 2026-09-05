from odoo import _, api, fields, models
from odoo.exceptions import UserError

ROLE_GROUP_XMLID = {
    "sales_manager": "dealflow360.group_dealflow_sales_manager",
    "finance": "dealflow360.group_dealflow_finance",
}


class DealflowApproval(models.Model):
    _name = "dealflow.approval"
    _description = "DealFlow360 Discount Approval Chain (DEC-003/DEC-010)"
    _order = "create_date desc"

    order_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, ondelete="cascade", index=True
    )
    risk_score = fields.Float(
        string="Risk Score",
        readonly=True,
        help="Snapshot of df_blended_risk_score at the moment this approval "
        "chain was created - the routing decision, not a live value.",
    )
    risk_level = fields.Selection(
        [("medium", "Medium"), ("high", "High")],
        string="Risk Level",
        readonly=True,
        help="Snapshot of df_risk_level at creation. NONE never reaches this "
        "model - DEC-003's NONE case is auto-approved and never routed.",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revision", "Revision Requested"),
        ],
        string="Status",
        default="pending",
        readonly=True,
    )
    step_ids = fields.One2many("dealflow.approval.step", "approval_id", string="Steps")
    current_step_id = fields.Many2one(
        "dealflow.approval.step",
        string="Current Step",
        compute="_compute_current_step_id",
        help="The single actionable (state=pending) step, if any.",
    )

    @api.depends("step_ids.state")
    def _compute_current_step_id(self):
        for approval in self:
            approval.current_step_id = approval.step_ids.filtered(
                lambda s: s.state == "pending"
            )[:1]

    @api.model
    def _create_for_order(self, order):
        """DEC-003/DEC-010 routing: MEDIUM -> Sales Manager only; HIGH ->
        Sales Manager then Finance (Finance only becomes actionable once the
        manager approves, AT-04). Caller must already have confirmed
        order.df_risk_level is 'medium' or 'high' - NONE is never routed.
        """
        if order.df_risk_level not in ("medium", "high"):
            raise UserError(_("Only a MEDIUM or HIGH risk quotation can be routed for approval."))
        roles = (
            ["sales_manager"]
            if order.df_risk_level == "medium"
            else ["sales_manager", "finance"]
        )
        approval = self.create(
            {
                "order_id": order.id,
                "risk_score": order.df_blended_risk_score,
                "risk_level": order.df_risk_level,
                "step_ids": [
                    (
                        0,
                        0,
                        {
                            "role": role,
                            "sequence": (index + 1) * 10,
                            "state": "pending" if index == 0 else "waiting",
                        },
                    )
                    for index, role in enumerate(roles)
                ],
            }
        )
        self.env["dealflow.audit.log"]._log(
            order,
            "submitted",
            _("Routed for approval (%(level)s risk, score %(score).1f): %(reason)s")
            % {
                "level": order.df_risk_level,
                "score": order.df_blended_risk_score,
                "reason": order.df_risk_summary or "",
            },
        )
        return approval

    def _advance(self):
        """Called after a step is approved: activate the next waiting step,
        or close the chain out as fully approved."""
        self.ensure_one()
        remaining = self.step_ids.filtered(lambda s: s.state == "waiting").sorted("sequence")
        if remaining:
            remaining[0].state = "pending"
        else:
            self.state = "approved"

    def _reject(self):
        self.ensure_one()
        self.state = "rejected"

    def _request_revision(self):
        self.ensure_one()
        self.state = "revision"


class DealflowApprovalStep(models.Model):
    _name = "dealflow.approval.step"
    _description = "DealFlow360 Approval Step"
    _order = "sequence"

    approval_id = fields.Many2one(
        "dealflow.approval", string="Approval", required=True, ondelete="cascade", index=True
    )
    order_id = fields.Many2one(
        related="approval_id.order_id", string="Quotation", store=True, readonly=True
    )
    role = fields.Selection(
        [("sales_manager", "Sales Manager"), ("finance", "Finance")],
        string="Approver Role",
        required=True,
    )
    sequence = fields.Integer(default=10)
    approver_id = fields.Many2one("res.users", string="Acted By", readonly=True)
    state = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revision", "Revision Requested"),
        ],
        default="waiting",
        readonly=True,
    )
    reason = fields.Text(string="Reason")
    acted_on = fields.Datetime(string="Acted On", readonly=True)

    def _role_label(self):
        return dict(self._fields["role"].selection)[self.role]

    def _check_actionable(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("This approval step is not currently actionable."))
        if not self.env.user.has_group(ROLE_GROUP_XMLID[self.role]):
            raise UserError(
                _("Only a %s may act on this approval step.") % self._role_label()
            )

    def action_approve(self, reason=False):
        self.ensure_one()
        self._check_actionable()
        self.write(
            {
                "state": "approved",
                "approver_id": self.env.user.id,
                "acted_on": fields.Datetime.now(),
                "reason": reason or False,
            }
        )
        self.env["dealflow.audit.log"]._log(
            self.order_id,
            "approved",
            _("%(user)s approved as %(role)s%(reason)s")
            % {
                "user": self.env.user.name,
                "role": self._role_label(),
                "reason": (": %s" % reason) if reason else "",
            },
        )
        self.approval_id._advance()
        return True

    def action_reject(self, reason):
        self.ensure_one()
        self._check_actionable()
        if not reason:
            raise UserError(_("A reason is required to reject an approval."))
        self.write(
            {
                "state": "rejected",
                "approver_id": self.env.user.id,
                "acted_on": fields.Datetime.now(),
                "reason": reason,
            }
        )
        self.env["dealflow.audit.log"]._log(
            self.order_id,
            "rejected",
            _("%(user)s rejected as %(role)s: %(reason)s")
            % {"user": self.env.user.name, "role": self._role_label(), "reason": reason},
        )
        self.approval_id._reject()
        return True

    def action_request_revision(self, reason):
        self.ensure_one()
        self._check_actionable()
        if not reason:
            raise UserError(_("A reason is required to request a revision."))
        self.write(
            {
                "state": "revision",
                "approver_id": self.env.user.id,
                "acted_on": fields.Datetime.now(),
                "reason": reason,
            }
        )
        self.env["dealflow.audit.log"]._log(
            self.order_id,
            "revision_requested",
            _("%(user)s requested revision as %(role)s: %(reason)s")
            % {"user": self.env.user.name, "role": self._role_label(), "reason": reason},
        )
        self.approval_id._request_revision()
        return True
