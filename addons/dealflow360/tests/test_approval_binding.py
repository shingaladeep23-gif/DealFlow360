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

from odoo.exceptions import UserError
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

        # _df_engine() rather than sudo(): the decision fields are guarded
        # against direct writes now (see test_approval_authority), so this is
        # how a test deliberately manufactures the corrupt state that
        # _df_covers() has to reject.
        approval._df_engine().write({"state": "approved"})
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
        approval._df_engine().write({"order_fingerprint": False})
        self.assertFalse(approval._df_covers(order))

    # -- a refusal binds too ----------------------------------------------
    #
    # The mirror of everything above. An approval only authorises the exact
    # order it was granted for; symmetrically a rejection only binds the exact
    # order it was refused for - and it has to bind to SOMETHING, or it costs
    # the rep one click.

    def _reject_first_step(self, order, reason="Not acceptable, do not resubmit"):
        step = order.df_approval_id.current_step_id
        step.with_user(self.manager_user).action_reject(reason)
        return step

    def test_rejected_quotation_cannot_be_resubmitted_unchanged(self):
        """Live-reproduced: manager rejects with "Not acceptable, do not
        resubmit", the rep clicks Confirm again on a byte-identical order, and
        a brand-new approval chain opens against the same numbers."""
        order = self._order(20.0)
        order.action_confirm()
        rejected_chain = order.df_approval_id
        self._reject_first_step(order)
        self.assertEqual(rejected_chain.state, "rejected")
        chains_before = self.env["dealflow.approval"].search_count(
            [("order_id", "=", order.id)]
        )

        with self.assertRaises(UserError) as caught:
            order.action_confirm()

        self.assertIn("Not acceptable, do not resubmit", str(caught.exception))
        self.assertEqual(
            self.env["dealflow.approval"].search_count([("order_id", "=", order.id)]),
            chains_before,
            "an unchanged rejected deal must not open a fresh chain",
        )
        self.assertEqual(order.df_approval_id, rejected_chain)
        self.assertNotEqual(order.state, "sale")

    def test_revising_the_deal_lets_it_route_again(self):
        """The other direction: a rejection binds to the deal that was
        refused, not to the quotation forever. Genuinely change it and it
        routes normally - that is what "changes requested" means."""
        order = self._order(20.0)
        order.action_confirm()
        rejected_chain = order.df_approval_id
        self._reject_first_step(order, "Too deep, come back lower")

        # Still over the ceiling, so it must route - just not the SAME deal.
        order.order_line.discount = 18.0
        order.action_confirm()

        self.assertNotEqual(order.df_approval_id, rejected_chain)
        self.assertEqual(order.df_approval_id.state, "pending")
        self.assertEqual(rejected_chain.state, "rejected", "history is not rewritten")

    def test_revising_back_within_the_ceiling_confirms_outright(self):
        """A deal revised all the way back inside its limit needs no approval
        at all - the rejection must not leave the quotation permanently
        un-confirmable."""
        order = self._order(20.0)
        order.action_confirm()
        self._reject_first_step(order)

        order.order_line.discount = 0.0
        order.action_confirm()

        self.assertEqual(order.state, "sale")

    def test_revision_request_also_blocks_an_unchanged_resubmit(self):
        order = self._order(20.0)
        order.action_confirm()
        step = order.df_approval_id.current_step_id
        step.with_user(self.manager_user).action_request_revision("Justify the discount")

        with self.assertRaises(UserError) as caught:
            order.action_confirm()
        self.assertIn("Justify the discount", str(caught.exception))

    def test_rejection_tells_the_rep_on_the_record_they_own(self):
        """The only chatter entry on a rejected order used to be "Sales Order
        created". The reason lived solely inside the approval record, which
        the rep has no reason to open."""
        order = self._order(20.0)
        order.action_confirm()
        messages_before = len(order.message_ids)

        self._reject_first_step(order, "Margin is below floor")

        order.invalidate_recordset(["message_ids", "activity_ids"])
        self.assertGreater(len(order.message_ids), messages_before)
        bodies = " ".join(order.message_ids.mapped("body"))
        self.assertIn("Margin is below floor", bodies)
        self.assertIn("Rejected by", bodies)

        activities = order.activity_ids.filtered(
            lambda a: a.user_id == order.user_id
        )
        self.assertTrue(
            activities, "the rep must get a real to-do, not just a chatter line"
        )
        self.assertIn("Margin is below floor", activities[0].note or "")
