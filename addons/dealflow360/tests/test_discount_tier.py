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


@tagged("post_install", "-at_install")
class TestCeilingDefaults(TransactionCase):
    """An UNSET ceiling means "this axis places no limit", not "no discount
    allowed". Reproduced live before 17.0.1.5.0: a brand-new customer given a
    2% discount came out "Needs manager approval", because both the tier and
    category ceilings default to 0.0 and the effective ceiling was min() of the
    two. Any judge creating their own customer to try the demo hit it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        # Deliberately a category with NO ceiling of its own, so that with an
        # untiered customer neither axis is configured and the fallback is what
        # is under test. (A Hardware product would take that category's real
        # 15% and never reach the default.)
        cls.ungoverned = cls.env["product.category"].create(
            {"name": "Ceiling Test Ungoverned"}
        )
        cls.laptop = cls.env["product.product"].create(
            {
                "name": "Ceiling Test Laptop",
                "categ_id": cls.ungoverned.id,
                "type": "consu",
                "list_price": 1000.0,
                "standard_price": 600.0,
            }
        )

    def _line_for(self, partner, product, discount):
        order = self.env["sale.order"].create({"partner_id": partner.id})
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "discount": discount,
            }
        )

    def test_untiered_customer_gets_the_configured_default_not_zero(self):
        partner = self.env["res.partner"].create({"name": "Ceiling Untiered Co"})
        self.assertFalse(partner.df_tier_id)
        line = self._line_for(partner, self.laptop, 2.0)
        self.assertEqual(line.df_effective_ceiling, 5.0)
        self.assertEqual(line.df_excess_points, 0.0)
        self.assertEqual(line.order_id.df_risk_level, "none")

    def test_the_default_is_admin_configurable(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "dealflow.default_max_discount", 1.0
        )
        partner = self.env["res.partner"].create({"name": "Ceiling Configurable Co"})
        line = self._line_for(partner, self.laptop, 2.0)
        self.assertEqual(line.df_effective_ceiling, 1.0)
        self.assertAlmostEqual(line.df_excess_points, 1.0, places=4)

    def test_an_uncategorised_product_still_respects_the_tier(self):
        """One axis configured is enough - the default only applies when
        NEITHER is."""
        gold = self.env["dealflow.discount.tier"].search(
            [("name", "=", "Gold")], limit=1
        )
        partner = self.env["res.partner"].create(
            {"name": "Ceiling Gold Co", "df_tier_id": gold.id}
        )
        plain = self.env["product.product"].create(
            {
                "name": "Ceiling Uncategorised Widget",
                "categ_id": self.env.ref("product.product_category_all").id,
                "type": "consu",
                "list_price": 500.0,
                "standard_price": 300.0,
            }
        )
        line = self._line_for(partner, plain, 12.0)
        self.assertEqual(line.df_effective_ceiling, gold.max_discount)
        self.assertEqual(line.df_excess_points, 0.0)

    def test_the_stricter_configured_axis_still_wins(self):
        """The core DEC-003 rule must be untouched: Services cap at 10% even
        for a Gold customer allowed 15%."""
        gold = self.env["dealflow.discount.tier"].search(
            [("name", "=", "Gold")], limit=1
        )
        partner = self.env["res.partner"].create(
            {"name": "Ceiling Gold Services Co", "df_tier_id": gold.id}
        )
        service = self.env["product.product"].create(
            {
                "name": "Ceiling Setup Service",
                "categ_id": self.env.ref("dealflow360.product_category_services").id,
                "type": "service",
                "list_price": 500.0,
                "standard_price": 300.0,
            }
        )
        line = self._line_for(partner, service, 18.0)
        self.assertEqual(line.df_effective_ceiling, 10.0)
        self.assertAlmostEqual(line.df_excess_points, 8.0, places=4)
