from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalIsolation(TransactionCase):
    """DF-016 / AT-08 / DEC-012: a portal user must never be able to read
    another customer's quotation. Proven directly against the ORM (search,
    search_read, browse+read) as portal users - not only through the HTTP
    route, per DEC-012's explicit requirement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.beta = cls.env["res.partner"].search([("name", "=", "Beta Industries")], limit=1)
        cls.probook = cls.env["product.product"].search(
            [("name", "=", "ProBook Laptop")], limit=1
        )

        portal_group = cls.env.ref("base.group_portal")
        cls.acme_user = cls.env["res.users"].create(
            {
                "name": "Acme Portal User",
                "login": "acme_portal_test@example.com",
                "email": "acme_portal_test@example.com",
                "partner_id": cls.acme.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )
        cls.beta_user = cls.env["res.users"].create(
            {
                "name": "Beta Portal User",
                "login": "beta_portal_test@example.com",
                "email": "beta_portal_test@example.com",
                "partner_id": cls.beta.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )

        cls.acme_order = cls.env["sale.order"].create({"partner_id": cls.acme.id})
        cls.env["sale.order.line"].create(
            {
                "order_id": cls.acme_order.id,
                "product_id": cls.probook.id,
                "product_uom_qty": 1,
            }
        )
        cls.beta_order = cls.env["sale.order"].create({"partner_id": cls.beta.id})
        cls.env["sale.order.line"].create(
            {
                "order_id": cls.beta_order.id,
                "product_id": cls.probook.id,
                "product_uom_qty": 1,
            }
        )

    def test_portal_user_search_excludes_other_customer(self):
        orders = self.env["sale.order"].with_user(self.acme_user).search([])
        self.assertIn(self.acme_order, orders)
        self.assertNotIn(self.beta_order, orders)

    def test_portal_user_search_read_excludes_other_customer(self):
        rows = (
            self.env["sale.order"]
            .with_user(self.acme_user)
            .search_read([("id", "=", self.beta_order.id)], ["name"])
        )
        self.assertFalse(
            rows, "search_read must silently drop rows outside the record rule"
        )

    def test_portal_user_browse_other_customer_raises_access_error(self):
        order_as_acme = (
            self.env["sale.order"].with_user(self.acme_user).browse(self.beta_order.id)
        )
        with self.assertRaises(AccessError):
            order_as_acme.read(["name"])

    def test_portal_user_can_read_own_order(self):
        order_as_acme = (
            self.env["sale.order"].with_user(self.acme_user).browse(self.acme_order.id)
        )
        order_as_acme.read(["name"])  # must not raise

    def test_portal_user_cannot_write_any_order(self):
        """The DEC-012 rule grants perm_read only - all mutation goes through
        controllers/portal.py's sudo()-mediated actions, never raw portal
        writes (see negotiation.py's _apply comment)."""
        own_order = (
            self.env["sale.order"].with_user(self.acme_user).browse(self.acme_order.id)
        )
        with self.assertRaises(AccessError):
            own_order.write({"partner_id": self.beta.id})

    def test_two_portal_users_never_cross_partners(self):
        acme_orders = self.env["sale.order"].with_user(self.acme_user).search([])
        beta_orders = self.env["sale.order"].with_user(self.beta_user).search([])
        self.assertTrue(set(acme_orders.ids).isdisjoint(set(beta_orders.ids)))

    def test_portal_user_cannot_read_other_customer_negotiation(self):
        negotiation = self.env["dealflow.negotiation"].sudo().create(
            {"order_id": self.beta_order.id, "counter_discount": 5.0}
        )
        rows = (
            self.env["dealflow.negotiation"]
            .with_user(self.acme_user)
            .search_read([("id", "=", negotiation.id)], ["counter_discount"])
        )
        self.assertFalse(rows)

    def test_portal_user_cannot_write_any_negotiation_via_orm(self):
        """Every mutation goes through controllers/portal.py's validated
        sudo() calls - a portal user must never be able to write a
        dealflow.negotiation directly, not even their own (perm_write=0)."""
        own_negotiation = self.env["dealflow.negotiation"].sudo().create(
            {"order_id": self.acme_order.id, "counter_discount": 5.0}
        )
        with self.assertRaises(AccessError):
            own_negotiation.with_user(self.acme_user).write({"counter_discount": 50.0})

    def test_portal_user_cannot_create_negotiation_via_orm(self):
        with self.assertRaises(AccessError):
            self.env["dealflow.negotiation"].with_user(self.acme_user).create(
                {"order_id": self.acme_order.id, "counter_discount": 5.0}
            )
