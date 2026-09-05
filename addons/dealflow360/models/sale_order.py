from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

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
        help="Mockup screen 3's Kanban grouping. Only 'draft' and 'confirmed' "
        "are derivable from native state today - this is a deliberate seam: "
        "DF-004's approval chain will drive pending_approval/approved, and "
        "DF-014/015's portal negotiation model will drive negotiation.",
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

    @api.depends("state")
    def _compute_df_pipeline_stage(self):
        for order in self:
            order.df_pipeline_stage = "confirmed" if order.state == "sale" else "draft"
