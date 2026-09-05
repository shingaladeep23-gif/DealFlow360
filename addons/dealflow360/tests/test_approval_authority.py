"""Separation of duties has to hold at the DATA layer (17.0.1.4.0).

Role enforcement used to live only inside _check_actionable(), which a plain
ORM write never reaches. Reproduced live before this version: a Sales Manager
wrote state='approved' onto FINANCE's step and onto the chain, and the order
confirmed - the two-tier chain the problem statement asks for (§3: Manager and
Finance are distinct roles) collapsed into one signature.

Stage 1 already stopped that from CONFIRMING anything, via _df_covers(). These
tests cover the other half: the write must not succeed in the first place, so
the approval record never lies about who approved what.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestApprovalAuthority(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.services = cls.env.ref("dealflow360.product_category_services")
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Authority Manager",
                "login": "authority_manager@dealflow360.test",
                "email": "authority_manager@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_manager").id])
                ],
            }
        )
        cls.finance = cls.env["res.users"].create(
            {
                "name": "Authority Finance",
                "login": "authority_finance@dealflow360.test",
                "email": "authority_finance@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_finance").id])
                ],
            }
        )
        cls.service = cls.env["product.product"].create(
            {
                "name": "Authority Setup Service",
                "categ_id": cls.services.id,
                "type": "service",
                "list_price": 500.0,
                "standard_price": 300.0,
            }
        )

    def _high_risk_order(self):
        """Services cap at 10%, so 40% routes Manager -> Finance."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.service.id,
                            "product_uom_qty": 4,
                            "discount": 40.0,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        self.assertEqual(order.df_approval_id.risk_level, "high")
        return order

    # -- the reproduction ------------------------------------------------

    def test_manager_cannot_write_the_finance_step(self):
        order = self._high_risk_order()
        finance_step = order.df_approval_id.step_ids.filtered(
            lambda s: s.role == "finance"
        )
        with self.assertRaises(UserError):
            finance_step.with_user(self.manager).write({"state": "approved"})
        self.assertEqual(finance_step.state, "waiting")

    def test_manager_cannot_write_the_chain_state(self):
        order = self._high_risk_order()
        with self.assertRaises(UserError):
            order.df_approval_id.with_user(self.manager).write({"state": "approved"})
        self.assertEqual(order.df_approval_id.state, "pending")

    def test_even_sudo_cannot_write_a_decision_without_the_engine(self):
        """The guard is not just an ACL - it holds for admin and dev mode too,
        which is what stops a hand-edit through a debug list view."""
        order = self._high_risk_order()
        with self.assertRaises(UserError):
            order.df_approval_id.sudo().write({"state": "approved"})
        with self.assertRaises(UserError):
            order.df_approval_id.step_ids.sudo().write({"reason": "rewritten"})

    def test_nobody_can_hand_craft_a_chain(self):
        """Otherwise the write guard is sidestepped at birth: create a chain
        that arrives already approved, with the order's own fingerprint."""
        order = self._high_risk_order()
        with self.assertRaises(UserError):
            self.env["dealflow.approval"].sudo().create(
                {
                    "order_id": order.id,
                    "state": "approved",
                    "order_fingerprint": order.df_governance_fingerprint,
                }
            )

    def test_finance_cannot_act_before_the_manager(self):
        """The ordering rule itself, through the supported entry point."""
        order = self._high_risk_order()
        finance_step = order.df_approval_id.step_ids.filtered(
            lambda s: s.role == "finance"
        )
        with self.assertRaises(UserError):
            finance_step.with_user(self.finance).action_approve("early")

    def test_manager_cannot_act_on_a_finance_step(self):
        """Even once it IS actionable, the role gate holds."""
        order = self._high_risk_order()
        steps = order.df_approval_id.step_ids
        steps.filtered(lambda s: s.role == "sales_manager").with_user(
            self.manager
        ).action_approve("ok")
        finance_step = steps.filtered(lambda s: s.role == "finance")
        self.assertEqual(finance_step.state, "pending")
        with self.assertRaises(UserError):
            finance_step.with_user(self.manager).action_approve("mine too")

    # -- the guard must not break the real flow --------------------------

    def test_the_supported_path_still_works_end_to_end(self):
        order = self._high_risk_order()
        steps = order.df_approval_id.step_ids.sorted("sequence")
        steps[0].with_user(self.manager).action_approve("looks fine")
        order.df_approval_id.invalidate_recordset()
        steps[1].with_user(self.finance).action_approve("margin acceptable")

        self.assertEqual(order.df_approval_id.state, "approved")
        self.assertEqual(
            steps.mapped("approver_id"), self.manager + self.finance
        )
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_rejection_still_records_its_reason(self):
        order = self._high_risk_order()
        step = order.df_approval_id.current_step_id
        step.with_user(self.manager).action_reject("too thin")
        self.assertEqual(step.state, "rejected")
        self.assertEqual(step.reason, "too thin")
        self.assertEqual(step.approver_id, self.manager)
        self.assertEqual(order.df_approval_id.state, "rejected")
