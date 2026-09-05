"""Post-confirmation engines must only run for orders that CONFIRMED.

Three overrides of action_confirm() stack on sale.order (models/sale_order.py,
then warehouse_split.py, then recurring.py - see models/__init__.py). The
governance override confirms only the subset that passed its checks and leaves
an over-ceiling quotation in 'draft', routed for approval. The other two used
to loop over ALL of `self` regardless.

Reproduced live before this version: a draft quotation blocked pending manager
AND finance approval had its subscription activated, a billing schedule row
written, and the daily cron posted a real 999.00 customer invoice against it -
which was then invisible from the order, because the invoice line carried no
sale_line_ids.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConfirmCascade(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.services = cls.env.ref("dealflow360.product_category_services")
        cls.plan = cls.env["dealflow.recurring.plan"].search([], limit=1)

        cls.widget = cls.env["product.product"].create(
            {
                "name": "Cascade Widget",
                "categ_id": cls.hardware.id,
                "type": "product",
                "list_price": 100.0,
                "standard_price": 60.0,
            }
        )
        cls.subscription = cls.env["product.product"].create(
            {
                "name": "Cascade Subscription",
                "categ_id": cls.services.id,
                "type": "service",
                "list_price": 999.0,
                "standard_price": 200.0,
                "df_is_recurring": True,
                "df_recurring_plan_id": cls.plan.id,
            }
        )

    def _order(self, discount):
        return self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.widget.id,
                            "product_uom_qty": 1,
                            "discount": discount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.subscription.id,
                            "product_uom_qty": 1,
                        },
                    ),
                ],
            }
        )

    # -- the reproduction -------------------------------------------------

    def test_blocked_quotation_starts_no_subscription_and_no_split(self):
        order = self._order(80.0)
        order.action_confirm()

        self.assertEqual(order.state, "draft", "precondition: routed, not confirmed")
        self.assertEqual(order.df_approval_id.state, "pending")

        sub_line = order.order_line.filtered(
            lambda l: l.product_id == self.subscription
        )
        self.assertFalse(sub_line.df_sub_state, "no subscription may start")
        self.assertFalse(
            self.env["dealflow.billing.schedule"].search(
                [("order_id", "=", order.id)]
            ),
            "no billing schedule may be written for an unapproved quotation",
        )
        self.assertFalse(
            order.df_split_ids, "no fulfillment allocation for an unconfirmed order"
        )

    def test_cron_never_invoices_an_unconfirmed_order(self):
        """The second lock: even if a schedule row somehow exists, billing it
        would charge a customer for a quotation nobody accepted."""
        order = self._order(80.0)
        order.action_confirm()
        sub_line = order.order_line.filtered(
            lambda l: l.product_id == self.subscription
        )
        schedule = self.env["dealflow.billing.schedule"].sudo().create(
            {
                "order_id": order.id,
                "order_line_id": sub_line.id,
                "date": order.date_order.date(),
                "amount": 999.0,
                "state": "pending",
            }
        )

        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()

        self.assertEqual(
            schedule.state,
            "pending",
            "left pending, not cancelled - the order may yet be approved",
        )
        self.assertFalse(schedule.invoice_id, "no invoice for a draft quotation")

    # -- the confirmed path must still work fully -------------------------

    def test_confirmed_order_starts_its_subscription_and_split(self):
        order = self._order(0.0)
        order.action_confirm()

        self.assertEqual(order.state, "sale")
        sub_line = order.order_line.filtered(
            lambda l: l.product_id == self.subscription
        )
        self.assertEqual(sub_line.df_sub_state, "active")
        self.assertTrue(sub_line.billing_schedule_ids)
        self.assertTrue(order.df_split_ids, "a confirmed order still gets its split")

    def test_subscription_invoice_is_reachable_from_its_order(self):
        """§1.4's second half: the invoice existed but was orphaned."""
        order = self._order(0.0)
        order.action_confirm()
        sub_line = order.order_line.filtered(
            lambda l: l.product_id == self.subscription
        )
        schedule = sub_line.billing_schedule_ids[0]
        schedule.action_invoice_now()

        self.assertEqual(schedule.state, "invoiced")
        invoice = schedule.invoice_id
        self.assertEqual(invoice.state, "posted")
        self.assertIn(
            invoice,
            order.invoice_ids,
            "a subscription invoice must show on its own order",
        )
        self.assertEqual(invoice.company_id, order.company_id)

    def test_native_create_invoice_does_not_double_bill_a_subscription(self):
        """The schedule bills the recurring line; the order's own Create
        Invoice button must bill only the one-time line."""
        order = self._order(0.0)
        order.action_confirm()
        sub_line = order.order_line.filtered(
            lambda l: l.product_id == self.subscription
        )
        sub_line.billing_schedule_ids[0].action_invoice_now()

        invoiceable = order._get_invoiceable_lines()
        self.assertNotIn(
            sub_line, invoiceable, "a recurring line is never natively invoiceable"
        )
        self.assertIn(
            order.order_line.filtered(lambda l: l.product_id == self.widget),
            invoiceable,
            "the one-time line on the same order still invoices normally",
        )
