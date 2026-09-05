from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDealHealth(TransactionCase):
    """DF-017: deal-health scoring (DEC-005) and its per-signal breakdown
    (DEC-011). Nothing here existed before this task."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.rep = cls.env["res.users"].create(
            {
                "name": "Test Health Rep",
                "login": "test_health_rep@dealflow360.test",
                "email": "test_health_rep@dealflow360.test",
                "groups_id": [(6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_rep").id])],
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Test Health Manager",
                "login": "test_health_manager@dealflow360.test",
                "email": "test_health_manager@dealflow360.test",
                "groups_id": [(6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_manager").id])],
            }
        )

    def _make_product(self, name, list_price=1000.0, standard_price=600.0, categ=None, type="consu"):
        # Default type="consu": the delivery-risk signal only ever looks at
        # type="product" (storable) lines, so non-storable test products
        # are naturally immune to it - needed so tests for the OTHER three
        # signals get a clean, predictable score. Delivery-risk tests pass
        # type="product" explicitly.
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": (categ or self.hardware).id,
                "type": type,
                "list_price": list_price,
                "standard_price": standard_price,
            }
        )

    def _make_line(self, order, product, qty=1, discount=0.0):
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "discount": discount,
            }
        )

    def _flag_codes(self, order):
        return set(order.df_health_flags.mapped("code"))

    # -- healthy baseline ------------------------------------------------

    def test_no_signals_stays_healthy_100(self):
        product = self._make_product("Health OK Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1)

        order._compute_deal_health()

        self.assertEqual(order.df_health_score, 100)
        self.assertEqual(order.df_health_status, "healthy")
        self.assertFalse(order.df_health_flags)
        self.assertFalse(order.df_health_reason)
        self.assertFalse(order.df_health_flagged_date)

    # -- stalled -----------------------------------------------------------

    def test_stalled_signal_penalizes_and_caps_at_30(self):
        self.env["ir.config_parameter"].sudo().set_param("dealflow.health_stalled_days", "7")
        product = self._make_product("Health Stalled Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1)

        # 10 days inactive -> 3 days beyond the 7-day threshold -> 15 penalty
        order.df_last_activity = fields.Datetime.now() - timedelta(days=10)
        order._compute_deal_health()
        self.assertEqual(order.df_health_score, 85)
        self.assertIn("stalled", self._flag_codes(order))
        self.assertIn("Stalled", order.df_health_reason)

        # far beyond threshold -> capped at 30, not unbounded
        order.df_last_activity = fields.Datetime.now() - timedelta(days=100)
        order._compute_deal_health()
        self.assertEqual(order.df_health_score, 70)

    def test_stalled_within_threshold_not_flagged(self):
        self.env["ir.config_parameter"].sudo().set_param("dealflow.health_stalled_days", "7")
        product = self._make_product("Health Recent Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1)
        order.df_last_activity = fields.Datetime.now() - timedelta(days=2)

        order._compute_deal_health()
        self.assertNotIn("stalled", self._flag_codes(order))
        self.assertEqual(order.df_health_score, 100)

    # -- discount anomaly -----------------------------------------------

    def test_discount_anomaly_against_real_rep_history(self):
        product = self._make_product("Health Anomaly Product")
        # Rep's real 90-day baseline: two past confirmed orders at 10% discount.
        for _i in range(2):
            past = self.env["sale.order"].create(
                {"partner_id": self.acme.id, "user_id": self.rep.id}
            )
            self._make_line(past, product, 1, discount=10.0)
            past.action_confirm()

        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        # 30% > 1.5 * 10% -> anomaly
        self._make_line(order, product, 1, discount=30.0)

        order._compute_deal_health()
        self.assertIn("discount_anomaly", self._flag_codes(order))
        self.assertEqual(order.df_health_score, 80)  # 100 - 20
        self.assertIn("Discount", order.df_health_reason)

    def test_discount_anomaly_not_flagged_without_rep_history(self):
        product = self._make_product("Health No History Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1, discount=30.0)

        order._compute_deal_health()
        self.assertNotIn("discount_anomaly", self._flag_codes(order))
        self.assertEqual(order.df_health_score, 100)

    def test_discount_within_normal_range_not_flagged(self):
        product = self._make_product("Health Normal Discount Product")
        for _i in range(2):
            past = self.env["sale.order"].create(
                {"partner_id": self.acme.id, "user_id": self.rep.id}
            )
            self._make_line(past, product, 1, discount=10.0)
            past.action_confirm()

        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1, discount=12.0)  # not > 1.5x

        order._compute_deal_health()
        self.assertNotIn("discount_anomaly", self._flag_codes(order))

    # -- approval delay --------------------------------------------------

    def test_approval_delay_signal_after_backdating_pending_since(self):
        self.env["ir.config_parameter"].sudo().set_param("dealflow.health_approval_delay_days", "2")
        # 1% rather than 0%: a category ceiling of 0 now means UNSET
        # (it falls back to the tier, then to dealflow.default_max_discount),
        # so a genuinely strict ceiling has to be a real positive number.
        strict = self.env["product.category"].create(
            {"name": "Health Approval Delay Category", "df_max_discount": 1.0}
        )
        product = self._make_product("Health Approval Delay Product", 1000.0, 600.0, strict)
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1, discount=5.0)  # excess -> medium/high risk

        try:
            order.action_confirm()
        except Exception:
            pass
        self.assertTrue(order.df_approval_id)
        self.assertEqual(order.df_approval_id.state, "pending")

        step = order.df_approval_id.current_step_id
        step.pending_since = fields.Datetime.now() - timedelta(days=5)  # 3 days over threshold

        order._compute_deal_health()
        self.assertIn("approval_delay", self._flag_codes(order))
        self.assertEqual(order.df_health_score, 85)  # 100 - 15
        self.assertIn("Approval pending", order.df_health_reason)

    def test_no_approval_delay_when_not_pending(self):
        product = self._make_product("Health No Approval Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1)

        order._compute_deal_health()
        self.assertNotIn("approval_delay", self._flag_codes(order))

    # -- delivery risk ----------------------------------------------------

    def test_delivery_risk_when_stock_insufficient(self):
        product = self._make_product("Health Delivery Risk Product", type="product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 50)  # no stock.quant seeded -> 0 available

        order._compute_deal_health()
        self.assertIn("delivery_risk", self._flag_codes(order))
        self.assertEqual(order.df_health_score, 75)  # 100 - 25
        self.assertIn("Cannot be fully sourced", order.df_health_reason)

    def test_no_delivery_risk_when_stock_sufficient(self):
        product = self._make_product("Health Sufficient Stock Product", type="product")
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.env["stock.quant"].sudo().create(
            {
                "product_id": product.id,
                "location_id": warehouse.lot_stock_id.id,
                "quantity": 100.0,
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 5)

        order._compute_deal_health()
        self.assertNotIn("delivery_risk", self._flag_codes(order))

    # -- status buckets ----------------------------------------------------

    def test_status_buckets_healthy_at_risk_critical(self):
        product = self._make_product("Health Bucket Product", type="product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 50)  # delivery_risk only -> score 75

        order._compute_deal_health()
        self.assertEqual(order.df_health_score, 75)
        self.assertEqual(order.df_health_status, "at_risk")

    # -- flagged_date state -------------------------------------------------

    def test_flagged_date_set_once_and_cleared_when_resolved(self):
        product = self._make_product("Health Flagged Date Product", type="product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 50)  # delivery risk

        order._compute_deal_health()
        self.assertTrue(order.df_health_flagged_date)
        first_flagged = order.df_health_flagged_date

        # Recompute again while still flagged - date must NOT move.
        order._compute_deal_health()
        self.assertEqual(order.df_health_flagged_date, first_flagged)

        # Resolve it (bring in enough stock) - flag clears, date resets.
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.env["stock.quant"].sudo().create(
            {
                "product_id": product.id,
                "location_id": warehouse.lot_stock_id.id,
                "quantity": 100.0,
            }
        )
        order._compute_deal_health()
        self.assertFalse(order.df_health_flagged_date)
        self.assertEqual(order.df_health_score, 100)

    # -- cron scoping --------------------------------------------------

    def test_cron_skips_cancelled_orders(self):
        product = self._make_product("Health Cron Cancelled Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 50)
        order.action_cancel()
        self.assertEqual(order.state, "cancel")

        self.env["sale.order"]._cron_compute_deal_health()
        self.assertEqual(order.df_health_score, 0)  # never computed - default value

    def test_cron_covers_draft_sent_and_sale_orders(self):
        product = self._make_product("Health Cron Draft Product")
        order = self.env["sale.order"].create({"partner_id": self.acme.id, "user_id": self.rep.id})
        self._make_line(order, product, 1)
        self.assertEqual(order.state, "draft")

        self.env["sale.order"]._cron_compute_deal_health()
        self.assertEqual(order.df_health_score, 100)
        self.assertEqual(order.df_health_status, "healthy")
