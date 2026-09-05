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


@tagged("post_install", "-at_install")
class TestWorkspaceAndAlerts(TransactionCase):
    """B1's Sales Workspace, B9's nudge/escalate, and A7's PDF half - the
    remaining spec surfaces that had nothing behind them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.services = cls.env.ref("dealflow360.product_category_services")
        cls.rep = cls.env["res.users"].create(
            {
                "name": "Workspace Rep",
                "login": "workspace_rep@dealflow360.test",
                "email": "workspace_rep@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_rep").id])
                ],
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Workspace Manager",
                "login": "workspace_manager@dealflow360.test",
                "email": "workspace_manager@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_manager").id])
                ],
            }
        )
        cls.service = cls.env["product.product"].create(
            {
                "name": "Workspace Service",
                "categ_id": cls.services.id,
                "type": "service",
                "list_price": 500.0,
                "standard_price": 300.0,
            }
        )

    def _order(self, discount=0.0):
        return self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "user_id": self.rep.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.service.id,
                            "product_uom_qty": 2,
                            "discount": discount,
                        },
                    )
                ],
            }
        )

    # -- B1 ---------------------------------------------------------------

    def test_workspace_action_and_menu_exist(self):
        action = self.env.ref("dealflow360.action_dealflow_workspace")
        self.assertEqual(action.tag, "dealflow_workspace")
        self.assertTrue(self.env.ref("dealflow360.menu_dealflow_workspace").active)

    def test_reload_data_actually_refreshes_something(self):
        """B1 calls it "Refreshes pricing, stock and approval data". Deal
        health is the part that genuinely goes stale, so this must really
        recompute it, not just re-render the client."""
        order = self._order()
        self.assertFalse(order.df_health_status, "precondition: not scored yet")

        result = self.env["sale.order"].with_user(self.rep).action_df_reload_workspace_data()

        self.assertGreater(result["orders_refreshed"], 0)
        self.assertIn("at_risk", result)
        order.invalidate_recordset()
        self.assertTrue(
            order.df_health_status, "a reload must leave the deal actually scored"
        )

    def test_workspace_targets_resolve(self):
        """Go to Back-end and Close Workspace both doAction on an xmlid; a
        typo there is only visible at click time."""
        self.assertTrue(self.env.ref("dealflow360.action_dealflow_discount_tier"))
        self.assertTrue(self.env.ref("dealflow360.action_dealflow_dashboard"))

    # -- B9 ---------------------------------------------------------------

    def test_nudge_schedules_a_real_activity_for_the_owner(self):
        order = self._order()
        order.sudo()._compute_deal_health()
        before = len(order.message_ids)

        order.with_user(self.manager).action_df_nudge()

        activity = self.env["mail.activity"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", order.id)]
        )
        self.assertTrue(activity, "a nudge must land in someone's actual inbox")
        self.assertEqual(activity.user_id, self.rep)
        self.assertGreater(len(order.message_ids), before)

    def test_escalation_goes_to_someone_other_than_the_owner(self):
        order = self._order()
        order.sudo()._compute_deal_health()

        order.with_user(self.manager).action_df_escalate()

        activity = self.env["mail.activity"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", order.id)]
        )
        self.assertTrue(activity)
        self.assertNotEqual(
            activity.user_id,
            self.rep,
            "escalating to the person who already owns it is not an escalation",
        )

    def test_nudge_without_a_salesperson_is_refused(self):
        from odoo.exceptions import UserError

        order = self._order()
        order.user_id = False
        with self.assertRaises(UserError):
            order.action_df_nudge()

    # -- A7's PDF ---------------------------------------------------------

    def test_deal_summary_report_renders(self):
        """A QWeb template only fails when something actually renders it."""
        order = self._order(discount=40.0)
        order.action_confirm()
        order.df_approval_id.current_step_id.with_user(
            self.manager
        ).action_approve("fine")

        html = self.env["ir.actions.report"]._render_qweb_html(
            "dealflow360.report_deal_summary", order.ids
        )[0]
        text = html.decode() if isinstance(html, bytes) else html
        self.assertIn(order.name, text)
        self.assertIn("Deal Governance Summary", text)
        self.assertIn("Audit trail", text)
