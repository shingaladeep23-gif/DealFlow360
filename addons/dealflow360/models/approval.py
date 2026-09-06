from odoo import _, api, fields, models
from odoo.exceptions import UserError

ROLE_GROUP_XMLID = {
    "sales_manager": "dealflow360.group_dealflow_sales_manager",
    "finance": "dealflow360.group_dealflow_finance",
}

# Fields that ARE the approval decision. Nobody writes these directly - not a
# Sales Manager, not Finance, not Admin, not dev mode. They are only ever
# written by the action_* / _advance / _reject / _supersede engine methods,
# which announce themselves with the context flag below AFTER checking that
# the acting user really holds the step's role.
#
# Before this, role enforcement lived only inside _check_actionable(), which a
# plain ORM write never reaches. Reproduced live: a Sales Manager wrote
# state='approved' onto FINANCE's step and onto the chain, and the order
# confirmed - the two-tier chain the problem statement asks for collapsed into
# one signature. The ACLs (ir.model.access.csv) now also withhold write and
# create from both approver roles, so this guard is the second layer, not the
# only one.
DECISION_CONTEXT = "dealflow_engine"
GUARDED_APPROVAL_FIELDS = frozenset(
    {"state", "risk_score", "risk_level", "order_fingerprint", "order_id"}
)
GUARDED_STEP_FIELDS = frozenset(
    {"state", "approver_id", "acted_on", "reason", "role", "sequence", "approval_id"}
)


class DealflowApproval(models.Model):
    _name = "dealflow.approval"
    _description = "Discount Approval"
    _order = "create_date desc"
    # A model with no name field falls back to "model,id" for its label, so
    # this record's breadcrumb read "dealflow.approval,15" - a raw technical
    # reference sitting on the core approval screen.
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("order_id.name", "risk_level")
    def _compute_display_name(self):
        levels = dict(self._fields["risk_level"].selection)
        for approval in self:
            if not approval.order_id:
                approval.display_name = _("Approval")
                continue
            level = levels.get(approval.risk_level)
            approval.display_name = (
                _("%(order)s - %(level)s") % {"order": approval.order_id.name, "level": level}
                if level
                else _("Approval for %s") % approval.order_id.name
            )

    order_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, ondelete="cascade", index=True
    )
    risk_score = fields.Float(
        string="Discount Risk",
        readonly=True,
        help="Snapshot of df_blended_risk_score at the moment this approval "
        "chain was created - the routing decision, not a live value.",
    )
    risk_level = fields.Selection(
        [("medium", "Manager approval"), ("high", "Manager + finance")],
        string="Approval Needed",
        readonly=True,
        help="Snapshot of df_risk_level at creation. NONE never reaches this "
        "model - DEC-003's NONE case is auto-approved and never routed.",
    )
    order_fingerprint = fields.Char(
        string="Approved Content",
        readonly=True,
        copy=False,
        help="sale.order.df_governance_fingerprint as it stood when this chain "
        "was routed - i.e. WHAT the approvers were shown. An approval is a "
        "decision about a specific set of lines, discounts and customer tier, "
        "not a permanent licence for the quotation to confirm: if the order "
        "changes afterwards, this no longer matches and the chain is "
        "superseded. Without it a rep could route a 20% deal, edit it to 60% "
        "while it sat in the queue, and have the manager approve the stale "
        "numbers they were shown.",
    )
    state = fields.Selection(
        [
            ("pending", "Awaiting decision"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revision", "Changes requested"),
            ("superseded", "Superseded by an edit"),
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

    def _df_engine(self):
        """The only recordset allowed to write a decision field.

        sudo() because routing and advancing a chain is done BY THE SYSTEM in
        response to a rep's Confirm or an approver's button, not authored by
        that user - and the ACLs deliberately give neither of them write on
        this model. Same reasoning, and same shape, as audit_log._log().
        """
        return self.sudo().with_context(**{DECISION_CONTEXT: True})

    @api.model_create_multi
    def create(self, vals_list):
        # Without this, the write guard below is trivially sidestepped: a
        # Sales Manager with create rights could author a chain that arrives
        # already state='approved', steps already approved, fingerprint copied
        # off the order - and _df_covers() would rightly accept it.
        if not self.env.context.get(DECISION_CONTEXT):
            raise UserError(
                _(
                    "Approval chains are raised automatically when a quotation "
                    "goes past its discount limit. They cannot be created by "
                    "hand."
                )
            )
        return super().create(vals_list)

    def write(self, vals):
        guarded = GUARDED_APPROVAL_FIELDS & set(vals)
        if guarded and not self.env.context.get(DECISION_CONTEXT):
            raise UserError(
                _(
                    "An approval decision can only be recorded with the "
                    "Approve, Reject or Request Revision buttons - it cannot "
                    "be edited directly (attempted: %s)."
                )
                % ", ".join(sorted(guarded))
            )
        return super().write(vals)

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
        # _df_engine(): routing is performed BY THE SYSTEM in response to the
        # rep's Confirm, not authored by the rep. ir.model.access.csv
        # deliberately withholds create on this model from every non-admin
        # role so nobody can hand-craft an approval chain, and create() above
        # withholds it from admin too - but without the engine recordset here
        # that same protection would also block the automatic routing AT-04
        # requires, so a rep confirming their own over-ceiling quotation would
        # get an error instead of an approval. Same reasoning, and same fix,
        # as dealflow.audit.log._log().
        approval = self._df_engine().create(
            {
                "order_id": order.id,
                "risk_score": order.df_blended_risk_score,
                "risk_level": order.df_risk_level,
                "order_fingerprint": order.df_governance_fingerprint,
                "step_ids": [
                    (
                        0,
                        0,
                        {
                            "role": role,
                            "sequence": (index + 1) * 10,
                            "state": "pending" if index == 0 else "waiting",
                            "pending_since": (
                                fields.Datetime.now() if index == 0 else False
                            ),
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
        or close the chain out as fully approved.

        Closing the chain is not the end of the story. Approval used to be a
        dead end: every step went green, the chain went to 'approved', and the
        order sat in state 'draft' with nothing telling the rep it had cleared
        and nothing putting it in front of the customer. Live-reproduced -
        manager and finance both approved a HIGH-risk quotation and it stayed
        state='draft', invisible on the rep's dashboard and absent from the
        customer's portal list. The order-side hook below is what turns a
        granted approval into something that actually happens.
        """
        self.ensure_one()
        remaining = self.step_ids.filtered(lambda s: s.state == "waiting").sorted("sequence")
        if remaining:
            remaining[0]._df_engine().write(
                {"state": "pending", "pending_since": fields.Datetime.now()}
            )
        else:
            self._df_engine().write({"state": "approved"})
            self.order_id._df_on_approval_granted()

    def _reject(self):
        self.ensure_one()
        self._df_engine().write({"state": "rejected"})

    def _request_revision(self):
        self.ensure_one()
        self._df_engine().write({"state": "revision"})

    def _df_covers(self, order):
        """Whether this chain actually authorises `order` to confirm RIGHT NOW.

        All three conditions are load-bearing and were each independently
        exploitable before this method existed:

        1. the chain itself is approved;
        2. EVERY step is approved - `state` alone was not enough, because it
           is a plain writable column: a Sales Manager could set the chain to
           'approved' while their own step (or Finance's) was still pending,
           and the order confirmed on a chain nobody had actually walked;
        3. the order still looks the way it did when it was approved - see
           the comment on order_fingerprint.
        """
        self.ensure_one()
        if self.state != "approved":
            return False
        if any(step.state != "approved" for step in self.step_ids):
            return False
        return bool(self.order_fingerprint) and (
            self.order_fingerprint == order.df_governance_fingerprint
        )

    def _df_refusal_step(self):
        """The step that turned this chain down, if one did."""
        self.ensure_one()
        return self.step_ids.filtered(
            lambda s: s.state in ("rejected", "revision")
        ).sorted("sequence")[:1]

    def _df_blocks_resubmission(self, order):
        """Whether this chain forbids `order` being routed for approval again.

        A rejection is a decision about a specific deal, not a speed bump.
        Live-reproduced: a manager rejected a quotation with the reason "Not
        acceptable, do not resubmit", the rep pressed Confirm again on a
        byte-identical order, and a brand-new chain opened against the same
        numbers - so the rejection cost the rep one click and nothing else, and
        the same approver got the same deal back with no indication they had
        already refused it.

        The gate is the governance fingerprint, the same digest _df_covers()
        uses in the other direction: an approval only authorises the exact
        order it was granted for, and symmetrically a refusal only binds the
        exact order it was refused for. Change the discount, the quantity, the
        pricing or the customer tier and this stops matching, so a genuinely
        revised deal routes freely - which is the entire point of "changes
        requested". Resubmitting the identical deal is what is blocked.
        """
        self.ensure_one()
        if self.state not in ("rejected", "revision"):
            return False
        return bool(self.order_fingerprint) and (
            self.order_fingerprint == order.df_governance_fingerprint
        )

    def _supersede(self):
        """Retire a chain whose order has changed underneath it. The decision
        is not reversed (a rejection stays a rejection and is never reopened
        this way) - only an outstanding or still-standing one is retired, so
        the next confirm attempt routes a fresh chain against the new numbers.

        sudo(): superseding is done BY THE ENGINE in response to an edit, not
        authored by whoever made the edit - a rep editing their own quotation
        has no write access to the approval chain, and must not need any.
        Same reasoning as _create_for_order() and audit_log._log().
        """
        self.ensure_one()
        if self.state not in ("pending", "approved"):
            return False
        self._df_engine().write({"state": "superseded"})
        self.step_ids.filtered(
            lambda s: s.state in ("waiting", "pending")
        )._df_engine().write({"state": "superseded"})
        return True


class DealflowApprovalStep(models.Model):
    _name = "dealflow.approval.step"
    _description = "Approval Step"
    _order = "sequence"
    # The Approvals list shows current_step_id in its "Waiting on" column.
    # With no name field that rendered as "dealflow.approval.step,29" - the
    # single least useful answer to "who is this waiting on".
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("role")
    def _compute_display_name(self):
        roles = dict(self._fields["role"].selection)
        for step in self:
            step.display_name = roles.get(step.role) or _("Approval Step")

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
            ("pending", "Action needed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revision", "Changes requested"),
            ("superseded", "Superseded by an edit"),
        ],
        string="Status",
        default="waiting",
        readonly=True,
    )
    reason = fields.Text(string="Reason")
    acted_on = fields.Datetime(string="Acted On", readonly=True)
    pending_since = fields.Datetime(
        string="Pending Since",
        readonly=True,
        help="When this step's state last became 'pending' (i.e. became "
        "actionable). DF-017's approval-delay signal reads this - never "
        "create_date, which for a HIGH-risk chain's finance step is set "
        "when the chain was created, not when the manager's approval "
        "actually made finance's step actionable.",
    )

    def _df_engine(self):
        """See DealflowApproval._df_engine - identical contract."""
        return self.sudo().with_context(**{DECISION_CONTEXT: True})

    @api.model_create_multi
    def create(self, vals_list):
        # Steps are only ever born as part of a chain, through the (0, 0, ...)
        # commands in _create_for_order - which runs inside the engine context,
        # and Odoo propagates that context to the child create. A step created
        # any other way would let someone bolt an already-'approved' row onto a
        # live chain.
        if not self.env.context.get(DECISION_CONTEXT):
            raise UserError(
                _(
                    "Approval steps are generated with the chain they belong "
                    "to. They cannot be created by hand."
                )
            )
        return super().create(vals_list)

    def write(self, vals):
        guarded = GUARDED_STEP_FIELDS & set(vals)
        if guarded and not self.env.context.get(DECISION_CONTEXT):
            raise UserError(
                _(
                    "An approval decision can only be recorded with the "
                    "Approve, Reject or Request Revision buttons - it cannot "
                    "be edited directly (attempted: %s)."
                )
                % ", ".join(sorted(guarded))
            )
        return super().write(vals)

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
        # _df_engine() only AFTER _check_actionable() has confirmed this user
        # really holds this step's role - the guard exists to stop writes that
        # skip that check, never to skip it here.
        self._df_engine().write(
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
        self._df_engine().write(
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
        self.order_id._df_on_approval_refused(self)
        return True

    def action_request_revision(self, reason):
        self.ensure_one()
        self._check_actionable()
        if not reason:
            raise UserError(_("A reason is required to request a revision."))
        self._df_engine().write(
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
        self.order_id._df_on_approval_refused(self)
        return True
