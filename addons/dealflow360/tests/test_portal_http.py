import re

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPortalHttp(HttpCase):
    """DF-016 hardening: real HTTP requests through controllers/portal.py,
    not just ORM/model-method calls - proves AccessError/MissingError
    actually surface as 403/404 to a caller, and that every route rejects
    the negative path (someone else's order, wrong state), not only the
    happy one."""

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
                "name": "Acme Portal HTTP",
                "login": "acme_http_test@example.com",
                "email": "acme_http_test@example.com",
                "partner_id": cls.acme.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )
        cls.acme_user.password = "AcmeHttp123!"
        cls.beta_user = cls.env["res.users"].create(
            {
                "name": "Beta Portal HTTP",
                "login": "beta_http_test@example.com",
                "email": "beta_http_test@example.com",
                "partner_id": cls.beta.id,
                "groups_id": [(6, 0, [portal_group.id])],
            }
        )
        cls.beta_user.password = "BetaHttp123!"

        cls.acme_order = cls.env["sale.order"].create(
            {"partner_id": cls.acme.id, "state": "sent"}
        )
        cls.acme_line = cls.env["sale.order.line"].create(
            {
                "order_id": cls.acme_order.id,
                "product_id": cls.probook.id,
                "product_uom_qty": 1,
            }
        )
        cls.beta_order = cls.env["sale.order"].create(
            {"partner_id": cls.beta.id, "state": "sent"}
        )
        cls.env["sale.order.line"].create(
            {
                "order_id": cls.beta_order.id,
                "product_id": cls.probook.id,
                "product_uom_qty": 1,
            }
        )

    def _csrf_token(self, html):
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.assertTrue(match, "expected a csrf_token hidden input on the rendered form")
        return match.group(1)

    def test_own_quotation_detail_renders(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        response = self.url_open(f"/my/quotation/{self.acme_order.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.acme_order.name, response.text)

    def test_cross_customer_detail_is_403_or_404_not_the_document(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        response = self.url_open(f"/my/quotation/{self.beta_order.id}")
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(self.beta_order.name, response.text)

    def test_cross_customer_counter_denied_and_no_negotiation_created(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        before = self.env["dealflow.negotiation"].sudo().search_count(
            [("order_id", "=", self.beta_order.id)]
        )
        response = self.url_open(
            f"/my/quotation/{self.beta_order.id}/counter",
            data={"csrf_token": token, "counter_discount": "10"},
        )
        self.assertIn(response.status_code, (403, 404))
        after = self.env["dealflow.negotiation"].sudo().search_count(
            [("order_id", "=", self.beta_order.id)]
        )
        self.assertEqual(before, after, "a denied cross-customer counter must not create a record")

    def test_cross_customer_comment_denied_and_no_message_posted(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        before = len(self.beta_order.message_ids)
        response = self.url_open(
            f"/my/quotation/{self.beta_order.id}/comment",
            data={"csrf_token": token, "message": "trying to comment on someone else's deal"},
        )
        self.assertIn(response.status_code, (403, 404))
        self.beta_order.invalidate_recordset(["message_ids"])
        self.assertEqual(len(self.beta_order.message_ids), before)

    def test_cross_customer_confirm_denied_and_state_unchanged(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        response = self.url_open(
            f"/my/quotation/{self.beta_order.id}/confirm",
            data={"csrf_token": token},
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.beta_order.state, "sent")

    def test_confirm_already_confirmed_order_is_noop(self):
        self.acme_order.action_confirm()
        self.assertEqual(self.acme_order.state, "sale")
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        self.url_open(
            f"/my/quotation/{self.acme_order.id}/confirm",
            data={"csrf_token": token},
        )
        self.assertEqual(self.acme_order.state, "sale")

    def test_counter_discount_on_cancelled_order_is_noop(self):
        self.acme_order.state = "cancel"
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        before = self.env["dealflow.negotiation"].sudo().search_count(
            [("order_id", "=", self.acme_order.id)]
        )
        self.url_open(
            f"/my/quotation/{self.acme_order.id}/counter",
            data={"csrf_token": token, "counter_discount": "10"},
        )
        after = self.env["dealflow.negotiation"].sudo().search_count(
            [("order_id", "=", self.acme_order.id)]
        )
        self.assertEqual(before, after, "a cancelled quotation must reject a counter-discount")

    def test_own_counter_discount_is_recorded_but_not_applied(self):
        """A counter-discount is a REQUEST. This test used to assert the
        opposite - that posting the form moved the discount to 5% - which is
        exactly the bug: a portal user could price their own order and then
        confirm it. Submitting now records a proposal and changes nothing
        until someone on the sales side accepts it."""
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        before = self.acme_order.amount_total
        self.url_open(
            f"/my/quotation/{self.acme_order.id}/counter",
            data={"csrf_token": token, "counter_discount": "5"},
        )
        self.acme_line.invalidate_recordset(["discount"])
        self.acme_order.invalidate_recordset(["amount_total"])
        self.assertEqual(self.acme_line.discount, 0.0, "no price may change")
        self.assertEqual(self.acme_order.amount_total, before)

        negotiation = self.env["dealflow.negotiation"].search(
            [("order_id", "=", self.acme_order.id)]
        )
        self.assertEqual(len(negotiation), 1)
        self.assertEqual(negotiation.state, "proposed")
        self.assertEqual(negotiation.counter_discount, 5.0)

    def test_customer_cannot_confirm_while_their_request_is_unanswered(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        self.url_open(
            f"/my/quotation/{self.acme_order.id}/counter",
            data={"csrf_token": token, "counter_discount": "5"},
        )
        self.url_open(
            f"/my/quotation/{self.acme_order.id}/confirm",
            data={"csrf_token": token},
        )
        self.acme_order.invalidate_recordset(["state"])
        self.assertNotEqual(
            self.acme_order.state,
            "sale",
            "confirming terms the customer has themselves disputed",
        )

    def test_only_one_open_request_at_a_time(self):
        self.authenticate("acme_http_test@example.com", "AcmeHttp123!")
        detail = self.url_open(f"/my/quotation/{self.acme_order.id}")
        token = self._csrf_token(detail.text)
        for pct in ("5", "9", "12"):
            self.url_open(
                f"/my/quotation/{self.acme_order.id}/counter",
                data={"csrf_token": token, "counter_discount": pct},
            )
        negotiations = self.env["dealflow.negotiation"].search(
            [("order_id", "=", self.acme_order.id)]
        )
        self.assertEqual(
            len(negotiations), 1, "a customer cannot outrun the rep answering"
        )
