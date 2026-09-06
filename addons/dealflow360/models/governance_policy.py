"""A3: the governance thresholds, configurable by the roles that own them.

The four numbers below already existed and were already read by the engines -
but only as `ir.config_parameter` keys surfaced through a res.config.settings
panel, and that panel is unreachable for every DealFlow role. Odoo's own
res.config.settings.execute() hard-requires base.group_system
(`if not self.env.is_admin(): raise AccessError`), and the model's ACL grants
nothing below it either. Live-verified: no menu opened the panel for any of the
four internal roles, and df.admin got an AccessError trying to save it. So A3's
"configure which range needs manager vs manager+finance" was configurable by
nobody, and section 3's "Sales Manager - configures discount tiers and approval
chains" had no screen behind it.

This is deliberately a thin UI surface over the SAME ir.config_parameter keys,
not a second source of truth:

  * every engine read site is untouched - sale.order._compute_df_risk,
    sale.order.line._compute_df_governance and _compute_deal_health still read
    the parameters exactly as before, so the risk arithmetic is unchanged;
  * res.config.settings keeps its panel for a full Odoo administrator;
  * this screen just lets a Sales Manager or DealFlow Admin write the same
    keys, gated by an ordinary ACL rather than by base.group_system.

sudo() on set_param is the point of the model, not an oversight: writing
ir.config_parameter requires group_system, and granting that to every Sales
Manager to let them move one threshold would hand them the whole Odoo
administration surface. The escalation is bounded to these four named keys and
is only reachable by a user who already holds the ACL for this model.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# key -> (parameter name, default). The single place the mapping lives.
POLICY_PARAMETERS = {
    "risk_high_min": ("dealflow.risk_high_min", 40.0),
    "default_max_discount": ("dealflow.default_max_discount", 5.0),
    "health_stalled_days": ("dealflow.health_stalled_days", 7),
    "health_approval_delay_days": ("dealflow.health_approval_delay_days", 2),
}


class DealflowGovernancePolicy(models.TransientModel):
    _name = "dealflow.governance.policy"
    _description = "Discount governance and approval routing settings (A3)"

    risk_high_min = fields.Float(
        string="Send to finance above",
        help="How far over its discount limit a quotation must score before "
        "finance has to approve it as well as a sales manager. At or below "
        "this score a sales manager alone can approve it. This is the "
        "manager-vs-manager+finance boundary A3 asks to be configurable; the "
        "scoring formula itself stays in code.",
    )
    default_max_discount = fields.Float(
        string="Default discount limit (%)",
        help="The discount limit applied to a line when neither the "
        "customer's tier nor the product's category sets one. A tier or "
        "category left at 0 counts as UNSET, not as a 0% ceiling.",
    )
    health_stalled_days = fields.Integer(
        string="Call a deal stalled after (days)",
        help="A deal with no activity beyond this many days starts accruing "
        "the 'stalled' deal-health penalty.",
    )
    health_approval_delay_days = fields.Integer(
        string="Flag an approval delay after (days)",
        help="An approval step left pending beyond this many days starts "
        "accruing the 'approval delay' deal-health penalty.",
    )

    @api.model
    def default_get(self, fields_list):
        """Open the form on what is CURRENTLY in force, not on field
        defaults - otherwise saving would silently reset a threshold the
        person never intended to touch."""
        res = super().default_get(fields_list)
        params = self.env["ir.config_parameter"].sudo()
        for fname, (key, default) in POLICY_PARAMETERS.items():
            raw = params.get_param(key, default)
            res[fname] = (
                int(float(raw))
                if self._fields[fname].type == "integer"
                else float(raw)
            )
        return res

    @api.constrains(
        "risk_high_min",
        "default_max_discount",
        "health_stalled_days",
        "health_approval_delay_days",
    )
    def _check_ranges(self):
        for policy in self:
            if not 0.0 < policy.risk_high_min <= 100.0:
                raise ValidationError(
                    _(
                        "The finance threshold is a risk score, so it has to "
                        "sit between 0 and 100. A score can never exceed 100, "
                        "and a threshold of 0 would send every flagged deal to "
                        "finance."
                    )
                )
            if not 0.0 <= policy.default_max_discount <= 100.0:
                raise ValidationError(
                    _("The default discount limit must be between 0 and 100%.")
                )
            if policy.health_stalled_days < 1 or policy.health_approval_delay_days < 1:
                raise ValidationError(
                    _("Deal-health thresholds must be at least one day.")
                )

    def action_save(self):
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
        for fname, (key, _default) in POLICY_PARAMETERS.items():
            params.set_param(key, self[fname])
        self._df_recompute_governance()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Governance settings saved"),
                "message": _(
                    "Open quotations have been re-scored against the new "
                    "thresholds."
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _df_recompute_governance(self):
        """Re-score open deals against the thresholds just saved.

        df_effective_ceiling, df_excess_points and the order-level risk fields
        are STORED computes, and neither threshold appears in their
        @api.depends - they cannot, since an ir.config_parameter is not a
        field. Odoo therefore never recomputes them on its own, so without
        this a saved threshold changed nothing anybody could see: existing
        quotations kept the risk level the old boundary gave them, and the
        setting looked broken. Same reasoning, and the same add_to_compute
        mechanism, as the 17.0.1.5.0 migration.

        Scoped to still-open quotations: a confirmed or cancelled order's
        governance record is history and is not re-judged by a rule written
        afterwards.
        """
        env = self.env
        orders = env["sale.order"].sudo().search([("state", "in", ("draft", "sent"))])
        lines = orders.order_line.filtered(lambda l: l.product_id)
        if lines:
            for fname in ("df_effective_ceiling", "df_excess_points"):
                env.add_to_compute(lines._fields[fname], lines)
            lines.flush_recordset(["df_effective_ceiling", "df_excess_points"])
        if orders:
            for fname in (
                "df_blended_risk_score",
                "df_risk_level",
                "df_risk_summary",
            ):
                env.add_to_compute(orders._fields[fname], orders)
            orders.flush_recordset(
                ["df_blended_risk_score", "df_risk_level", "df_risk_summary"]
            )
