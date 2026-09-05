from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    df_tier_id = fields.Many2one(
        "dealflow.discount.tier",
        string="Discount Tier",
        help="Customer's discount tier, sets the general discount ceiling used "
        "by the blended discount risk engine.",
    )
