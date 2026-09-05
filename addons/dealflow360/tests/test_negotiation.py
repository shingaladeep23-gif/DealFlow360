from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNegotiation(TransactionCase):
    """DF-014: portal counter-discount rewrites line discount and reuses
    Atlas's existing risk engine (DF-002/DF-003) rather than reimplementing
    it - recompute-after-negotiate is asserted against sale.order's own
    computed fields, never a duplicated formula here."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.setup_service = cls.env["product.product"].search(
            [("name", "=", "Onsite Setup Service")], limit=1
        )

    def _make_order(self, discount=0.0):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.setup_service.id,
                "product_uom_qty": 1,
                "discount": discount,
            }
        )
        return order

    def test_counter_discount_within_ceiling_applies_cleanly(self):
        order = self._make_order(discount=0.0)
        self.assertEqual(order.df_risk_level, "none")
        negotiation = self.env["dealflow.negotiation"].create(
            {"order_id": order.id, "counter_discount": 5.0}
        )
        negotiation._apply()
        self.assertEqual(negotiation.state, "applied")
        self.assertEqual(order.order_line.discount, 5.0)
        self.assertEqual(order.df_risk_level, "none")

    def test_counter_discount_over_ceiling_requires_reapproval(self):
        """Setup Service's category ceiling is 10% (DEC-014); an 18% counter
        matches the spec's own canonical over-limit example."""
        order = self._make_order(discount=0.0)
        negotiation = self.env["dealflow.negotiation"].create(
            {"order_id": order.id, "counter_discount": 18.0}
        )
        negotiation._apply()
        self.assertEqual(negotiation.state, "requires_reapproval")
        self.assertNotEqual(order.df_risk_level, "none")
        self.assertEqual(negotiation.risk_level_before, "none")
        self.assertEqual(negotiation.risk_level_after, order.df_risk_level)

    def test_apply_posts_audit_message_on_order_chatter(self):
        order = self._make_order(discount=0.0)
        message_count_before = len(order.message_ids)
        negotiation = self.env["dealflow.negotiation"].create(
            {"order_id": order.id, "counter_discount": 5.0}
        )
        negotiation._apply()
        self.assertGreater(len(order.message_ids), message_count_before)

    def test_apply_with_no_lines_raises(self):
        from odoo.exceptions import UserError

        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        negotiation = self.env["dealflow.negotiation"].create(
            {"order_id": order.id, "counter_discount": 5.0}
        )
        with self.assertRaises(UserError):
            negotiation._apply()
