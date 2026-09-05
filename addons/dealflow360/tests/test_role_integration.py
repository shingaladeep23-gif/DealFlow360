"""End-to-end flows executed AS EACH ROLE, not as superuser.

Why this file exists: every other test in this module runs with the default
superuser environment, which bypasses ir.model.access.csv entirely. That hid a
P1 - a Sales Rep clicking Confirm on their own over-ceiling quotation got
"You are not allowed to create dealflow.approval records" instead of the
automatic routing AT-04 requires, because the routing code created the chain
as the acting user. The same shape of bug existed for the warehouse split and
the billing schedule. These tests drive the real entry points with
with_user(), so an ACL regression fails here instead of in the browser.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRoleIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.service = cls.env["product.product"].search(
            [("name", "=", "Onsite Setup Service")], limit=1
        )
        cls.probook = cls.env["product.product"].search(
            [("name", "=", "ProBook Laptop")], limit=1
        )
        cls.rep = cls._make_user("t.rep", "dealflow360.group_dealflow_sales_rep")
        cls.manager = cls._make_user(
            "t.manager", "dealflow360.group_dealflow_sales_manager"
        )
        cls.finance = cls._make_user("t.finance", "dealflow360.group_dealflow_finance")

    @classmethod
    def _make_user(cls, login, group_xmlid):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                # Chatter posts resolve the sender from the author's email;
                # without one, message_post() raises and takes down every flow
                # that writes a note (split confirmation, portal comments).
                "email": "%s@dealflow360.example" % login,
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(group_xmlid).id,
                        ],
                    )
                ],
            }
        )

    def _rep_order(self, product, qty, discount):
        order = self.env["sale.order"].with_user(self.rep).create(
            {"partner_id": self.acme.id, "user_id": self.rep.id}
        )
        self.env["sale.order.line"].with_user(self.rep).create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "discount": discount,
            }
        )
        return order

    def test_rep_confirming_over_ceiling_quotation_is_routed_not_denied(self):
        """The P1 this file was written for."""
        order = self._rep_order(self.service, 4, 30.0)
        self.assertEqual(order.df_risk_level, "high")

        # Confirm must ROUTE (no AccessError, no rollback-inducing raise) and
        # the chain must genuinely survive the call.
        result = order.with_user(self.rep).action_confirm()
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("tag"), "display_notification")

        self.assertNotEqual(order.state, "sale")
        self.assertTrue(order.df_approval_id)
        self.assertEqual(order.df_approval_id.state, "pending")
        self.assertEqual(order.df_pipeline_stage, "pending_approval")
        self.assertEqual(
            order.df_approval_id.step_ids.mapped("role"),
            ["sales_manager", "finance"],
        )

    def test_rep_cannot_hand_author_an_approval_chain(self):
        """The sudo() in _create_for_order must not have widened the ACL:
        a rep still cannot create an approval record directly."""
        order = self._rep_order(self.service, 4, 30.0)
        with self.assertRaises(Exception):
            self.env["dealflow.approval"].with_user(self.rep).create(
                {"order_id": order.id}
            )

    def test_manager_then_finance_approve_a_high_risk_chain(self):
        order = self._rep_order(self.service, 4, 30.0)
        order.with_user(self.rep).action_confirm()
        approval = order.df_approval_id
        self.assertTrue(approval)

        step1 = approval.current_step_id
        self.assertEqual(step1.role, "sales_manager")
        step1.with_user(self.manager).action_approve()

        approval.invalidate_recordset()
        step2 = approval.current_step_id
        self.assertEqual(step2.role, "finance")
        step2.with_user(self.finance).action_approve()

        approval.invalidate_recordset()
        self.assertEqual(approval.state, "approved")
        order.invalidate_recordset()
        self.assertEqual(order.df_pipeline_stage, "approved")

    def test_rep_confirming_stock_order_generates_the_warehouse_split(self):
        order = self._rep_order(self.probook, 10, 0.0)
        self.assertEqual(order.df_risk_level, "none")
        order.with_user(self.rep).action_confirm()

        order.invalidate_recordset()
        self.assertEqual(order.state, "sale")
        split = order.df_split_ids
        self.assertTrue(split, "confirm must generate a warehouse split")
        self.assertTrue(split.line_ids)
        # Real fragmented stock: 6 at Main + 4 at East cannot ship from one.
        self.assertGreater(len(split.line_ids.mapped("warehouse_id")), 1)

        # Accepting the suggestion must materialise real pickings. This posts
        # to the order chatter, which is where a user with no email address
        # previously blew up.
        split.with_user(self.rep).action_confirm()
        split.invalidate_recordset()
        self.assertEqual(split.state, "confirmed")
        live = split.picking_ids.filtered(lambda p: p.state != "cancel")
        self.assertGreater(len(live), 1, "one delivery per sourcing warehouse")

        # The split's deliveries must be reachable FROM the order - they carry
        # the order's procurement group, so native sale_id and the order's
        # Delivery smart button both resolve to them.
        order.invalidate_recordset()
        for picking in live:
            self.assertEqual(picking.sale_id, order)
        self.assertTrue(
            set(live.ids).issubset(set(order.picking_ids.ids)),
            "split deliveries must appear on the order they belong to",
        )

    def test_rep_confirming_recurring_line_starts_billing_schedule(self):
        core_plan = self.env["product.product"].search(
            [("name", "=", "Core Plan")], limit=1
        )
        order = self._rep_order(core_plan, 1, 0.0)
        order.with_user(self.rep).action_confirm()

        line = order.order_line
        self.assertEqual(line.df_sub_state, "active")
        self.assertTrue(
            line.billing_schedule_ids, "confirm must queue the first billing cycle"
        )

    def test_core_plan_demo_product_has_a_recurring_plan(self):
        """Without a plan, MRR computes to 0 and no next cycle is ever
        queued - the Subscriptions screen looked broken."""
        core_plan = self.env["product.template"].search(
            [("name", "=", "Core Plan")], limit=1
        )
        self.assertTrue(core_plan.df_is_recurring)
        self.assertTrue(
            core_plan.df_recurring_plan_id,
            "a recurring demo product must carry a billing plan",
        )

    def test_finance_can_refresh_deal_health_without_write_access(self):
        order = self._rep_order(self.probook, 1, 0.0)
        order.with_user(self.finance).action_df_refresh_health()
        order.invalidate_recordset()
        self.assertTrue(order.df_health_status)

    def test_every_role_can_read_the_screens_its_menu_exposes(self):
        """Each menu is group-scoped; the model behind it must be readable by
        those same groups or the screen opens onto an AccessError."""
        checks = [
            (self.rep, "dealflow.warehouse.split"),   # Fulfillment menu
            (self.finance, "dealflow.warehouse.split"),
            (self.rep, "dealflow.health.flag"),       # Deal Health menu
            (self.finance, "dealflow.health.flag"),
            (self.rep, "dealflow.billing.schedule"),  # Subscriptions menu
            (self.finance, "dealflow.billing.schedule"),
            (self.rep, "dealflow.upsell.rule"),       # upsell panel on the form
            (self.finance, "dealflow.upsell.rule"),
            (self.manager, "dealflow.approval"),      # Approvals menu
            (self.finance, "dealflow.approval"),
        ]
        for user, model in checks:
            with self.subTest(user=user.login, model=model):
                self.env[model].with_user(user).search([], limit=1)
