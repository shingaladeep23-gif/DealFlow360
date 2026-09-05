"""The screens and configuration surfaces the problem statement asks for.

Every case here covers something that existed in the engine and had no way in
from the UI, or a control the spec names explicitly and the product did not
have. The reachability tests matter as much as the behavioural ones: this
codebase has twice shipped an action whose view selection silently no-opped
(`views` is compute-only on this build; `view_ids` is the stored field), and a
Deal Health screen whose menu sat at active="0" with a full engine behind it.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSpecScreens(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.services = cls.env.ref("dealflow360.product_category_services")
        cls.plan = cls.env["dealflow.recurring.plan"].search([], limit=1)

        cls.widget = cls.env["product.product"].create(
            {
                "name": "Screens Widget",
                "categ_id": cls.hardware.id,
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 60.0,
            }
        )
        cls.subscription = cls.env["product.product"].create(
            {
                "name": "Screens Subscription",
                "categ_id": cls.services.id,
                "type": "service",
                "list_price": 300.0,
                "standard_price": 90.0,
                "df_is_recurring": True,
                "df_recurring_plan_id": cls.plan.id,
            }
        )
        cls.rep = cls.env["res.users"].create(
            {
                "name": "Screens Rep",
                "login": "screens_rep@dealflow360.test",
                "email": "screens_rep@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_rep").id])
                ],
            }
        )
        cls.admin = cls.env["res.users"].create(
            {
                "name": "Screens Admin",
                "login": "screens_admin@dealflow360.test",
                "email": "screens_admin@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_admin").id])
                ],
            }
        )

    def _hybrid_order(self):
        return self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "order_line": [
                    (0, 0, {"product_id": self.widget.id, "product_uom_qty": 2}),
                    (0, 0, {"product_id": self.subscription.id, "product_uom_qty": 1}),
                ],
            }
        )

    # -- B7: one-time and recurring, separately, on the same order --------

    def test_order_splits_one_time_from_recurring_lines(self):
        order = self._hybrid_order()
        self.assertEqual(order.df_recurring_line_ids.product_id, self.subscription)
        self.assertEqual(order.df_one_time_line_ids.product_id, self.widget)
        self.assertFalse(order.df_recurring_line_ids & order.df_one_time_line_ids)

    def test_order_exposes_its_own_billing_schedule(self):
        order = self._hybrid_order()
        order.action_confirm()
        self.assertTrue(
            order.df_billing_schedule_ids,
            "B7 asks for the upcoming billing schedule on the ORDER",
        )
        self.assertEqual(
            order.df_billing_schedule_ids.order_line_id.product_id, self.subscription
        )

    # -- the 'paused' state that nothing could ever set -------------------

    def test_pause_and_resume_a_subscription(self):
        order = self._hybrid_order()
        order.action_confirm()
        line = order.df_recurring_line_ids
        self.assertEqual(line.df_sub_state, "active")

        line.action_pause_subscription()
        self.assertEqual(line.df_sub_state, "paused")
        self.assertEqual(line.df_mrr, 0.0, "a paused line contributes no MRR")

        line.action_resume_subscription()
        self.assertEqual(line.df_sub_state, "active")
        self.assertTrue(
            line.billing_schedule_ids.filtered(lambda s: s.state == "pending"),
            "resuming must queue a cycle again",
        )

    def test_pausing_stops_the_cron_billing_it(self):
        order = self._hybrid_order()
        order.action_confirm()
        line = order.df_recurring_line_ids
        schedule = line.billing_schedule_ids[0]
        line.action_pause_subscription()

        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()
        self.assertEqual(schedule.state, "cancelled")
        self.assertFalse(schedule.invoice_id)

    # -- B5's Dismiss ------------------------------------------------------

    def test_dismissing_a_suggestion_removes_it_and_it_stays_gone(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "order_line": [
                    (0, 0, {"product_id": self.widget.id, "product_uom_qty": 1})
                ],
            }
        )
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": self.widget.id,
                "suggested_product_id": self.subscription.id,
                "reason": "Pairs with the widget",
                "score": 50.0,
            }
        )
        suggested = [r["product_id"] for r in order.get_upsell_recommendations()]
        self.assertIn(self.subscription.id, suggested)

        order.action_dismiss_upsell(self.subscription.id)
        suggested_after = [r["product_id"] for r in order.get_upsell_recommendations()]
        self.assertNotIn(
            self.subscription.id,
            suggested_after,
            "a dismissal must survive the next render, not just the click",
        )

    # -- B4/A3: the audit trail is now readable ---------------------------

    def test_audit_trail_is_reachable_from_the_order(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.subscription.id,
                            "product_uom_qty": 1,
                            "discount": 40.0,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        self.assertTrue(
            order.df_audit_log_ids,
            "the order must expose its own audit trail, not just write rows",
        )
        self.assertIn("submitted", order.df_audit_log_ids.mapped("action"))

    # -- reachability: an action that renders nothing is not a feature ----

    def test_every_new_screen_actually_renders(self):
        """get_views() is what the client calls when a menu is clicked. It
        raises if a view references a field that does not exist, or if the
        action's view selection never landed."""
        checks = [
            (self.rep, "dealflow360.action_dealflow_negotiations", ["tree", "form"]),
            (self.rep, "dealflow360.action_dealflow_report_orders",
             ["pivot", "graph", "tree"]),
            (self.rep, "dealflow360.action_dealflow_report_products", ["pivot", "tree"]),
            (self.admin, "dealflow360.action_dealflow_audit_log", ["tree"]),
            (self.admin, "dealflow360.action_dealflow_recurring_plan", ["tree", "form"]),
            (self.admin, "dealflow360.action_dealflow_upsell_rule", ["tree"]),
            (self.admin, "dealflow360.action_dealflow_warehouses", ["tree", "form"]),
        ]
        for user, xmlid, modes in checks:
            action = self.env.ref(xmlid)
            with self.subTest(action=xmlid):
                self.env[action.res_model].with_user(user).get_views(
                    [(None, mode) for mode in modes]
                )

    def test_report_action_uses_the_views_it_declares(self):
        """`views` is compute-only on this build, so an eval write to it
        silently no-ops and the action falls back to defaults - the exact bug
        already found twice in this codebase."""
        action = self.env.ref("dealflow360.action_dealflow_report_orders")
        declared = action.view_ids.filtered(lambda v: v.view_mode == "pivot").view_id
        self.assertEqual(
            declared,
            self.env.ref("dealflow360.view_dealflow_report_pivot"),
            "the reporting pivot must be the one this module defines",
        )

    def test_reports_and_config_menus_are_enabled(self):
        """menu_dealflow_reports shipped at active='0' with a comment saying
        reporting was not implemented."""
        for xmlid in (
            "dealflow360.menu_dealflow_reports",
            "dealflow360.menu_dealflow_report_orders",
            "dealflow360.menu_dealflow_negotiations",
            "dealflow360.menu_dealflow_audit_log",
            "dealflow360.menu_dealflow_recurring_plans",
            "dealflow360.menu_dealflow_upsell_rules",
            "dealflow360.menu_dealflow_warehouses",
        ):
            with self.subTest(menu=xmlid):
                self.assertTrue(self.env.ref(xmlid).active)

    def test_product_form_exposes_the_recurring_plan(self):
        """Without it a product configured through the UI is recurring with no
        plan, so it never bills, never accrues MRR and never prorates."""
        arch = self.env["product.template"].get_views([(None, "form")])["views"][
            "form"
        ]["arch"]
        self.assertIn("df_recurring_plan_id", arch)

    def test_warehouse_form_exposes_the_shipping_weight(self):
        """A4: the tie-break the allocation engine minimises against had no
        field on any screen."""
        arch = self.env["stock.warehouse"].get_views([(None, "form")])["views"][
            "form"
        ]["arch"]
        self.assertIn("df_shipping_cost_weight", arch)
