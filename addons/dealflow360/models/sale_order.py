import hashlib
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

HEALTH_FLAG_CODES = ("stalled", "discount_anomaly", "approval_delay", "delivery_risk")

# Writing any of these on sale.order changes what an approver would have been
# looking at, so an outstanding approval chain has to be re-checked against it.
# (The line-level equivalent lives in models/sale_order_line.py.)
GOVERNANCE_ORDER_FIELDS = frozenset({"partner_id", "pricelist_id"})


class DealflowHealthFlag(models.Model):
    _name = "dealflow.health.flag"
    _description = "Deal Health Warning Sign"

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        help="Technical constant the compute reads by - one of "
        "stalled/discount_anomaly/approval_delay/delivery_risk.",
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "A health flag code must be unique.")
    ]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    df_approval_id = fields.Many2one(
        "dealflow.approval",
        string="Approval Chain",
        readonly=True,
        copy=False,
        help="Most recent DF-004 approval chain routed for this quotation. "
        "A rejected/revision chain is superseded by a fresh one on the next "
        "confirm attempt or reapproval trigger - this always points at the "
        "latest one, and older ones remain in the audit trail via "
        "dealflow.audit.log.",
    )

    df_audit_log_ids = fields.One2many(
        "dealflow.audit.log",
        "order_id",
        string="Audit Trail",
        readonly=True,
        help="Every governance event on this deal - routed, approved, "
        "rejected, revision requested, superseded by an edit, re-routed after "
        "a negotiation. The rows were always written; until now nothing in "
        "the UI showed them, so the problem statement's 'confirmation screen "
        "with a full audit trail entry' had no screen.",
    )
    df_approval_state = fields.Selection(
        related="df_approval_id.state",
        string="Approval Status",
        store=True,
        help="Stored so the reporting screen can filter and group by it "
        "without reaching through df_approval_id on every row.",
    )

    df_negotiation_ids = fields.One2many(
        "dealflow.negotiation",
        "order_id",
        string="Customer Negotiations",
        help="Counter-discounts the customer has proposed from the portal. "
        "Defined here rather than on dealflow.negotiation so the pipeline "
        "stage below can depend on it.",
    )

    df_margin_pct = fields.Float(
        string="Margin (%)",
        compute="_compute_df_margin_pct",
        store=True,
        help="Live order-level margin: aggregate (price_subtotal - cost) / "
        "price_subtotal across all product lines.",
    )
    df_pipeline_stage = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_approval", "Waiting for approval"),
            ("approved", "Approved"),
            ("negotiation", "In negotiation"),
            ("confirmed", "Confirmed"),
        ],
        string="Stage",
        compute="_compute_df_pipeline_stage",
        store=True,
        group_expand="_read_group_df_pipeline_stage",
        help="The Kanban column a quotation sits in, derived from native "
        "state plus the approval chain plus portal negotiations. Never set "
        "by hand.",
    )

    @api.model
    def _read_group_df_pipeline_stage(self, *args, **kwargs):
        """Render all five pipeline columns, empty ones included.

        Odoo only produces a Kanban column for a group that actually has
        records, so the board showed 3 of its 5 stages - Approved and Confirmed
        never appeared, and a pipeline that silently hides the two stages
        representing SUCCESS is worse than no pipeline. A funnel has to show
        the empty steps or it cannot show that they are empty.

        (*args/**kwargs: Odoo calls a group_expand with different signatures
        depending on the field type and version - (values, domain) for a
        selection, plus an order for a many2one. The answer here does not
        depend on any of them: the stages are a fixed, ordered set.)
        """
        return [value for value, _label in self._fields["df_pipeline_stage"].selection]

    @api.depends(
        "order_line.price_subtotal",
        "order_line.product_uom_qty",
        "order_line.product_id.standard_price",
        "order_line.display_type",
    )
    def _compute_df_margin_pct(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            revenue = sum(lines.mapped("price_subtotal"))
            cost = sum(
                line.product_uom_qty * (line.product_id.standard_price or 0.0)
                for line in lines
            )
            order.df_margin_pct = (
                (revenue - cost) / revenue * 100.0 if revenue else 0.0
            )

    @api.depends("state", "df_approval_id.state", "df_negotiation_ids.state")
    def _compute_df_pipeline_stage(self):
        # Ordered most-actionable first. "In negotiation" ranks BELOW the two
        # approval states on purpose: a counter-discount that pushed the deal
        # back over the limit is already sitting in someone's approval queue,
        # and that is the fact the pipeline board needs to surface.
        #
        # The negotiation branch is why df_negotiation_ids exists. Before it,
        # nothing in the codebase ever assigned "negotiation", so the Kanban
        # rendered a column that could never contain a card no matter what a
        # customer did.
        for order in self:
            if order.state == "sale":
                order.df_pipeline_stage = "confirmed"
            elif order.df_approval_id.state == "pending":
                order.df_pipeline_stage = "pending_approval"
            elif order.df_approval_id.state == "approved":
                order.df_pipeline_stage = "approved"
            elif order.df_negotiation_ids.filtered(lambda n: n.state == "proposed"):
                # Only an UNANSWERED request parks a card here. Keying on any
                # negotiation at all meant a deal stayed "In negotiation"
                # forever once a customer had ever asked for anything, however
                # long ago it was settled.
                order.df_pipeline_stage = "negotiation"
            else:
                order.df_pipeline_stage = "draft"

    df_governance_fingerprint = fields.Char(
        string="Governance Fingerprint",
        compute="_compute_df_governance_fingerprint",
        store=True,
        copy=False,
        help="Digest of everything an approval decision actually depends on: "
        "the customer's discount tier plus every product line's product, "
        "quantity, unit price and discount. dealflow.approval snapshots this "
        "at routing time so a decision can be checked against the order it "
        "was made about - see dealflow.approval.order_fingerprint.",
    )

    @api.depends(
        "partner_id.df_tier_id",
        "order_line.product_id",
        "order_line.product_uom_qty",
        "order_line.price_unit",
        "order_line.discount",
        "order_line.display_type",
    )
    def _compute_df_governance_fingerprint(self):
        # Sorted, so re-ordering lines is correctly NOT treated as a change;
        # rounded, so float noise from a recompute cannot spuriously supersede
        # a live approval chain.
        for order in self:
            lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id
            )
            payload = repr(
                (
                    order.partner_id.df_tier_id.id or 0,
                    sorted(
                        (
                            line.product_id.id,
                            round(line.product_uom_qty or 0.0, 4),
                            round(line.price_unit or 0.0, 4),
                            round(line.discount or 0.0, 4),
                        )
                        for line in lines
                    ),
                )
            )
            order.df_governance_fingerprint = hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()

    def _df_invalidate_stale_approvals(self):
        """Retire any approval chain that no longer describes its order.

        Called after every governance-relevant edit (see the create/write/
        unlink overrides on sale.order.line). This is also what finally makes
        the problem statement's "all approvals, rejections AND EDITS must be
        logged with user, timestamp and reason" true: before it, an edit that
        invalidated a decision left no trace anywhere.
        """
        for order in self:
            approval = order.df_approval_id
            if not approval or approval.state not in ("pending", "approved"):
                continue
            if approval.order_fingerprint == order.df_governance_fingerprint:
                continue
            was_approved = approval.state == "approved"
            if not approval._supersede():
                continue
            self.env["dealflow.audit.log"]._log(
                order,
                "superseded",
                _(
                    "Quotation edited after it was %(status)s, so that "
                    "decision no longer applies. Discount risk was %(old).1f "
                    "at routing time and is %(new).1f now; the quotation must "
                    "be routed for approval again before it can be confirmed."
                )
                % {
                    "status": _("approved") if was_approved else _("sent for approval"),
                    "old": approval.risk_score,
                    "new": order.df_blended_risk_score,
                },
            )

    def write(self, vals):
        res = super().write(vals)
        if GOVERNANCE_ORDER_FIELDS & set(vals):
            self._df_invalidate_stale_approvals()
        return res

    df_blended_risk_score = fields.Float(
        string="Discount Risk",
        compute="_compute_df_risk",
        store=True,
        help="DEC-003: min(100, 6*blended_excess + 3*max_excess), where "
        "blended_excess is the revenue-weighted average per-line "
        "df_excess_points and max_excess is the worst single line's. Weights "
        "use each line's pre-discount reference value (qty * pricelist/list "
        "price), not its post-discount price_subtotal - see the comment on "
        "_compute_df_risk for why.",
    )
    df_risk_level = fields.Selection(
        # The labels state the CONSEQUENCE rather than an abstract severity:
        # a salesperson reading "Medium" has to look up what that costs them,
        # whereas "Needs manager approval" is already the answer.
        [
            ("none", "Within limits"),
            ("medium", "Needs manager approval"),
            ("high", "Needs manager + finance"),
        ],
        string="Discount Status",
        compute="_compute_df_risk",
        store=True,
        help="NONE is structural (every line within its ceiling, i.e. "
        "max_excess == 0) - never a score threshold. MEDIUM/HIGH split at "
        "the admin-configurable ir.config_parameter 'dealflow.risk_high_min' "
        "(DEC-010), default 40.",
    )
    df_risk_summary = fields.Char(
        string="Why this needs approval",
        compute="_compute_df_risk",
        store=True,
        help="Human-readable reason this order was flagged, naming the worst "
        "offending line and its overshoot, so the approval UI (DF-006) does "
        "not invent its own wording for DEC-003's thresholds.",
    )

    @api.depends(
        "order_line.df_excess_points",
        "order_line.df_effective_ceiling",
        "order_line.discount",
        "order_line.price_unit",
        "order_line.product_uom_qty",
        "order_line.product_id",
        "order_line.display_type",
    )
    def _compute_df_risk(self):
        # DEC-003's own worked example states weights of 0.667/0.333 for
        # "subtotals 1000/500" on a 12%/18%-discounted pair - that ratio only
        # comes out of the PRE-discount value (1000/500), not the post-
        # discount price_subtotal (880/410, which gives 0.682/0.318 and a
        # score of 39.26, not 40). Weighting by revenue actually collected
        # would also perversely dampen the signal for the worst offenders:
        # a bigger discount both raises excess_i and shrinks its own weight.
        # So weight_i uses each line's pre-discount reference value (its
        # DEC-009 pricelist/list price times quantity), matching the spec's
        # stated numbers exactly.
        threshold = float(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dealflow.risk_high_min", 40.0)
        )
        for order in self:
            lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id
            )
            gross_values = {
                line.id: line._df_reference_price() * (line.product_uom_qty or 0.0)
                for line in lines
            }
            order_gross = sum(gross_values.values())
            if not lines or not order_gross:
                order.df_blended_risk_score = 0.0
                order.df_risk_level = "none"
                order.df_risk_summary = False
                continue

            max_excess = max(lines.mapped("df_excess_points"))
            blended_excess = sum(
                line.df_excess_points * (gross_values[line.id] / order_gross)
                for line in lines
            )
            score = min(100.0, 6 * blended_excess + 3 * max_excess)
            order.df_blended_risk_score = score

            if max_excess <= 0.0:
                order.df_risk_level = "none"
                order.df_risk_summary = False
            else:
                order.df_risk_level = "high" if score > threshold else "medium"
                worst_line = max(lines, key=lambda l: l.df_excess_points)
                # Shown verbatim on the quotation and approval screens, so it
                # is written for a salesperson: no "blended", no "ceiling",
                # no score arithmetic they did not ask for.
                order.df_risk_summary = (
                    "%s is discounted %.1f points past the %.1f%% limit for "
                    "this customer."
                    % (
                        worst_line.product_id.display_name,
                        worst_line.df_excess_points,
                        worst_line.df_effective_ceiling,
                    )
                )

    def action_confirm(self):
        """DF-004/AT-04: a quotation whose blended risk is MEDIUM/HIGH is
        never confirmed directly - clicking Confirm on it instead routes it
        (or re-routes it, if the previous chain was rejected/needs revision)
        into a dealflow.approval chain, automatically, without the rep ever
        requesting approval by hand. Confirmation stays blocked while a
        chain is pending; once every step is approved a further Confirm
        click proceeds through native sale.order.action_confirm normally.
        Orders with risk NONE are never touched by this override.

        The green light is dealflow.approval._df_covers(), NOT a bare
        `state == 'approved'` check. A chain only authorises the order it was
        actually approved against, with every step genuinely walked - see that
        method for the two bypasses a bare state check allowed.
        """
        routed = self.env["sale.order"]
        to_confirm = self.env["sale.order"]
        for order in self:
            if order.df_risk_level == "none":
                to_confirm |= order
                continue
            approval = order.df_approval_id
            if approval and approval._df_covers(order):
                to_confirm |= order
            elif approval and approval._df_blocks_resubmission(order):
                # Refused, and nothing about the deal has changed since. See
                # dealflow.approval._df_blocks_resubmission: re-routing an
                # unchanged deal put the same numbers back in front of the same
                # approver and made the rejection meaningless.
                step = approval._df_refusal_step()
                raise UserError(
                    _(
                        "%(name)s was %(outcome)s by %(user)s (%(role)s): "
                        "%(reason)s\n\nNothing has changed on this quotation "
                        "since. Revise the deal - its discount, quantities or "
                        "pricing - before submitting it for approval again."
                    )
                    % {
                        "name": order.name,
                        "outcome": (
                            _("rejected")
                            if approval.state == "rejected"
                            else _("sent back for changes")
                        ),
                        "user": step.approver_id.name or _("an approver"),
                        "role": step._role_label() if step else _("approver"),
                        "reason": step.reason or _("no reason was given"),
                    }
                )
            elif approval.state == "pending" and (
                approval.order_fingerprint == order.df_governance_fingerprint
            ):
                step = approval.current_step_id
                raise UserError(
                    _("%(name)s cannot be confirmed: it is pending %(role)s approval.")
                    % {
                        "name": order.name,
                        "role": step._role_label() if step else _("further"),
                    }
                )
            else:
                # No chain yet, or the previous one was rejected/sent back
                # for revision and the rep re-attempted confirm - route a
                # fresh chain now, per AT-04's "automatically" requirement.
                new_approval = self.env["dealflow.approval"]._create_for_order(order)
                order.df_approval_id = new_approval.id
                routed |= order
        confirmed = super(SaleOrder, to_confirm).action_confirm() if to_confirm else True
        if routed:
            # NOT a UserError. Routing is a state change we must KEEP: raising
            # here propagated out of the RPC call, which rolls the whole
            # transaction back - so the user was told "routed for approval"
            # while the dealflow.approval chain, its steps and df_approval_id
            # were all discarded. Live-verified before the fix: confirming an
            # over-ceiling quotation left approvals count unchanged,
            # df_approval_id False and df_pipeline_stage still 'draft', so
            # AT-04's automatic routing never actually happened through the UI
            # and the Approvals screen stayed permanently empty. (The portal
            # path survived only because its controller CATCHES the UserError,
            # which is what kept this hidden.) A returned client action
            # reports the same thing without destroying it.
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Routed for approval"),
                    "message": _(
                        "%s exceeded its discount ceiling and has been sent "
                        "for approval instead of being confirmed."
                    )
                    % ", ".join(routed.mapped("name")),
                    "type": "warning",
                    "sticky": False,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
        return confirmed

    def _df_on_approval_granted(self):
        """Called by dealflow.approval._advance() the moment a chain closes as
        fully approved. Turns "the chain went green" into something the rep and
        the customer can actually see.

        Before this, approval was a dead end. Every step went green, the chain
        went to 'approved' - and the order stayed in state 'draft' with no
        chatter entry, no audit line and nothing in front of the customer. The
        rep had no way to learn their deal had cleared short of reopening the
        record and reading the approval tab, and the quotation was never sent
        to anybody. Live-reproduced on a HIGH-risk quotation: manager approved,
        finance approved, `covers?` returned True, and the order was still
        state='draft'.

        Three things happen here, all of them things a human would otherwise
        have had to remember to do:

        1. The quotation is marked SENT. That is what puts it in front of the
           customer as a live quotation rather than someone's private draft,
           and it is the state the portal's own Confirm button reads. It is
           deliberately NOT auto-confirmed: the customer accepting the deal is
           their decision, and confirming for them would make the portal
           negotiate/confirm flow unreachable.
        2. The rep is told, on the record they own, via the chatter.
        3. The decision is written to the audit trail, so "approved and
           released to the customer" is one auditable event rather than an
           inference from two unrelated timestamps.

        sudo() throughout: the actor here is FINANCE or a SALES MANAGER, who
        has no business writing the salesperson's quotation - this is the
        system releasing the deal in response to their decision, exactly like
        the engine recordset on dealflow.approval. Same reasoning as
        _create_for_order() and audit_log._log().
        """
        for order in self:
            if order.state not in ("draft", "sent"):
                # Already confirmed or cancelled - a late-arriving approval has
                # nothing left to release.
                continue
            order_sudo = order.sudo()
            if order.state == "draft":
                order_sudo.write({"state": "sent"})
            order_sudo.message_post(
                body=_(
                    "Approved. This quotation has cleared every approval step "
                    "and is now available to %(customer)s in their portal."
                )
                % {"customer": order.partner_id.display_name},
                subtype_xmlid="mail.mt_note",
            )
            self.env["dealflow.audit.log"]._log(
                order,
                "approved",
                _(
                    "Approval chain complete - quotation released to "
                    "%(customer)s for acceptance."
                )
                % {"customer": order.partner_id.display_name},
            )

    def _df_on_approval_refused(self, step):
        """Called by dealflow.approval.step when an approver rejects a deal or
        sends it back for changes. Tells the person who owns the deal.

        The rep was never told anything. Live-reproduced: a manager rejected a
        quotation with a written reason and the ONLY chatter entry on the order
        was still "Sales Order created" - no message, no activity, no email.
        The reason existed solely inside the dealflow.approval record, which
        the rep has no particular reason to open and, as an approver-owned
        model, is not on their radar. So the decision was invisible to the one
        person whose job it is to act on it.

        Two things happen, both of which reach the rep where they already
        work: a chatter message (mt_comment, so followers are actually
        notified rather than it landing as a silent internal note), and a real
        to-do activity in their Odoo inbox carrying the approver's reason.

        sudo() throughout: the actor is a Sales Manager or Finance, who has no
        write access to the salesperson's quotation. This is the system
        relaying their decision, exactly as in _df_on_approval_granted.
        """
        self.ensure_one()
        rejected = step.state == "rejected"
        reason = step.reason or _("No reason was given.")
        headline = (
            _("Rejected by %(user)s (%(role)s).")
            if rejected
            else _("Changes requested by %(user)s (%(role)s).")
        ) % {"user": step.approver_id.name, "role": step._role_label()}
        order_sudo = self.sudo()
        order_sudo.message_post(
            body="%s %s %s"
            % (
                headline,
                reason,
                _(
                    "This quotation cannot be submitted again as it stands - "
                    "change the deal first."
                ),
            ),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        if self.user_id:
            order_sudo.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=self.user_id.id,
                summary=(
                    _("Rejected: %s") if rejected else _("Changes requested: %s")
                )
                % self.name,
                note="%s %s" % (headline, reason),
            )

    def _df_trigger_reapproval(self, negotiation=None):
        """DF-014/AT-09: called by dealflow.negotiation._apply() when a
        customer counter-discount pushes the order's risk back above
        threshold. Creates a fresh approval chain (a new audit entry per the
        'submitted' log inside _create_for_order) and points df_approval_id
        at it, exactly as if the rep had re-attempted Confirm.
        """
        self.ensure_one()
        approval = self.env["dealflow.approval"]._create_for_order(self)
        self.df_approval_id = approval.id
        return approval

    # -- DF-017: Deal Health (DEC-005/DEC-011) ---------------------------
    #
    # Not an @api.depends compute: two of the four signals (stalled,
    # approval delay) are functions of wall-clock time passing, not of any
    # stored field changing, so they can only be refreshed by the DF-017
    # cron (or an on-demand call) actually re-running - matching
    # architecture.md's "scheduled cron + computed fields" framing.
    # df_health_flagged_date also has state a pure compute cannot express:
    # it must be preserved across recomputes while a signal stays active,
    # and only reset once every signal clears.

    df_last_activity = fields.Datetime(
        string="Last Activity",
        compute="_compute_df_last_activity",
        store=True,
        help="Latest real touch on this quotation: the order's own last "
        "write, its latest line edit, or its latest chatter message - "
        "whichever is most recent. DEC-005's 'stalled' signal reads this.",
    )
    df_health_score = fields.Integer(
        string="Health Score",
        readonly=True,
        copy=False,
        help="DEC-005: starts at 100, accrues penalties for each active "
        "signal (stalled/discount anomaly/approval delay/delivery risk). "
        "Written only by _compute_deal_health() (DF-017 cron or on-demand) "
        "- not a live @api.depends compute, see the module-level note.",
    )
    df_health_status = fields.Selection(
        [("healthy", "Healthy"), ("at_risk", "At Risk"), ("critical", "Critical")],
        string="Health",
        readonly=True,
        copy=False,
        help="Bucketed from df_health_score: >=80 Healthy, 50-79 At Risk, "
        "<50 Critical (DEC-005).",
    )
    df_health_flags = fields.Many2many(
        "dealflow.health.flag",
        string="Warning Signs",
        readonly=True,
        copy=False,
        help="DEC-011: which of DEC-005's four signals are currently active "
        "on this deal, so the dashboard can count/filter per signal without "
        "re-deriving thresholds client-side.",
    )
    df_health_reason = fields.Text(
        string="What is wrong",
        readonly=True,
        copy=False,
        help="Human-readable detail for every currently active signal, "
        "naming the real numbers behind it (e.g. the actual vs. average "
        "discount) - not a generic label.",
    )
    df_health_flagged_date = fields.Datetime(
        string="Flagged Since",
        readonly=True,
        copy=False,
        help="When this deal first had ANY active health signal. Preserved "
        "across recomputes while at least one signal stays active; cleared "
        "the moment every signal clears (a deal that recovers and later "
        "degrades again gets a fresh flagged date).",
    )

    @api.depends("order_line.write_date", "message_ids.date")
    def _compute_df_last_activity(self):
        # Deliberately NOT depending on the order's own write_date: this
        # field's own writes bump write_date too, and write_date WAS
        # originally in this depends list - meaning every write immediately
        # marked the field dirty again and the next read recomputed it back
        # to "now", making it impossible for anything (including a test
        # simulating an old timestamp) to hold a genuinely stale value.
        # write_date is still READ below as one real activity signal, just
        # not a recompute TRIGGER.
        for order in self:
            candidates = [order.write_date or order.create_date]
            if order.order_line:
                candidates += [d for d in order.order_line.mapped("write_date") if d]
            if order.message_ids:
                candidates += [d for d in order.message_ids.mapped("date") if d]
            order.df_last_activity = max(candidates) if candidates else order.create_date

    def _df_health_signal_stalled(self, now, threshold_days):
        self.ensure_one()
        if not self.df_last_activity:
            return 0.0, None
        days_inactive = (now - self.df_last_activity).total_seconds() / 86400.0
        if days_inactive <= threshold_days:
            return 0.0, None
        penalty = min(30.0, 5.0 * (days_inactive - threshold_days))
        detail = _("Stalled %(days).1f day(s) (threshold %(threshold)d)") % {
            "days": days_inactive,
            "threshold": threshold_days,
        }
        return penalty, detail

    def _df_health_signal_discount_anomaly(self):
        self.ensure_one()
        lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if not lines or not self.user_id:
            return 0.0, None
        order_avg = sum(lines.mapped("discount")) / len(lines)
        if order_avg <= 0.0:
            return 0.0, None

        cutoff = fields.Datetime.now() - timedelta(days=90)
        past_lines = self.env["sale.order.line"].search(
            [
                ("order_id.user_id", "=", self.user_id.id),
                ("order_id", "!=", self.id),
                ("order_id.create_date", ">=", cutoff),
                ("display_type", "=", False),
                ("product_id", "!=", False),
            ]
        )
        if not past_lines:
            # No real historical baseline for this rep yet - cannot claim an
            # anomaly against data that does not exist.
            return 0.0, None
        rep_avg = sum(past_lines.mapped("discount")) / len(past_lines)
        if rep_avg <= 0.0 or order_avg <= 1.5 * rep_avg:
            return 0.0, None

        detail = _(
            "Discount %(order).1f%% vs %(rep)s's 90-day average %(avg).1f%%"
        ) % {"order": order_avg, "rep": self.user_id.name, "avg": rep_avg}
        return 20.0, detail

    def _df_health_signal_approval_delay(self, now, threshold_days):
        self.ensure_one()
        approval = self.df_approval_id
        if approval.state != "pending":
            return 0.0, None
        step = approval.current_step_id
        if not step or not step.pending_since:
            return 0.0, None
        days_pending = (now - step.pending_since).total_seconds() / 86400.0
        if days_pending <= threshold_days:
            return 0.0, None
        penalty = min(25.0, 5.0 * (days_pending - threshold_days))
        detail = _(
            "Approval pending %(days).1f day(s) with %(role)s (threshold %(threshold)d)"
        ) % {
            "days": days_pending,
            "role": step._role_label(),
            "threshold": threshold_days,
        }
        return penalty, detail

    def _df_health_signal_delivery_risk(self):
        self.ensure_one()
        lines = self.order_line.filtered(
            lambda l: not l.display_type and l.product_id and l.product_id.type == "product"
        )
        if not lines:
            return 0.0, None
        products = lines.mapped("product_id")
        quants = self.env["stock.quant"].sudo().search(
            [
                ("product_id", "in", products.ids),
                ("location_id.usage", "=", "internal"),
            ]
        )
        free_by_product = {}
        for quant in quants:
            free_by_product[quant.product_id.id] = (
                free_by_product.get(quant.product_id.id, 0.0)
                + quant.quantity
                - quant.reserved_quantity
            )
        shortfalls = []
        for line in lines:
            available = free_by_product.get(line.product_id.id, 0.0)
            if available + 1e-6 < line.product_uom_qty:
                shortfalls.append(
                    "%s (need %.1f, have %.1f)"
                    % (line.product_id.display_name, line.product_uom_qty, max(0.0, available))
                )
        if not shortfalls:
            return 0.0, None
        detail = _("Cannot be fully sourced from current stock: %s") % "; ".join(shortfalls)
        return 25.0, detail

    def _compute_deal_health(self):
        """Recompute DF-017 deal health for every order in self. Not
        api.depends-driven - see the module note above. Called by
        _cron_compute_deal_health() and safe to call on-demand (tests, a
        manual refresh action)."""
        now = fields.Datetime.now()
        stalled_days = int(
            self.env["ir.config_parameter"].sudo().get_param("dealflow.health_stalled_days", 7)
        )
        approval_delay_days = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dealflow.health_approval_delay_days", 2)
        )
        flags_by_code = {
            f.code: f for f in self.env["dealflow.health.flag"].search([])
        }

        for order in self:
            penalties = {}
            details = {}
            for code, (penalty, detail) in {
                "stalled": order._df_health_signal_stalled(now, stalled_days),
                "discount_anomaly": order._df_health_signal_discount_anomaly(),
                "approval_delay": order._df_health_signal_approval_delay(
                    now, approval_delay_days
                ),
                "delivery_risk": order._df_health_signal_delivery_risk(),
            }.items():
                if penalty:
                    penalties[code] = penalty
                    details[code] = detail

            score = max(0, round(100 - sum(penalties.values())))
            status = "healthy" if score >= 80 else ("at_risk" if score >= 50 else "critical")
            active_flags = [flags_by_code[c] for c in HEALTH_FLAG_CODES if c in penalties and c in flags_by_code]

            order.df_health_score = score
            order.df_health_status = status
            order.df_health_flags = [(6, 0, [f.id for f in active_flags])]
            order.df_health_reason = "; ".join(details[c] for c in HEALTH_FLAG_CODES if c in details) or False

            if active_flags and not order.df_health_flagged_date:
                order.df_health_flagged_date = now
            elif not active_flags:
                order.df_health_flagged_date = False

    def action_df_refresh_health(self):
        """On-demand recompute from the UI (quotation form button and the
        Deal Health screen). DF-017's signals are time-based, so without a
        manual trigger the only thing that ever refreshed them was the cron
        - which made the feature look dead to anyone opening a deal between
        cron runs. Same code path as the cron, never a parallel one."""
        # sudo(): df_health_* are engine-owned readonly fields. Finance can
        # open a quotation but has no write access to sale.order, so without
        # this the Refresh button would fail for exactly the role most likely
        # to be reviewing a troubled deal.
        self.sudo()._compute_deal_health()
        return True

    # -- B9: acting on an alert ------------------------------------------
    #
    # "An automated nudge or escalation action can be triggered from an
    # alert." The Deal Health screen could show a stalled or at-risk deal and
    # then offered nothing to DO about it, which is most of the point of
    # monitoring one.

    def _df_escalation_user(self):
        """Who a deal escalates TO: the sales team's leader, falling back to
        any Sales Manager. Never the rep who already owns the deal - that is
        a nudge, not an escalation."""
        self.ensure_one()
        leader = self.team_id.user_id
        if leader and leader != self.user_id:
            return leader
        group = self.env.ref(
            "dealflow360.group_dealflow_sales_manager", raise_if_not_found=False
        )
        if group:
            candidates = group.users.filtered(lambda u: u != self.user_id)
            if candidates:
                return candidates[0]
        return self.env["res.users"]

    def action_df_nudge(self):
        """Ask the deal's owner to move it on: a real chatter message plus a
        real scheduled activity in their Odoo inbox, not a notification that
        vanishes on refresh."""
        for order in self:
            if not order.user_id:
                raise UserError(
                    _("%s has no salesperson to nudge.") % order.name
                )
            reason = order.df_health_reason or _("This deal needs attention.")
            order.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=order.user_id.id,
                summary=_("Follow up on %s") % order.name,
                note=reason,
            )
            order.message_post(
                body=_("%(user)s nudged %(owner)s to follow this deal up. %(reason)s")
                % {
                    "user": self.env.user.name,
                    "owner": order.user_id.name,
                    "reason": reason,
                },
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    def action_df_escalate(self):
        """Put the deal in front of someone senior, with the health engine's
        own reasoning attached."""
        for order in self:
            target = order._df_escalation_user()
            if not target:
                raise UserError(
                    _(
                        "There is nobody to escalate %s to - no sales team "
                        "leader and no other sales manager."
                    )
                    % order.name
                )
            reason = order.df_health_reason or _("Flagged as at risk.")
            order.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=target.id,
                summary=_("Escalated: %s") % order.name,
                note=reason,
            )
            order.message_post(
                body=_(
                    "%(user)s escalated this deal to %(target)s. %(reason)s"
                )
                % {
                    "user": self.env.user.name,
                    "target": target.name,
                    "reason": reason,
                },
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    # -- B1: the rep workspace's "Reload Data" ----------------------------

    @api.model
    def action_df_reload_workspace_data(self):
        """B1's Reload Data: "Refreshes pricing, stock and approval data from
        the backend."

        A real refresh, not a client-side re-render dressed up as one. Deal
        health is the one thing on the workspace that genuinely goes stale
        without work being done - two of its four signals are functions of
        wall-clock time (see the note above _compute_deal_health), and the
        stock-shortfall signal re-reads live stock.quant. Prices and approval
        state are stored computes that Odoo keeps current on their own, so
        this deliberately does not pretend to "recompute" them.
        """
        orders = self.search([("state", "in", ("draft", "sent", "sale"))])
        # sudo(): df_health_* are engine-owned readonly fields, same reasoning
        # as action_df_refresh_health.
        orders.sudo()._compute_deal_health()
        return {
            "orders_refreshed": len(orders),
            "at_risk": len(
                orders.filtered(lambda o: o.df_health_status in ("at_risk", "critical"))
            ),
        }

    @api.model
    def _cron_compute_deal_health(self):
        """DF-017 scheduled action: refresh deal health for every open
        deal. Scoped to draft/sent/sale - a cancelled or fully-invoiced
        deal is no longer 'live' in the sense DEC-005's signals describe."""
        orders = self.search([("state", "in", ("draft", "sent", "sale"))])
        orders._compute_deal_health()
