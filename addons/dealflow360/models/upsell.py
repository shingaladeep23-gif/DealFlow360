from odoo import _, api, fields, models
from odoo.exceptions import UserError

CO_PURCHASE_WEIGHT = 5.0
PROMOTION_BONUS = 10.0


class DealflowUpsellRule(models.Model):
    _name = "dealflow.upsell.rule"
    _description = "DealFlow360 Upsell/Cross-sell Rule (DF-008)"
    _order = "score desc"

    product_id = fields.Many2one(
        "product.product",
        string="Trigger Product",
        required=True,
        index=True,
        help="When this product is on the quotation, suggested_product_id "
        "becomes a candidate recommendation.",
    )
    suggested_product_id = fields.Many2one(
        "product.product", string="Suggested Product", required=True, index=True
    )
    score = fields.Float(
        string="Base Score",
        default=50.0,
        help="Admin-curated ranking weight for this pairing. Combined at "
        "recommendation time with co-purchase history and the promotion "
        "bonus - see sale.order.get_upsell_recommendations().",
    )
    reason = fields.Char(
        string="Reason",
        required=True,
        help="Human-readable justification shown in the upsell panel, e.g. "
        "'Frequently paired with laptops'.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "no_self_pairing",
            "CHECK(product_id != suggested_product_id)",
            "A product cannot be its own upsell suggestion.",
        ),
        (
            "unique_pairing",
            "UNIQUE(product_id, suggested_product_id)",
            "This trigger/suggestion pairing already exists.",
        ),
    ]


class SaleOrderUpsell(models.Model):
    _inherit = "sale.order"

    def _df_upsell_reference_price(self, product):
        """Same pricelist-aware reference price used by DEC-009's governance
        compute (sale_order_line._df_reference_price) - never the raw
        catalogue price when a pricelist applies, so the projected margin
        this feeds is consistent with the rest of the order."""
        self.ensure_one()
        if self.pricelist_id:
            return self.pricelist_id._get_product_price(
                product, 1.0, uom=product.uom_id, date=self.date_order
            )
        return product.list_price

    def get_upsell_recommendations(self, limit=5):
        """DF-008: deterministic, rule-driven upsell/cross-sell ranking -
        no ML, no randomness. Combines three real signals:
          1. admin-curated dealflow.upsell.rule pairings (score)
          2. co-purchase history: real confirmed sale.order.line rows from
             OTHER orders that also contain a product in this cart
             (CO_PURCHASE_WEIGHT per distinct trigger)
          3. a fixed bonus for product.template.df_is_promoted

        Candidates whose OWN standalone margin falls below their configured
        df_min_margin are excluded entirely (that field's own docstring:
        "upsell suggestions below this threshold are excluded").

        projected_margin_pct is the order's df_margin_pct recomputed as if
        one unit of the candidate were added at its real pricelist/list
        reference price - a genuine projection, not an estimate. Returns
        [{product_id, product_name, score, projected_margin_pct,
        margin_delta_pct, reason}], ranked by score desc.
        """
        self.ensure_one()
        lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
        cart_products = lines.mapped("product_id")
        if not cart_products:
            return []

        candidates = {}

        def _bump(product, score, reason):
            if product.id in cart_products.ids:
                return
            bucket = candidates.setdefault(
                product.id, {"product": product, "score": 0.0, "reasons": []}
            )
            bucket["score"] += score
            if reason not in bucket["reasons"]:
                bucket["reasons"].append(reason)

        rules = self.env["dealflow.upsell.rule"].search(
            [("product_id", "in", cart_products.ids)]
        )
        for rule in rules:
            _bump(rule.suggested_product_id, rule.score, rule.reason)

        sibling_order_ids = (
            self.env["sale.order.line"]
            .search(
                [
                    ("order_id.state", "in", ("sale", "done")),
                    ("order_id", "!=", self.id),
                    ("product_id", "in", cart_products.ids),
                ]
            )
            .mapped("order_id")
            .ids
        )
        if sibling_order_ids:
            co_lines = self.env["sale.order.line"].search(
                [
                    ("order_id", "in", sibling_order_ids),
                    ("product_id", "not in", cart_products.ids),
                    ("display_type", "=", False),
                ]
            )
            for line in co_lines:
                _bump(
                    line.product_id,
                    CO_PURCHASE_WEIGHT,
                    _("Frequently bought together with items in this quotation"),
                )

        if not candidates:
            return []

        order_revenue = sum(lines.mapped("price_subtotal"))
        order_cost = sum(
            l.product_uom_qty * (l.product_id.standard_price or 0.0) for l in lines
        )
        current_margin_pct = self.df_margin_pct

        results = []
        for bucket in candidates.values():
            product = bucket["product"]
            score = bucket["score"]
            reasons = list(bucket["reasons"])
            if product.df_is_promoted:
                score += PROMOTION_BONUS
                reasons.append(_("Currently promoted"))

            own_margin_pct = (
                (product.list_price - product.standard_price) / product.list_price * 100.0
                if product.list_price
                else 0.0
            )
            if product.df_min_margin and own_margin_pct < product.df_min_margin:
                continue

            ref_price = self._df_upsell_reference_price(product)
            new_revenue = order_revenue + ref_price
            new_cost = order_cost + (product.standard_price or 0.0)
            projected_margin_pct = (
                (new_revenue - new_cost) / new_revenue * 100.0 if new_revenue else 0.0
            )

            results.append(
                {
                    "product_id": product.id,
                    "product_name": product.display_name,
                    "score": score,
                    "projected_margin_pct": projected_margin_pct,
                    "margin_delta_pct": projected_margin_pct - current_margin_pct,
                    "reason": "; ".join(reasons),
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def action_add_upsell_line(self, product_id, qty=1.0):
        """AT-05's 'Add to Quote': writes a REAL sale.order.line (native
        price_unit compute handles pricelist/tier pricing) so the order
        total and every DF-002/DF-003 governance/margin field recomputes
        immediately, exactly as if the rep had added the line by hand."""
        self.ensure_one()
        product = self.env["product.product"].browse(product_id)
        if not product.exists():
            raise UserError(_("Unknown product."))
        line = self.env["sale.order.line"].create(
            {
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
            }
        )
        return line.id
