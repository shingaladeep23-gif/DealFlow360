from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSaleOrderGovernance(TransactionCase):
    """DF-002: sale.order/sale.order.line discount governance, margin and
    pipeline stage, validated against the problem statement's own worked
    example and the seeded demo data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.beta = cls.env["res.partner"].search(
            [("name", "=", "Beta Industries")], limit=1
        )
        cls.probook = cls.env["product.product"].search(
            [("name", "=", "ProBook Laptop")], limit=1
        )
        cls.setup_service = cls.env["product.product"].search(
            [("name", "=", "Onsite Setup Service")], limit=1
        )

    def _make_order(self, partner, product, discount):
        order = self.env["sale.order"].create({"partner_id": partner.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "discount": discount,
            }
        )
        return order, line

    def test_worked_example_probook_within_ceiling(self):
        """Gold customer, ProBook (Hardware, ceiling 15) at 12% -> within limit."""
        _, line = self._make_order(self.acme, self.probook, 12.0)
        self.assertEqual(line.df_effective_ceiling, 15.0)
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)

    def test_worked_example_setup_service_over_ceiling(self):
        """Gold customer, Setup Service (Services, ceiling 10) at 18% ->
        8 points over, even though the customer's general tier ceiling is 15.
        This is the spec's canonical case."""
        _, line = self._make_order(self.acme, self.setup_service, 18.0)
        self.assertEqual(line.df_effective_ceiling, 10.0)
        self.assertAlmostEqual(line.df_excess_points, 8.0, places=6)

    def test_recompute_on_discount_change(self):
        _, line = self._make_order(self.acme, self.setup_service, 0.0)
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)
        line.write({"discount": 18.0})
        self.assertAlmostEqual(line.df_excess_points, 8.0, places=6)

    def test_recompute_on_quantity_and_price_change(self):
        order, line = self._make_order(self.acme, self.probook, 12.0)
        cost = self.probook.standard_price
        line.write({"product_uom_qty": 2})
        expected_margin = (line.price_subtotal - 2 * cost) / line.price_subtotal * 100.0
        self.assertAlmostEqual(line.df_margin_pct, expected_margin, places=4)

        original_margin = line.df_margin_pct
        line.write({"price_unit": line.price_unit * 2})
        self.assertNotEqual(line.df_margin_pct, original_margin)

    def test_tier_stricter_than_category(self):
        """Beta Industries is Silver (10%); ProBook's Hardware ceiling is 15%.
        The tier is the binding constraint here."""
        _, line = self._make_order(self.beta, self.probook, 8.0)
        self.assertEqual(line.df_effective_ceiling, 10.0)
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)

        line.write({"discount": 13.0})
        self.assertAlmostEqual(line.df_excess_points, 3.0, places=6)

    def test_category_stricter_than_tier(self):
        """Acme is Gold (15%); Setup Service's Services ceiling is 10%.
        The category is the binding constraint here (already exercised as the
        canonical worked example above; asserted again explicitly for the
        min(tier, category) requirement)."""
        _, line = self._make_order(self.acme, self.setup_service, 10.0)
        self.assertEqual(line.df_effective_ceiling, 10.0)
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)

    def test_margin_is_real_not_placeholder(self):
        _, line = self._make_order(self.acme, self.probook, 0.0)
        expected = (
            (line.price_subtotal - line.product_uom_qty * self.probook.standard_price)
            / line.price_subtotal
            * 100.0
        )
        self.assertAlmostEqual(line.df_margin_pct, expected, places=4)
        self.assertNotEqual(line.df_margin_pct, 0.0)

    def test_pipeline_stage_draft_and_confirmed(self):
        order, _ = self._make_order(self.acme, self.probook, 0.0)
        self.assertEqual(order.df_pipeline_stage, "draft")
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.df_pipeline_stage, "confirmed")
