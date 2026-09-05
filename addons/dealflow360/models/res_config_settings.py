from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dealflow_risk_high_min = fields.Float(
        string="HIGH Risk Threshold",
        config_parameter="dealflow.risk_high_min",
        default=40.0,
        help="DEC-010: blended risk scores above this value route HIGH "
        "(Sales Manager then Finance); at or below it (and above zero) "
        "routes MEDIUM (Sales Manager only). The scoring formula itself "
        "(DEC-003) stays in code - only this boundary is admin-configurable "
        "data, per problem statement section A3.",
    )
