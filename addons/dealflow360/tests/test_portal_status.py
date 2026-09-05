from odoo.tests.common import TransactionCase, tagged

from odoo.addons.dealflow360.controllers.portal import DealflowPortal


@tagged("post_install", "-at_install")
class TestPortalStatus(TransactionCase):
    """AT-08 wants the customer-facing vocabulary Sent / Under Negotiation /
    Confirmed - sale.order.df_pipeline_stage has neither 'sent' nor a
    negotiation-driven value yet (see its own docstring), so the portal
    computes its own label instead of depending on that field."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.probook = cls.env["product.product"].search(
            [("name", "=", "ProBook Laptop")], limit=1
        )
        cls.controller = DealflowPortal()

    def _make_order(self):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.probook.id,
                "product_uom_qty": 1,
            }
        )
        return order

    def test_no_customer_facing_status_is_ever_draft(self):
        """B8's vocabulary is Sent / Under Negotiation / Confirmed. "Draft" is
        an internal state and used to leak straight through to the customer's
        list - alongside 18 quotations the rep had never sent. Drafts are now
        unreadable to portal users at all (see the record rule in
        security/dealflow_security.xml), so there is no draft label left to
        render."""
        order = self._make_order()
        self.assertEqual(order.state, "draft")
        self.assertNotEqual(
            self.controller._dealflow_portal_status(order, False), "Draft"
        )
        self.assertNotIn(
            "draft",
            self.controller._dealflow_portal_status_badge_class(order, False),
        )

    def test_sent_without_negotiation(self):
        order = self._make_order()
        order.state = "sent"
        self.assertEqual(self.controller._dealflow_portal_status(order, False), "Sent")

    def test_under_negotiation_overrides_sent(self):
        order = self._make_order()
        order.state = "sent"
        self.assertEqual(
            self.controller._dealflow_portal_status(order, True), "Under Negotiation"
        )

    def test_confirmed_overrides_negotiation(self):
        order = self._make_order()
        order.action_confirm()
        self.assertEqual(
            self.controller._dealflow_portal_status(order, True), "Confirmed"
        )

    def test_cancelled(self):
        order = self._make_order()
        order.state = "cancel"
        self.assertEqual(self.controller._dealflow_portal_status(order, False), "Cancelled")
