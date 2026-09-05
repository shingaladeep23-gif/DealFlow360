from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDiscountTierFoundation(TransactionCase):
    """DF-001 foundation checks: seeded tiers, category ceilings and the
    Acme Corp / Gold tier link the rest of the risk engine depends on."""

    def test_seeded_tiers(self):
        tiers = {
            t.name: t.max_discount
            for t in self.env["dealflow.discount.tier"].search([])
        }
        self.assertEqual(tiers.get("Bronze"), 5.0)
        self.assertEqual(tiers.get("Silver"), 10.0)
        self.assertEqual(tiers.get("Gold"), 15.0)

    def test_seeded_category_limits(self):
        """DEC-014: product.category.df_max_discount is the sole source of
        truth - no separate dealflow.category.limit model exists anymore."""
        categories = self.env["product.category"].search(
            [("name", "in", ("Hardware", "Services"))]
        )
        limits = {categ.name: categ.df_max_discount for categ in categories}
        self.assertEqual(limits.get("Hardware"), 15.0)
        self.assertEqual(limits.get("Services"), 10.0)

    def test_acme_corp_is_gold(self):
        acme = self.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        self.assertTrue(acme, "Acme Corp seed customer must exist")
        self.assertEqual(acme.df_tier_id.name, "Gold")

    def test_probook_stock_requires_split(self):
        probook = self.env["product.product"].search(
            [("name", "=", "ProBook Laptop")], limit=1
        )
        self.assertTrue(probook, "ProBook Laptop seed product must exist")

        warehouses = self.env["stock.warehouse"].search(
            [("name", "in", ("Main Warehouse", "East Depot"))]
        )
        self.assertEqual(len(warehouses), 2)

        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", probook.id),
                ("location_id", "in", warehouses.mapped("lot_stock_id").ids),
            ]
        )
        per_warehouse_qty = {
            quant.location_id.warehouse_id.name: quant.quantity for quant in quants
        }
        # Load-bearing for DF-010: no single warehouse can cover a 10-unit order.
        for qty in per_warehouse_qty.values():
            self.assertLess(qty, 10.0)
        self.assertGreaterEqual(sum(per_warehouse_qty.values()), 10.0)
