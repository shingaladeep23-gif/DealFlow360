from odoo import fields, models


class DealflowDiscountTier(models.Model):
    _name = "dealflow.discount.tier"
    _description = "Customer Discount Tier"
    _order = "max_discount"

    name = fields.Char(required=True)
    max_discount = fields.Float(
        string="Max Discount (%)",
        required=True,
        help="General discount ceiling granted to customers in this tier.",
    )
    partner_ids = fields.One2many("res.partner", "df_tier_id", string="Customers")

    _sql_constraints = [
        (
            "max_discount_range",
            "CHECK(max_discount >= 0 AND max_discount <= 100)",
            "Max discount must be between 0 and 100.",
        ),
    ]


class DealflowCategoryLimit(models.Model):
    _name = "dealflow.category.limit"
    _description = "Product Category Discount Limit"
    _order = "max_discount"

    category_id = fields.Many2one(
        "product.category", required=True, ondelete="cascade"
    )
    max_discount = fields.Float(
        string="Max Discount (%)",
        required=True,
        help="Discount ceiling for products in this category, regardless of customer tier.",
    )

    _sql_constraints = [
        (
            "category_unique",
            "UNIQUE(category_id)",
            "A discount limit already exists for this category.",
        ),
        (
            "max_discount_range",
            "CHECK(max_discount >= 0 AND max_discount <= 100)",
            "Max discount must be between 0 and 100.",
        ),
    ]
