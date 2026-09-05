from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    df_max_discount = fields.Float(
        string="Max Discount (%)",
        help="Discount ceiling for products in this category, regardless of "
        "customer tier. Mirrored onto dealflow.category.limit.",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    df_is_recurring = fields.Boolean(
        string="Recurring",
        help="Sold as a recurring subscription line rather than a one-time sale. "
        "The dealflow.recurring.plan link is added in a later phase once the "
        "billing engine model exists.",
    )
    df_is_promoted = fields.Boolean(
        string="Promoted",
        help="Eligible for upsell/cross-sell recommendation as a featured item.",
    )
    df_min_margin = fields.Float(
        string="Min Margin (%)",
        help="Minimum acceptable margin percentage; upsell suggestions below "
        "this threshold are excluded.",
    )
