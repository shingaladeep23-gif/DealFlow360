from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dealflow_risk_high_min = fields.Float(
        string="Send to finance above",
        config_parameter="dealflow.risk_high_min",
        default=40.0,
        help="How far over the discount limit a quotation must go before "
        "finance has to approve it as well as a sales manager. At or below "
        "this score, a sales manager alone can approve it. Only this "
        "boundary is configurable; the scoring itself lives in code.",
    )
    dealflow_default_max_discount = fields.Float(
        string="Default discount limit (%)",
        config_parameter="dealflow.default_max_discount",
        default=5.0,
        help="The discount limit that applies to a line when neither the "
        "customer's tier nor the product's category sets one. A tier or "
        "category left at 0 counts as UNSET, not as a 0% ceiling - otherwise "
        "every quotation to a customer with no tier yet would need approval.",
    )
    dealflow_health_stalled_days = fields.Integer(
        string="Call a deal stalled after (days)",
        config_parameter="dealflow.health_stalled_days",
        default=7,
        help="DEC-005: a deal with no activity beyond this many days starts "
        "accruing the 'stalled' deal-health penalty.",
    )
    dealflow_health_approval_delay_days = fields.Integer(
        string="Approval Delay Threshold (days)",
        config_parameter="dealflow.health_approval_delay_days",
        default=2,
        help="DEC-005: an approval step pending beyond this many days starts "
        "accruing the 'approval delay' deal-health penalty.",
    )
