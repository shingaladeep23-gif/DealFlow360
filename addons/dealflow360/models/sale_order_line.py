from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    df_effective_ceiling = fields.Float(
        string="Effective Ceiling (%)",
        compute="_compute_df_governance",
        store=True,
        help="min(customer tier ceiling, product category ceiling) per DEC-003 "
        "- the maximum manual discount this line may carry before it counts as excess.",
    )
    df_excess_points = fields.Float(
        string="Excess (points)",
        compute="_compute_df_governance",
        store=True,
        help="Percentage points by which the rep's discount exceeds "
        "df_effective_ceiling. Measured against the pricelist price, not the "
        "catalogue list price, per DEC-009 - never double-count a pricelist "
        "reduction as rep discount.",
    )
    df_margin_pct = fields.Float(
        string="Margin (%)",
        compute="_compute_df_margin_pct",
        store=True,
        help="Live line margin: (price_subtotal - cost) / price_subtotal, using "
        "the product's real standard_price as cost.",
    )

    def _df_reference_price(self):
        """The price this line's tier should pay before any additional manual
        discount: the order's pricelist price, or the catalogue list price if
        no pricelist applies (DEC-009 degrade path). Governance excess must be
        measured against this, never against the catalogue price directly -
        that would double-count the pricelist's own reduction as a rep discount.
        """
        self.ensure_one()
        if not self.product_id:
            return 0.0
        pricelist = self.order_id.pricelist_id
        if pricelist:
            return pricelist._get_product_price(
                self.product_id,
                self.product_uom_qty or 1.0,
                uom=self.product_uom or self.product_id.uom_id,
                date=self.order_id.date_order,
            )
        return self.product_id.list_price

    @api.depends(
        "discount",
        "price_unit",
        "product_uom_qty",
        "product_uom",
        "product_id",
        "product_id.list_price",
        "product_id.categ_id.df_max_discount",
        "order_id.partner_id.df_tier_id.max_discount",
        "order_id.pricelist_id",
    )
    def _compute_df_governance(self):
        for line in self:
            if not line.product_id:
                line.df_effective_ceiling = 0.0
                line.df_excess_points = 0.0
                continue

            tier = line.order_id.partner_id.df_tier_id
            tier_ceiling = tier.max_discount if tier else 0.0
            category_ceiling = line.product_id.categ_id.df_max_discount
            line.df_effective_ceiling = min(tier_ceiling, category_ceiling)

            reference_price = line._df_reference_price()
            actual_unit_price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            if reference_price:
                rep_discount_pct = max(
                    0.0,
                    (reference_price - actual_unit_price) / reference_price * 100.0,
                )
            else:
                rep_discount_pct = 0.0
            line.df_excess_points = max(
                0.0, rep_discount_pct - line.df_effective_ceiling
            )

    @api.depends("price_subtotal", "product_uom_qty", "product_id.standard_price")
    def _compute_df_margin_pct(self):
        for line in self:
            cost = (line.product_uom_qty or 0.0) * (
                line.product_id.standard_price or 0.0
            )
            if line.price_subtotal:
                line.df_margin_pct = (
                    (line.price_subtotal - cost) / line.price_subtotal * 100.0
                )
            else:
                line.df_margin_pct = 0.0
