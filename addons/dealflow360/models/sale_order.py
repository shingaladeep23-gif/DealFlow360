from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("negotiation", "Negotiation"),
            ("confirmed", "Confirmed"),
        ],
        string="Pipeline Stage",
        compute="_compute_df_pipeline_stage",
        store=True,
        help="Mockup screen 3's Kanban grouping, driven by native state plus "
        "DF-004's df_approval_id.state. Negotiation is driven by "
        "DF-014/015's portal negotiation model (see DEC-019 for why the "
        "customer-facing portal status is computed separately).",
    )

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

    @api.depends("state", "df_approval_id.state")
    def _compute_df_pipeline_stage(self):
        for order in self:
            if order.state == "sale":
                order.df_pipeline_stage = "confirmed"
            elif order.df_approval_id.state == "pending":
                order.df_pipeline_stage = "pending_approval"
            elif order.df_approval_id.state == "approved":
                order.df_pipeline_stage = "approved"
            else:
                order.df_pipeline_stage = "draft"

    df_blended_risk_score = fields.Float(
        string="Blended Risk Score",
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
        [("none", "None"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level",
        compute="_compute_df_risk",
        store=True,
        help="NONE is structural (every line within its ceiling, i.e. "
        "max_excess == 0) - never a score threshold. MEDIUM/HIGH split at "
        "the admin-configurable ir.config_parameter 'dealflow.risk_high_min' "
        "(DEC-010), default 40.",
    )
    df_risk_summary = fields.Char(
        string="Risk Summary",
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
                order.df_risk_summary = (
                    "%s exceeds its %.1f%% discount ceiling by %.1f points "
                    "(blended risk score %.1f)"
                    % (
                        worst_line.product_id.display_name,
                        worst_line.df_effective_ceiling,
                        worst_line.df_excess_points,
                        score,
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
        """
        routed = self.env["sale.order"]
        to_confirm = self.env["sale.order"]
        for order in self:
            if order.df_risk_level == "none":
                to_confirm |= order
                continue
            approval = order.df_approval_id
            if approval.state == "approved":
                to_confirm |= order
            elif approval.state == "pending":
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
            raise UserError(
                _(
                    "The following quotations exceeded their discount ceiling "
                    "and have been routed for approval instead of being "
                    "confirmed: %s"
                )
                % ", ".join(routed.mapped("name"))
            )
        return confirmed

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
