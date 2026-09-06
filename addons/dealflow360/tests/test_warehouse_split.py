from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWarehouseSplit(TransactionCase):
    """DF-010: DEC-006 greedy multi-warehouse allocation over real
    stock.quant, real stock.picking creation, manual override honoured,
    backorder + consolidation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.company = cls.env.ref("base.main_company")

    def _make_warehouse(self, name, code, cost_weight=1.0):
        wh = self.env["stock.warehouse"].create(
            {"name": name, "code": code, "company_id": self.company.id}
        )
        wh.df_shipping_cost_weight = cost_weight
        return wh

    def _make_storable(self, name, list_price=100.0):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": self.hardware.id,
                "type": "product",
                "list_price": list_price,
                "standard_price": list_price * 0.6,
            }
        )

    def _stock(self, product, warehouse, qty):
        self.env["stock.quant"].sudo().create(
            {
                "product_id": product.id,
                "location_id": warehouse.lot_stock_id.id,
                "quantity": qty,
            }
        )

    def _make_order(self, product, qty):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self.env["sale.order.line"].create(
            {"order_id": order.id, "product_id": product.id, "product_uom_qty": qty}
        )
        return order

    # -- full coverage by one warehouse -----------------------------------

    def test_single_warehouse_can_fully_cover_no_split(self):
        wh_a = self._make_warehouse("Split WH A", "SWA")
        wh_b = self._make_warehouse("Split WH B", "SWB")
        product = self._make_storable("Split Product A")
        self._stock(product, wh_a, 20)
        self._stock(product, wh_b, 20)
        order = self._make_order(product, 5)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertEqual(split.shipment_count, 1)
        self.assertFalse(split.has_backorder)
        self.assertEqual(len(split.line_ids), 1)
        self.assertAlmostEqual(sum(split.line_ids.mapped("qty")), 5.0, places=4)

    # -- order too big for any single warehouse splits across two ---------

    def test_order_exceeding_any_single_warehouse_splits_across_two(self):
        """Mirrors the seeded ProBook scenario (demo/demo_data.py): 6 + 4 =
        10 fragmented, no single warehouse can cover a 10-unit order."""
        wh_a = self._make_warehouse("Split WH C", "SWC")
        wh_b = self._make_warehouse("Split WH D", "SWD")
        product = self._make_storable("Split Product B")
        self._stock(product, wh_a, 6)
        self._stock(product, wh_b, 4)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertEqual(split.shipment_count, 2)
        self.assertFalse(split.has_backorder)
        qty_by_wh = {line.warehouse_id: line.qty for line in split.line_ids}
        self.assertAlmostEqual(qty_by_wh[wh_a], 6.0, places=4)
        self.assertAlmostEqual(qty_by_wh[wh_b], 4.0, places=4)

    # -- shortfall becomes a real backorder, both directions ---------------

    def test_shortfall_becomes_backorder_when_total_stock_insufficient(self):
        wh_a = self._make_warehouse("Split WH E", "SWE")
        product = self._make_storable("Split Product C")
        self._stock(product, wh_a, 3)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertTrue(split.has_backorder)
        backorder_line = split.line_ids.filtered("is_backorder")
        self.assertEqual(len(backorder_line), 1)
        self.assertAlmostEqual(backorder_line.qty, 7.0, places=4)
        fulfilled_line = split.line_ids - backorder_line
        self.assertAlmostEqual(fulfilled_line.qty, 3.0, places=4)

    def test_sufficient_stock_produces_no_backorder(self):
        """Other direction of the previous test: same shape, enough total
        stock this time - has_backorder must flip to False, not just
        'mostly false'."""
        wh_a = self._make_warehouse("Split WH F", "SWF")
        product = self._make_storable("Split Product D")
        self._stock(product, wh_a, 10)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertFalse(split.has_backorder)

    # -- DEC-006 shipping cost weight tie-break ----------------------------

    def test_tie_break_prefers_lower_shipping_cost_weight(self):
        """Two warehouses can each fully cover the line alone - DEC-006
        says prefer the lower df_shipping_cost_weight."""
        cheap = self._make_warehouse("Split WH G", "SWG", cost_weight=1.0)
        expensive = self._make_warehouse("Split WH H", "SWH", cost_weight=5.0)
        product = self._make_storable("Split Product E")
        self._stock(product, cheap, 10)
        self._stock(product, expensive, 10)
        order = self._make_order(product, 5)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertEqual(split.line_ids.warehouse_id, cheap)

    def test_tie_break_reverses_when_weight_reverses(self):
        """Other direction: swap which warehouse is cheaper and the choice
        must follow, proving this is genuinely reading the weight field and
        not just always preferring the first/lowest-id warehouse."""
        expensive = self._make_warehouse("Split WH G2", "SG2", cost_weight=5.0)
        cheap = self._make_warehouse("Split WH H2", "SH2", cost_weight=1.0)
        product = self._make_storable("Split Product E2")
        self._stock(product, expensive, 10)
        self._stock(product, cheap, 10)
        order = self._make_order(product, 5)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertEqual(split.line_ids.warehouse_id, cheap)

    # -- manual override is honoured on confirm ----------------------------

    def test_manual_override_is_honoured_by_confirm(self):
        wh_a = self._make_warehouse("Split WH I", "SWI")
        wh_b = self._make_warehouse("Split WH J", "SWJ")
        product = self._make_storable("Split Product F")
        self._stock(product, wh_a, 10)
        self._stock(product, wh_b, 10)
        order = self._make_order(product, 5)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        self.assertEqual(split.line_ids.warehouse_id, wh_a)  # system suggestion

        # User manually reassigns to wh_b before accepting.
        split.line_ids.write({"warehouse_id": wh_b.id})
        split.action_confirm()

        self.assertEqual(split.state, "confirmed")
        self.assertEqual(len(split.picking_ids), 1)
        self.assertIn(wh_b.lot_stock_id, split.picking_ids.mapped("location_id"))

    # -- action_confirm creates REAL stock.picking + stock.move records ----

    def test_action_confirm_creates_real_pickings_per_warehouse(self):
        wh_a = self._make_warehouse("Split WH K", "SWK")
        wh_b = self._make_warehouse("Split WH L", "SWL")
        product = self._make_storable("Split Product G")
        self._stock(product, wh_a, 6)
        self._stock(product, wh_b, 4)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        split.action_confirm()

        self.assertEqual(split.state, "confirmed")
        self.assertEqual(len(split.picking_ids), 2)
        for picking in split.picking_ids:
            self.assertEqual(picking.df_split_id, split)
            self.assertNotEqual(picking.state, "draft")
        self.assertAlmostEqual(
            sum(split.picking_ids.mapped("move_ids.product_uom_qty")), 10.0, places=4
        )

    def test_cannot_regenerate_a_confirmed_split(self):
        wh_a = self._make_warehouse("Split WH M", "SWM")
        product = self._make_storable("Split Product H")
        self._stock(product, wh_a, 10)
        order = self._make_order(product, 5)
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        split.action_confirm()

        with self.assertRaises(UserError):
            split.action_generate_split()

    def test_cannot_confirm_without_any_allocation(self):
        product = self._make_storable("Split Product H2")
        order = self._make_order(product, 5)
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})

        with self.assertRaises(UserError):
            split.action_confirm()

    # -- service lines never enter fulfillment ------------------------------

    def test_service_only_order_produces_no_fulfillable_lines(self):
        service = self.env["product.product"].create(
            {
                "name": "Split Service",
                "categ_id": self.hardware.id,
                "type": "service",
                "list_price": 100.0,
            }
        )
        order = self._make_order(service, 3)
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        self.assertFalse(split.line_ids)

    # -- backorder consolidation once stock arrives -------------------------

    def test_consolidate_backorder_once_stock_arrives(self):
        wh_a = self._make_warehouse("Split WH N", "SWN")
        product = self._make_storable("Split Product I")
        self._stock(product, wh_a, 3)
        order = self._make_order(product, 10)
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        split.action_confirm()

        backorder = split.line_ids.filtered("is_backorder")
        self.assertAlmostEqual(backorder.qty, 7.0, places=4)

        # Stock arrives.
        self._stock(product, wh_a, 7)
        split.action_consolidate_backorder()

        remaining_backorder = split.line_ids.filtered(
            lambda l: l.is_backorder and l.qty > 1e-6
        )
        self.assertFalse(remaining_backorder)
        self.assertEqual(len(split.picking_ids), 2)  # original + consolidation delivery
        self.assertAlmostEqual(
            sum(split.picking_ids.mapped("move_ids.product_uom_qty")), 10.0, places=4
        )

    def test_consolidate_backorder_raises_when_nothing_arrived(self):
        wh_a = self._make_warehouse("Split WH O", "SWO")
        product = self._make_storable("Split Product J")
        self._stock(product, wh_a, 3)
        order = self._make_order(product, 10)
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()
        split.action_confirm()

        with self.assertRaises(UserError):
            split.action_consolidate_backorder()

    # -- confirming the sale order auto-proposes a split --------------------

    def test_confirming_order_auto_generates_split_proposal(self):
        wh_a = self._make_warehouse("Split WH P", "SWP")
        product = self._make_storable("Split Product K")
        self._stock(product, wh_a, 10)
        order = self._make_order(product, 5)
        order.action_confirm()

        self.assertEqual(len(order.df_split_ids), 1)
        self.assertEqual(order.df_split_ids.state, "draft")
        self.assertTrue(order.df_split_ids.line_ids)

    def test_confirming_order_cancels_the_native_single_warehouse_delivery(self):
        """The native sale_stock auto-delivery (against order.warehouse_id
        alone) must not survive alongside our split - otherwise stock would
        be double-reserved and there would be two uncoordinated sets of
        shipments for one order (see the comment on SaleOrderSplit.action_
        confirm)."""
        wh_a = self._make_warehouse("Split WH Q", "SWQ")
        product = self._make_storable("Split Product L")
        self._stock(product, wh_a, 10)
        order = self._make_order(product, 5)
        order.write({"warehouse_id": wh_a.id})
        order.action_confirm()

        stray = order.picking_ids.filtered(
            lambda p: not p.df_split_id and p.state not in ("done", "cancel")
        )
        self.assertFalse(
            stray, "native single-warehouse delivery should have been cancelled"
        )

    # -- B6: the screen has to show an estimated SHIPMENT COST --------------

    def test_estimated_cost_is_money_and_moves_with_quantity(self):
        """The Cost column used to echo df_shipping_cost_weight, which is 1.00
        on every warehouse out of the box - so every row of every split read
        1.00 regardless of what was being shipped, and answered no question at
        all."""
        wh = self._make_warehouse("Cost WH A", "CWA")
        wh.write({"df_shipping_base_cost": 20.0, "df_shipping_cost_per_unit": 2.0})
        product = self._make_storable("Cost Product A")
        self._stock(product, wh, 50)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        line = split.line_ids
        self.assertAlmostEqual(line.df_estimated_cost, 20.0, places=2)  # 10 x 2.00
        # One shipment: its fixed cost plus the per-unit cost of what it carries.
        self.assertAlmostEqual(split.df_estimated_shipping_cost, 40.0, places=2)

    def test_a_second_warehouse_visibly_costs_more_to_ship(self):
        """DEC-006 minimizes shipment count because shipments cost money. The
        estimate has to reflect that, or the objective is invisible."""
        wh_a = self._make_warehouse("Cost WH B", "CWB")
        wh_b = self._make_warehouse("Cost WH C", "CWC", cost_weight=2.0)
        for wh in (wh_a, wh_b):
            wh.write({"df_shipping_base_cost": 20.0, "df_shipping_cost_per_unit": 1.0})
        product = self._make_storable("Cost Product B")
        self._stock(product, wh_a, 6)
        self._stock(product, wh_b, 6)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        self.assertEqual(split.shipment_count, 2)
        # Both warehouses' fixed costs are charged, and the remote one's weight
        # of 2.0 doubles its share.
        self.assertGreater(split.df_estimated_shipping_cost, 40.0)

    def test_backorder_rows_cost_nothing_until_they_ship(self):
        wh = self._make_warehouse("Cost WH D", "CWD")
        wh.write({"df_shipping_base_cost": 20.0, "df_shipping_cost_per_unit": 3.0})
        product = self._make_storable("Cost Product C")
        self._stock(product, wh, 2)
        order = self._make_order(product, 10)

        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.action_generate_split()

        backorder = split.line_ids.filtered("is_backorder")
        self.assertTrue(backorder)
        self.assertAlmostEqual(backorder.df_estimated_cost, 0.0, places=2)

    # -- B6: the consolidation prompt has to appear on its own --------------

    def test_consolidation_prompt_appears_when_stock_arrives(self):
        """B6 says the prompt "appears automatically". Nothing recomputed
        anything when stock landed, so the option only existed for a user who
        already knew to go and press the button - which is the one person who
        does not need prompting."""
        wh = self._make_warehouse("Consol WH A", "KWA")
        product = self._make_storable("Consol Product A")
        self._stock(product, wh, 2)
        order = self._make_order(product, 10)
        order.action_confirm()
        split = order.df_split_ids
        split.action_confirm()

        self.assertTrue(split.has_backorder)
        self.assertFalse(
            split.df_can_consolidate, "nothing has arrived yet"
        )

        self._stock(product, wh, 8)  # a delivery lands

        split.invalidate_recordset(["df_can_consolidate", "df_consolidatable_qty"])
        self.assertTrue(split.df_can_consolidate)
        self.assertAlmostEqual(split.df_consolidatable_qty, 8.0, places=2)

    def test_the_consolidation_cron_nudges_the_deals_owner(self):
        wh = self._make_warehouse("Consol WH B", "KWB")
        product = self._make_storable("Consol Product B")
        self._stock(product, wh, 1)
        order = self._make_order(product, 6)
        order.action_confirm()
        split = order.df_split_ids
        split.action_confirm()
        self._stock(product, wh, 5)

        messages_before = len(order.message_ids)
        self.env["dealflow.warehouse.split"]._cron_notify_consolidatable_backorders()

        order.invalidate_recordset(["message_ids"])
        self.assertGreater(len(order.message_ids), messages_before)
        self.assertTrue(split.df_consolidation_notified)

        # ...and it does not nag again on the next run.
        messages_after = len(order.message_ids)
        self.env["dealflow.warehouse.split"]._cron_notify_consolidatable_backorders()
        order.invalidate_recordset(["message_ids"])
        self.assertEqual(len(order.message_ids), messages_after)
