"""An approval must bind to WHAT was approved (17.0.1.4.0).

Every test here is a bypass that worked before this version, reproduced live
against a real database, not a hypothetical:

  * route a 20% deal, silently edit it to 60% while it sat in the approval
    queue, let the manager and finance approve the stale 45-point snapshot
    they were shown - and the order confirmed at 60%, 45 points past the
    ceiling, with no re-route and no audit row;
  * write state='approved' straight onto the chain (a plain writable column)
    and confirm, with every step still pending.

Both went through dealflow.approval.state alone, which is why _df_covers()
now checks the chain, every step, AND the order fingerprint.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestApprovalBinding(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Binding Sales Manager",
                "login": "binding_manager@dealflow360.test",
                "email": "binding_manager@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_sales_manager").id])
                ],
            }
        )
        cls.finance_user = cls.env["res.users"].create(
            {
                "name": "Binding Finance",
                "login": "binding_finance@dealflow360.test",
                "email": "binding_finance@dealflow360.test",
                "groups_id": [
                    (6, 0, [cls.env.ref("dealflow360.group_dealflow_finance").id])
                ],
            }
        )
        cls.laptop = cls.env["product.product"].create(
            {
                "name": "Binding Test Laptop",
                "categ_id": cls.hardware.id,
                "type": "consu",
                "list_price": 1000.0,
                "standard_price": 600.0,
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
                            "product_id": self.laptop.id,
                            "product_uom_qty": 1,
                            "discount": discount,
                        },
                    )
                ],
            }
        )

    def _walk_chain(self, approval):
        """Approve every step properly, through the real action methods."""
        for step in approval.step_ids.sorted("sequence"):
            user = (
                self.manager_user
                if step.role == "sales_manager"
                else self.finance_user
            )
            step.with_user(user).action_approve("ok")

    # -- the fingerprint itself ------------------------------------------

    def test_fingerprint_ignores_line_order_but_tracks_discount(self):
        order = self._order(20.0)
        before = order.df_governance_fingerprint
        self.assertTrue(before, "every order must carry a fingerprint")

        # A recompute with no real change must not move it - otherwise live
        # chains would be superseded by nothing at all.
        order.invalidate_recordset()
        self.assertEqual(order.df_governance_fingerprint, before)

        order.order_line.discount = 21.0
        self.assertNotEqual(
            order.df_governance_fingerprint,
            before,
            "a discount change must change the fingerprint",
        )

    # -- the headline bypass ---------------------------------------------

    def test_editing_a_pending_quotation_supersedes_its_chain(self):
        order = self._order(20.0)
        order.action_confirm()
        approval = order.df_approval_id
        self.assertEqual(approval.state, "pending")
        routed_score = approval.risk_score

        order.order_line.discount = 60.0

        self.assertEqual(
            approval.state,
            "superseded",
            "editing a quotation under review must retire the chain",
        )
        self.assertFalse(
            approval.step_ids.filtered(lambda s: s.state in ("waiting", "pending")),
            "no step may stay actionable on a superseded chain",
        )
        log = self.env["dealflow.audit.log"].search(
            [("order_id", "=", order.id), ("action", "=", "superseded")]
        )
        self.assertTrue(log, "an edit that voids a decision must be audited")
        self.assertIn("%.1f" % routed_score, log.detail)

    def test_cannot_confirm_at_a_discount_nobody_approved(self):
        """The §1.1 reproduction, end to end."""
        order = self._order(20.0)
        order.action_confirm()
        approval = order.df_approval_id
        self._walk_chain(approval)
        self.assertEqual(approval.state, "approved")

        # The rep quietly deepens the discount after sign-off.
        order.order_line.discount = 60.0
        order.action_confirm()

        self.assertNotEqual(
            order.state, "sale", "an order edited after approval must not confirm"
        )
        self.assertEqual(approval.state, "superseded")
        self.assertNotEqual(
            order.df_approval_id,
            approval,
            "a fresh chain must be routed against the new numbers",
        )
        self.assertEqual(order.df_approval_id.state, "pending")

    def test_untouched_approved_quotation_still_confirms(self):
        """The guard must not break the happy path it is protecting."""
        order = self._order(20.0)
        order.action_confirm()
        self._walk_chain(order.df_approval_id)
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    # -- the data-layer bypass -------------------------------------------

    def test_chain_marked_approved_with_unwalked_steps_does_not_confirm(self):
        """state is a plain column; walking the steps is what approval means."""
        order = self._order(30.0)
        order.action_confirm()
        approval = order.df_approval_id
        self.assertEqual(approval.risk_level, "high")

        approval.sudo().write({"state": "approved"})
        self.assertTrue(
            approval.step_ids.filtered(lambda s: s.state != "approved"),
            "precondition: at least one step is still unwalked",
        )
        self.assertFalse(
            approval._df_covers(order),
            "a chain nobody walked must not authorise confirmation",
        )

        order.action_confirm()
        self.assertNotEqual(order.state, "sale")

    def test_covers_requires_a_fingerprint(self):
        """A chain with no recorded content authorises nothing - this is what
        stops a hand-crafted or half-migrated row from acting as a skeleton
        key."""
        order = self._order(20.0)
        order.action_confirm()
        approval = order.df_approval_id
        self._walk_chain(approval)
        approval.sudo().write({"order_fingerprint": False})
        self.assertFalse(approval._df_covers(order))
