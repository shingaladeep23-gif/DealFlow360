from datetime import timedelta

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRecurringBilling(TransactionCase):
    """DF-012: DEC-004 native recurring billing (no sale_subscription),
    DEC-008 subscription lifecycle on sale.order.line, real account.move
    invoices, mid-cycle proration both directions, cancel_rule credit
    notes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.services = cls.env.ref("dealflow360.product_category_services")
        cls.monthly_plan = cls.env["dealflow.recurring.plan"].create(
            {
                "name": "Test Monthly",
                "interval": "monthly",
                "proration": True,
                "cancel_rule": "prorate_refund",
            }
        )

    def _make_recurring_product(self, name, list_price, plan=None):
        return self.env["product.product"].create(
            {
                "name": name,
                "categ_id": self.services.id,
                "type": "service",
                "list_price": list_price,
                "standard_price": list_price * 0.4,
                "df_is_recurring": True,
                "df_recurring_plan_id": (plan or self.monthly_plan).id,
            }
        )

    def _make_order(self, product, qty=1, discount=0.0):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "discount": discount,
            }
        )
        return order, line

    # -- confirming starts the subscription ---------------------------------

    def test_confirm_starts_subscription_and_first_schedule_entry(self):
        product = self._make_recurring_product("Recurring Care Plan", 100.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()

        self.assertEqual(line.df_sub_state, "active")
        self.assertTrue(line.df_sub_start_date)
        self.assertEqual(line.df_sub_next_bill_date, line.df_sub_start_date)
        self.assertEqual(len(line.billing_schedule_ids), 1)
        schedule = line.billing_schedule_ids
        self.assertEqual(schedule.state, "pending")
        self.assertAlmostEqual(schedule.amount, 100.0, places=2)

    def test_one_time_line_never_starts_a_subscription(self):
        one_time = self.env["product.product"].create(
            {
                "name": "One-Time Widget",
                "categ_id": self.services.id,
                "type": "service",
                "list_price": 50.0,
            }
        )
        order, line = self._make_order(one_time, qty=1)
        order.action_confirm()

        self.assertFalse(line.df_sub_state)
        self.assertFalse(line.billing_schedule_ids)

    def test_confirm_is_idempotent_does_not_duplicate_schedule(self):
        """Calling the recurring-billing action_confirm hook twice (e.g. via
        two overlapping _inherit extensions on the same order) must not
        create a second first-cycle schedule entry."""
        product = self._make_recurring_product("Idempotent Plan", 80.0)
        order, line = self._make_order(product, qty=1)
        line._df_start_subscription()
        line._df_start_subscription()
        self.assertEqual(len(line.billing_schedule_ids), 1)

    # -- the cron produces a REAL, posted account.move ----------------------

    def test_cron_generates_real_posted_invoice_and_queues_next_cycle(self):
        product = self._make_recurring_product("Cron Plan", 200.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        schedule = line.billing_schedule_ids
        first_date = schedule.date

        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, "invoiced")
        invoice = schedule.invoice_id
        self.assertTrue(invoice)
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.state, "posted")
        # The schedule bills the line's untaxed subtotal; tax is carried
        # through natively from the sale line's tax_ids, so amount_total is
        # subtotal + tax and only amount_untaxed equals the billed amount.
        self.assertAlmostEqual(invoice.amount_untaxed, 200.0, places=2)
        self.assertAlmostEqual(
            invoice.amount_total, invoice.amount_untaxed + invoice.amount_tax, places=2
        )
        self.assertEqual(invoice.invoice_line_ids.tax_ids, line.tax_id)

        # Next cycle's entry was queued exactly one month out.
        pending = line.billing_schedule_ids.filtered(lambda s: s.state == "pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.date.month, (first_date.month % 12) + 1)

    def test_manual_invoice_now_queues_the_next_cycle_like_the_cron(self):
        """The 'Generate Invoice Now' button must leave the subscription in
        exactly the state the cron would have: invoiced, and renewed. It
        previously called _create_invoice() directly and never queued the
        following cycle, so invoicing from the UI stopped the subscription
        dead."""
        product = self._make_recurring_product("Manual Invoice Plan", 300.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        schedule = line.billing_schedule_ids
        first_date = schedule.date

        schedule.action_invoice_now()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, "invoiced")
        self.assertEqual(schedule.invoice_id.state, "posted")

        pending = line.billing_schedule_ids.filtered(lambda s: s.state == "pending")
        self.assertEqual(len(pending), 1, "manual invoicing must queue the next cycle")
        self.assertEqual(pending.date.month, (first_date.month % 12) + 1)
        self.assertEqual(line.df_sub_next_bill_date, pending.date)

    def test_manual_invoice_now_cancels_entry_for_a_paused_line(self):
        product = self._make_recurring_product("Manual Paused Plan", 120.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        schedule = line.billing_schedule_ids
        line.df_sub_state = "paused"

        schedule.action_invoice_now()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, "cancelled")
        self.assertFalse(schedule.invoice_id)

    def test_cron_skips_entries_not_yet_due(self):
        product = self._make_recurring_product("Future Plan", 150.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        schedule = line.billing_schedule_ids
        schedule.date = schedule.date + timedelta(days=30)

        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, "pending")
        self.assertFalse(schedule.invoice_id)

    def test_cron_cancels_schedule_for_a_paused_line_instead_of_invoicing(self):
        product = self._make_recurring_product("Paused Plan", 90.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        schedule = line.billing_schedule_ids
        line.df_sub_state = "paused"

        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, "cancelled")
        self.assertFalse(schedule.invoice_id)

    # -- MRR, both directions of the "is active" gate -----------------------

    def test_mrr_normalizes_by_interval_and_zeroes_when_inactive(self):
        monthly_product = self._make_recurring_product("MRR Monthly", 100.0)
        quarterly_plan = self.env["dealflow.recurring.plan"].create(
            {"name": "Test Quarterly", "interval": "quarterly", "cancel_rule": "no_refund"}
        )
        quarterly_product = self._make_recurring_product(
            "MRR Quarterly", 300.0, plan=quarterly_plan
        )
        order, monthly_line = self._make_order(monthly_product, qty=1)
        quarterly_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": quarterly_product.id,
                "product_uom_qty": 1,
            }
        )
        order.action_confirm()

        self.assertAlmostEqual(monthly_line.df_mrr, 100.0, places=2)
        self.assertAlmostEqual(quarterly_line.df_mrr, 100.0, places=2)  # 300 / 3

        monthly_line.action_cancel_subscription()
        self.assertEqual(monthly_line.df_mrr, 0.0)

    # -- mid-cycle proration, BOTH directions -------------------------------

    def test_mid_cycle_quantity_increase_prorates_a_positive_charge(self):
        product = self._make_recurring_product("Proration Up Plan", 300.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        # 15 days left out of a 30-day month -> ~half a cycle remaining.
        line.df_sub_next_bill_date = line.df_sub_start_date + timedelta(days=15)

        line.product_uom_qty = 2  # add one more unit mid-cycle

        proration = line.billing_schedule_ids.filtered("df_is_proration")
        self.assertEqual(len(proration), 1)
        self.assertGreater(proration.amount, 0.0)
        self.assertLess(proration.amount, 300.0)  # never the full extra unit's price

    def test_mid_cycle_quantity_decrease_prorates_a_credit(self):
        product = self._make_recurring_product("Proration Down Plan", 300.0)
        order, line = self._make_order(product, qty=2)
        order.action_confirm()
        line.df_sub_next_bill_date = line.df_sub_start_date + timedelta(days=15)

        line.product_uom_qty = 1  # drop a unit mid-cycle

        proration = line.billing_schedule_ids.filtered("df_is_proration")
        self.assertEqual(len(proration), 1)
        self.assertLess(proration.amount, 0.0)

    def test_quantity_change_after_bill_date_does_not_prorate(self):
        """Other direction of the mid-cycle guard: once today >= next bill
        date, the (already overdue) regular cycle invoice will reflect the
        new quantity - no separate proration entry should appear."""
        product = self._make_recurring_product("No Proration Plan", 300.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        line.df_sub_next_bill_date = line.df_sub_start_date  # due today

        line.product_uom_qty = 2

        self.assertFalse(line.billing_schedule_ids.filtered("df_is_proration"))

    def test_plan_with_proration_disabled_never_prorates(self):
        no_proration_plan = self.env["dealflow.recurring.plan"].create(
            {"name": "No Proration Plan", "interval": "monthly", "proration": False}
        )
        product = self._make_recurring_product(
            "Flat Plan", 300.0, plan=no_proration_plan
        )
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        line.df_sub_next_bill_date = line.df_sub_start_date + timedelta(days=15)

        line.product_uom_qty = 2

        self.assertFalse(line.billing_schedule_ids.filtered("df_is_proration"))

    # -- cancel_rule: both branches ------------------------------------------

    def test_cancel_with_no_refund_rule_creates_no_credit_note(self):
        no_refund_plan = self.env["dealflow.recurring.plan"].create(
            {"name": "No Refund Plan", "interval": "monthly", "cancel_rule": "no_refund"}
        )
        product = self._make_recurring_product(
            "No Refund Product", 100.0, plan=no_refund_plan
        )
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()

        invoice_count_before = self.env["account.move"].search_count(
            [("partner_id", "=", self.acme.id)]
        )
        line.action_cancel_subscription()

        self.assertEqual(line.df_sub_state, "cancelled")
        invoice_count_after = self.env["account.move"].search_count(
            [("partner_id", "=", self.acme.id)]
        )
        self.assertEqual(invoice_count_before, invoice_count_after)

    def test_cancel_with_prorate_refund_rule_issues_a_credit_note(self):
        product = self._make_recurring_product("Refund Product", 300.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        self.env["dealflow.billing.schedule"]._cron_generate_recurring_invoices()
        invoiced_schedule = line.billing_schedule_ids.filtered(
            lambda s: s.state == "invoiced"
        )
        original_invoice = invoiced_schedule.invoice_id
        self.assertEqual(original_invoice.state, "posted")

        # Cancel partway through the cycle so a real unused remainder exists.
        invoiced_schedule.date = invoiced_schedule.date - timedelta(days=15)
        line.action_cancel_subscription()

        self.assertEqual(line.df_sub_state, "cancelled")
        credit_notes = self.env["account.move"].search(
            [
                ("reversed_entry_id", "=", original_invoice.id),
                ("move_type", "=", "out_refund"),
            ]
        )
        self.assertEqual(len(credit_notes), 1)
        self.assertEqual(credit_notes.state, "posted")
        self.assertGreater(credit_notes.amount_total, 0.0)
        self.assertLess(credit_notes.amount_total, original_invoice.amount_total)

    def test_cancelling_pending_schedule_stops_future_billing(self):
        product = self._make_recurring_product("Stop Billing Product", 120.0)
        order, line = self._make_order(product, qty=1)
        order.action_confirm()
        pending_before = line.billing_schedule_ids.filtered(lambda s: s.state == "pending")
        self.assertTrue(pending_before)

        line.action_cancel_subscription()

        pending_before.invalidate_recordset()
        self.assertEqual(pending_before.state, "cancelled")
