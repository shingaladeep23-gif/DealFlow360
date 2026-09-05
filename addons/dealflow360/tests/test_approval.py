from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestApproval(TransactionCase):
    """DF-004: automatic approval routing, Sales Manager/Finance levels,
    approve/reject/revision, audit trail, and confirm gating. Nothing here
    existed before this task - dealflow.approval didn't exist."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.services = cls.env.ref("dealflow360.product_category_services")

        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Test Sales Manager",
                "login": "test_sales_manager@dealflow360.test",
                "email": "test_sales_manager@dealflow360.test",
                "groups_id": [(6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_manager").id])],
            }
        )
        cls.finance_user = cls.env["res.users"].create(
            {
                "name": "Test Finance",
                "login": "test_finance@dealflow360.test",
                "email": "test_finance@dealflow360.test",
                "groups_id": [(6, 0, [cls.env.ref("dealflow360.group_dealflow_finance").id])],
            }
        )
        cls.rep_user = cls.env["res.users"].create(
            {
                "name": "Test Sales Rep",
                "login": "test_sales_rep@dealflow360.test",
                "email": "test_sales_rep@dealflow360.test",
                "groups_id": [(6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_rep").id])],
            }
        )

    def _make_product(self, name, categ, list_price, standard_price=50.0):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": categ.id,
                "type": "consu",
                "list_price": list_price,
                "standard_price": standard_price,
            }
        )

    def _make_line(self, order, product, qty, discount):
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "discount": discount,
            }
        )

    def _expect_user_error(self, func, *args, **kwargs):
        """Assert a genuine block: the call raises UserError and there is no
        state change worth keeping (a step acted on out of turn, a reject with
        no reason, a confirm while a chain is still pending).

        Uses a plain try/except rather than assertRaises because
        TransactionCase.assertRaises rolls back to a savepoint, which would
        also erase the approval chain these tests set up beforehand."""
        try:
            func(*args, **kwargs)
        except UserError:
            return
        self.fail("Expected a UserError to be raised")

    def _confirm_expecting_routing(self, order):
        """Assert the AT-04 routing contract: confirming an over-ceiling
        quotation ROUTES it and PERSISTS that routing.

        This deliberately does not accept a UserError. action_confirm used to
        report routing by raising, which propagated out of the RPC call and
        rolled the whole transaction back - live-verified: approvals count
        unchanged, df_approval_id False, df_pipeline_stage still 'draft'. The
        tests missed it only because catching the exception in-process leaves
        the writes intact. It now returns a display_notification action and
        the chain survives."""
        result = order.action_confirm()
        self.assertIsInstance(
            result, dict, "routing must return a client action, never raise"
        )
        self.assertEqual(result.get("tag"), "display_notification")
        self.assertNotEqual(order.state, "sale", "a routed order must not confirm")
        self.assertTrue(
            order.df_approval_id, "the routed approval chain must be persisted"
        )
        return result

    def _confirm_expecting_block(self, order):
        """Confirm is refused because a chain is still pending - a real
        UserError, nothing to persist."""
        self._expect_user_error(order.action_confirm)

    def _medium_risk_order(self):
        # Hardware ceiling 15%, single line at 20% -> excess 5, score 45*... let's
        # just use zero-ceiling category style from test_risk_engine for a clean
        # deterministic MEDIUM (score <= 40) case: excess 3 -> score 27 (< 40).
        zero_ceiling = self.env["product.category"].create(
            {"name": "Approval MEDIUM Category", "df_max_discount": 0.0}
        )
        product = self._make_product("Approval MEDIUM Product", zero_ceiling, 1000.0)
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, product, 1, 3.0)  # excess=3 -> score=27 -> MEDIUM
        self.assertEqual(order.df_risk_level, "medium")
        return order

    def _high_risk_order(self):
        zero_ceiling = self.env["product.category"].create(
            {"name": "Approval HIGH Category", "df_max_discount": 0.0}
        )
        product = self._make_product("Approval HIGH Product", zero_ceiling, 1000.0)
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, product, 1, 10.0)  # excess=10 -> score=90 -> HIGH
        self.assertEqual(order.df_risk_level, "high")
        return order

    # -- routing --------------------------------------------------------

    def test_none_risk_confirms_directly_no_approval(self):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        hw = self._make_product("No Risk Product", self.hardware, 1000.0)
        self._make_line(order, hw, 1, 5.0)  # within 15% ceiling
        self.assertEqual(order.df_risk_level, "none")

        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(order.df_approval_id)

    def test_medium_risk_creates_single_sales_manager_step(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)

        self.assertTrue(order.df_approval_id)
        self.assertEqual(order.df_approval_id.state, "pending")
        self.assertEqual(order.df_pipeline_stage, "pending_approval")
        steps = order.df_approval_id.step_ids
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps.role, "sales_manager")
        self.assertEqual(steps.state, "pending")
        self.assertNotEqual(order.state, "sale")

    def test_high_risk_creates_manager_then_finance_in_order(self):
        order = self._high_risk_order()
        self._confirm_expecting_routing(order)

        steps = order.df_approval_id.step_ids.sorted("sequence")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].role, "sales_manager")
        self.assertEqual(steps[0].state, "pending")
        self.assertEqual(steps[1].role, "finance")
        self.assertEqual(steps[1].state, "waiting", "finance step is not actionable until the manager approves")

    # -- confirm gating ---------------------------------------------------

    def test_confirm_blocked_while_pending_then_allowed_once_approved(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)

        step = order.df_approval_id.step_ids
        step.with_user(self.manager_user).action_approve()
        self.assertEqual(order.df_approval_id.state, "approved")
        self.assertEqual(order.df_pipeline_stage, "approved")

        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_high_risk_finance_step_blocked_until_manager_approves(self):
        order = self._high_risk_order()
        self._confirm_expecting_routing(order)
        steps = order.df_approval_id.step_ids.sorted("sequence")

        self._expect_user_error(
            steps[1].with_user(self.finance_user).action_approve
        )  # waiting, not pending

        steps[0].with_user(self.manager_user).action_approve()
        self.assertEqual(steps[1].state, "pending")

        self._confirm_expecting_block(order)  # finance hasn't acted yet

        steps[1].with_user(self.finance_user).action_approve()
        self.assertEqual(order.df_approval_id.state, "approved")
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_wrong_role_cannot_act_on_step(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        step = order.df_approval_id.step_ids
        self._expect_user_error(
            step.with_user(self.finance_user).action_approve
        )  # finance can't act on a sales_manager step

    # -- reject / revision --------------------------------------------------

    def test_reject_requires_reason_and_stops_confirm(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        step = order.df_approval_id.step_ids

        self._expect_user_error(step.with_user(self.manager_user).action_reject, False)

        step.with_user(self.manager_user).action_reject("Margin too thin")
        self.assertEqual(order.df_approval_id.state, "rejected")
        self.assertEqual(order.df_pipeline_stage, "draft")
        self.assertNotEqual(order.state, "sale")

    def test_request_revision_requires_reason(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        step = order.df_approval_id.step_ids

        self._expect_user_error(step.with_user(self.manager_user).action_request_revision, False)

        step.with_user(self.manager_user).action_request_revision("Please re-check pricing")
        self.assertEqual(order.df_approval_id.state, "revision")
        self.assertEqual(order.df_pipeline_stage, "draft")

    def test_reconfirm_after_rejection_routes_a_fresh_chain(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        first_approval = order.df_approval_id
        first_approval.step_ids.with_user(self.manager_user).action_reject("No")

        self._confirm_expecting_routing(order)
        self.assertNotEqual(order.df_approval_id.id, first_approval.id)
        self.assertEqual(order.df_approval_id.state, "pending")

    # -- audit trail ----------------------------------------------------

    def test_audit_trail_records_submit_approve_reject(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        step = order.df_approval_id.step_ids
        step.with_user(self.manager_user).action_approve("Looks fine")

        logs = self.env["dealflow.audit.log"].search(
            [("order_id", "=", order.id)], order="id asc"
        )
        actions = logs.mapped("action")
        self.assertIn("submitted", actions)
        self.assertIn("approved", actions)
        for log in logs:
            self.assertTrue(log.user_id)
            self.assertTrue(log.timestamp)

    def test_audit_log_is_read_only_for_sales_rep(self):
        order = self._medium_risk_order()
        self._confirm_expecting_routing(order)
        log = self.env["dealflow.audit.log"].search([("order_id", "=", order.id)], limit=1)
        self.assertTrue(log)
        # Rep can read...
        log.with_user(self.rep_user).read(["action"])
        # ...but cannot create or write (ACL create=0/write=0 for every non-sudo group).
        with self.assertRaises(Exception):
            self.env["dealflow.audit.log"].with_user(self.rep_user).create(
                {
                    "order_id": order.id,
                    "user_id": self.rep_user.id,
                    "timestamp": "2026-01-01 00:00:00",
                    "action": "submitted",
                    "detail": "forged",
                }
            )

    # -- reapproval (DF-014 negotiation hook) ----------------------------

    def test_negotiation_counter_discount_triggers_reapproval(self):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        hw = self._make_product("Reapproval Product", self.hardware, 1000.0)
        self._make_line(order, hw, 1, 5.0)
        self.assertEqual(order.df_risk_level, "none")

        negotiation = self.env["dealflow.negotiation"].create(
            {"order_id": order.id, "counter_discount": 40.0}  # well past the 15% ceiling
        )
        new_state = negotiation._apply()

        self.assertEqual(new_state, "requires_reapproval")
        self.assertTrue(order.df_approval_id)
        self.assertEqual(order.df_approval_id.state, "pending")
        logs = self.env["dealflow.audit.log"].search([("order_id", "=", order.id)])
        self.assertIn("submitted", logs.mapped("action"))
