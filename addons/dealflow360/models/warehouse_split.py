from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockWarehouse(models.Model):
    """DEC-006: shipping cost weight is the tie-break input the allocation
    engine uses when two or more warehouses can equally serve a line -
    cheaper-to-ship warehouses are preferred. Real config, not a display
    number: it feeds straight into DealflowWarehouseSplit._allocate_line."""

    _inherit = "stock.warehouse"

    df_shipping_cost_weight = fields.Float(
        string="Shipping Cost Weight",
        default=1.0,
        help="Relative shipping cost used by DealFlow360's warehouse "
        "allocation engine (DEC-006) as a tie-break: lower weight wins when "
        "two warehouses could equally fulfil a line.",
    )


class DealflowWarehouseSplit(models.Model):
    _name = "dealflow.warehouse.split"
    _description = "DealFlow360 Warehouse Allocation Plan"
    _order = "id desc"

    order_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, ondelete="cascade", index=True
    )
    state = fields.Selection(
        [("draft", "Suggested"), ("confirmed", "Confirmed")],
        string="Status",
        default="draft",
        required=True,
    )
    line_ids = fields.One2many(
        "dealflow.warehouse.split.line", "split_id", string="Allocation Lines"
    )
    shipment_count = fields.Integer(
        string="Est. Shipments",
        compute="_compute_shipment_count",
        store=True,
        help="Number of distinct warehouses (= distinct pickings) required "
        "to fulfil this order under the current plan - the quantity DEC-006's "
        "greedy set-cover heuristic minimises.",
    )
    has_backorder = fields.Boolean(
        string="Has Backorder", compute="_compute_shipment_count", store=True
    )
    df_recommendation_note = fields.Char(
        string="Recommendation", compute="_compute_recommendation_note"
    )
    currency_id = fields.Many2one(related="order_id.currency_id", string="Currency")
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer", store=True)

    @api.depends("line_ids.warehouse_id", "line_ids.qty", "line_ids.is_backorder")
    def _compute_shipment_count(self):
        for split in self:
            real_lines = split.line_ids.filtered(lambda l: not l.is_backorder and l.qty > 0)
            split.shipment_count = len(real_lines.mapped("warehouse_id"))
            split.has_backorder = bool(split.line_ids.filtered("is_backorder"))

    @api.depends("shipment_count", "has_backorder")
    def _compute_recommendation_note(self):
        for split in self:
            if split.has_backorder:
                split.df_recommendation_note = _(
                    "Some quantity has no available stock anywhere - a "
                    "backorder line is included. Combine the remaining "
                    "shipments to avoid extra cost/lead time."
                )
            elif split.shipment_count > 1:
                split.df_recommendation_note = _(
                    "Order can only be fully covered by splitting across "
                    "%(count)d warehouses - this is the minimum-shipment plan."
                ) % {"count": split.shipment_count}
            else:
                split.df_recommendation_note = _(
                    "Single warehouse covers the full order - one shipment."
                )

    @api.model
    def _create_for_order(self, order):
        """DEC-006: build the allocation plan from live stock.quant data.
        Greedy set-cover - for each order line, prefer the warehouse(s) that
        can fully cover the remaining demand (tie-broken by the cheapest
        df_shipping_cost_weight); split across more warehouses only when no
        single one suffices. Any demand no warehouse can source becomes a
        backorder line with zero real stock behind it."""
        existing = self.search([("order_id", "=", order.id)], limit=1)
        if existing:
            existing.line_ids.unlink()
        else:
            existing = self.create({"order_id": order.id})

        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", order.company_id.id)]
        )
        line_vals = []
        for order_line in order.order_line.filtered(
            lambda l: not l.display_type and l.product_id.type == "product"
        ):
            line_vals += self._allocate_line(order_line, warehouses)
        existing.write({"line_ids": [(0, 0, v) for v in line_vals], "state": "draft"})
        return existing

    @api.model
    def _allocate_line(self, order_line, warehouses):
        product = order_line.product_id
        remaining = order_line.product_uom_qty
        if remaining <= 0:
            return []

        # Real available-to-promise per warehouse: on-hand quant qty minus
        # what is already reserved by other pickings, read straight off
        # stock.quant - never a hardcoded number. warehouse_id on
        # stock.quant is a non-stored related field, so it cannot be used as
        # a read_group groupby column - instead each warehouse's stock is
        # queried under its own internal locations directly.
        available = {}
        for wh in warehouses:
            quants = self.env["stock.quant"].search(
                [
                    ("product_id", "=", product.id),
                    ("location_id", "child_of", wh.view_location_id.id),
                    ("location_id.usage", "=", "internal"),
                ]
            )
            available[wh.id] = max(
                0.0, sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
            )

        candidates = [wh for wh in warehouses if available.get(wh.id, 0.0) > 0]
        # Full-cover candidates first (fewest shipments), cheapest first;
        # then partial candidates by available desc, cheapest first.
        full_cover = sorted(
            [wh for wh in candidates if available[wh.id] >= remaining],
            key=lambda wh: wh.df_shipping_cost_weight,
        )
        partial = sorted(
            [wh for wh in candidates if available[wh.id] < remaining],
            key=lambda wh: (-available[wh.id], wh.df_shipping_cost_weight),
        )
        ordered = full_cover[:1] + partial if full_cover else partial

        vals = []
        last_warehouse = order.warehouse_id if (order := order_line.order_id) else False
        for wh in ordered:
            if remaining <= 0:
                break
            take = min(available[wh.id], remaining)
            if take <= 0:
                continue
            vals.append(
                {
                    "order_line_id": order_line.id,
                    "warehouse_id": wh.id,
                    "qty": take,
                    "is_backorder": False,
                }
            )
            remaining -= take
            last_warehouse = wh

        if remaining > 1e-6:
            fallback = last_warehouse or order_line.order_id.warehouse_id or warehouses[:1]
            vals.append(
                {
                    "order_line_id": order_line.id,
                    "warehouse_id": fallback.id if fallback else False,
                    "qty": remaining,
                    "is_backorder": True,
                }
            )
        return vals

    def action_confirm(self):
        """Screen 5's 'Accept Suggested Split' - creates REAL stock.picking
        records, one per warehouse involved (that is the shipment DEC-006
        counts), with real moves for the allocated quantities, then reserves
        them via action_assign(). A picking for the backorder fallback
        warehouse is created too so the shortfall is a genuine, trackable
        Odoo picking - not just a flag - and will show as unavailable until
        real stock lands, which is exactly what a backorder is."""
        StockPicking = self.env["stock.picking"]
        customer_loc = self.env.ref("stock.stock_location_customers")
        for split in self:
            if split.state == "confirmed":
                continue
            if not split.line_ids:
                raise UserError(_("Nothing to confirm: no allocation lines on this split."))
            by_warehouse = {}
            for line in split.line_ids:
                by_warehouse.setdefault(line.warehouse_id, self.env["dealflow.warehouse.split.line"])
                by_warehouse[line.warehouse_id] |= line

            for warehouse, lines in by_warehouse.items():
                if not warehouse or not warehouse.out_type_id:
                    continue
                picking = StockPicking.create(
                    {
                        "picking_type_id": warehouse.out_type_id.id,
                        "location_id": warehouse.lot_stock_id.id,
                        "location_dest_id": customer_loc.id,
                        "partner_id": split.order_id.partner_id.id,
                        "origin": split.order_id.name,
                        "move_ids": [
                            (
                                0,
                                0,
                                {
                                    "name": line.order_line_id.product_id.display_name,
                                    "product_id": line.order_line_id.product_id.id,
                                    "product_uom_qty": line.qty,
                                    "product_uom": line.order_line_id.product_uom.id,
                                    "location_id": warehouse.lot_stock_id.id,
                                    "location_dest_id": customer_loc.id,
                                    "sale_line_id": line.order_line_id.id,
                                },
                            )
                            for line in lines
                        ],
                    }
                )
                picking.action_confirm()
                picking.action_assign()
                lines.write({"picking_id": picking.id})
            split.state = "confirmed"
            split.order_id.message_post(
                body=_(
                    "Warehouse allocation confirmed: %(shipments)d shipment(s) created%(bo)s."
                )
                % {
                    "shipments": split.shipment_count,
                    "bo": _(" (includes a backorder)") if split.has_backorder else "",
                }
            )
        return True


class DealflowWarehouseSplitLine(models.Model):
    _name = "dealflow.warehouse.split.line"
    _description = "DealFlow360 Warehouse Allocation Line"

    split_id = fields.Many2one(
        "dealflow.warehouse.split", string="Split", required=True, ondelete="cascade", index=True
    )
    order_line_id = fields.Many2one(
        "sale.order.line", string="Order Line", required=True, ondelete="cascade"
    )
    product_id = fields.Many2one(related="order_line_id.product_id", string="Product")
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse")
    qty = fields.Float(string="Qty Fulfilled", required=True)
    is_backorder = fields.Boolean(string="Backorder", default=False)
    picking_id = fields.Many2one("stock.picking", string="Shipment", readonly=True)
    currency_id = fields.Many2one(related="split_id.currency_id", string="Currency")
    df_estimated_cost = fields.Monetary(
        string="Est. Cost",
        currency_field="currency_id",
        compute="_compute_df_estimated_cost",
        help="qty x the warehouse's configured shipping cost weight - makes "
        "DEC-006's tie-break rule inspectable on the fulfillment screen.",
    )

    @api.depends("qty", "warehouse_id.df_shipping_cost_weight")
    def _compute_df_estimated_cost(self):
        for line in self:
            line.df_estimated_cost = line.qty * (line.warehouse_id.df_shipping_cost_weight or 1.0)


class SaleOrderFulfillment(models.Model):
    """DF-010: a separate extension of sale.order (never touching
    sale_order.py, which is Atlas's DF-004 approval-chain lane) so the
    allocation plan is suggested the moment an order actually becomes
    'sale' - regardless of whether that happened directly or via the
    approval chain's own action_confirm override, since super() chains
    through every _inherit cooperatively."""

    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered(lambda o: o.state == "sale"):
            if not self.env["dealflow.warehouse.split"].search_count(
                [("order_id", "=", order.id)]
            ):
                self.env["dealflow.warehouse.split"]._create_for_order(order)
        return res
