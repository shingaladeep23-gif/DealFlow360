from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUpsell(TransactionCase):
    """DF-008: deterministic upsell/cross-sell recommendation engine.
    Nothing here existed before this task - dealflow.upsell.rule didn't exist."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.beta = cls.env["res.partner"].create({"name": "Upsell Test Beta Co"})
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")

    def _make_product(self, name, list_price=1000.0, standard_price=600.0, **extra):
        vals = {
            "name": name,
            "categ_id": self.hardware.id,
            "type": "consu",
            "list_price": list_price,
            "standard_price": standard_price,
        }
        vals.update(extra)
        return self.env["product.product"].create(vals)

    def _make_line(self, order, product, qty=1, discount=0.0):
        return self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "discount": discount,
            }
        )

    # -- explicit curated rules -----------------------------------------

    def test_curated_rule_recommends_and_carries_reason(self):
        laptop = self._make_product("Upsell Laptop", 1000.0, 600.0)
        mouse = self._make_product("Upsell Mouse", 50.0, 20.0)
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": laptop.id,
                "suggested_product_id": mouse.id,
                "score": 80.0,
                "reason": "Frequently paired with laptops",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["product_id"], mouse.id)
        self.assertEqual(recs[0]["score"], 80.0)
        self.assertIn("Frequently paired with laptops", recs[0]["reason"])

    def test_product_already_in_cart_is_never_suggested(self):
        laptop = self._make_product("Upsell Laptop Own", 1000.0, 600.0)
        mouse = self._make_product("Upsell Mouse Own", 50.0, 20.0)
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": laptop.id,
                "suggested_product_id": mouse.id,
                "score": 80.0,
                "reason": "test",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)
        self._make_line(order, mouse)  # already added

        recs = order.get_upsell_recommendations()
        self.assertFalse(any(r["product_id"] == mouse.id for r in recs))

    def test_empty_cart_returns_no_recommendations(self):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self.assertEqual(order.get_upsell_recommendations(), [])

    # -- promotion bonus --------------------------------------------------

    def test_promoted_product_gets_bonus_and_reason(self):
        laptop = self._make_product("Upsell Laptop Promo", 1000.0, 600.0)
        dock = self._make_product(
            "Upsell Dock Promo", 200.0, 100.0, df_is_promoted=True
        )
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": laptop.id,
                "suggested_product_id": dock.id,
                "score": 40.0,
                "reason": "Common accessory",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["score"], 50.0)  # 40 base + 10 promotion bonus
        self.assertIn("Currently promoted", recs[0]["reason"])

    # -- margin floor exclusion -------------------------------------------

    def test_candidate_below_its_own_min_margin_is_excluded(self):
        laptop = self._make_product("Upsell Laptop MinMargin", 1000.0, 600.0)
        # own margin = (100-95)/100 = 5%, floor set to 20% -> must be excluded
        thin_margin_product = self._make_product(
            "Upsell Thin Margin", 100.0, 95.0, df_min_margin=20.0
        )
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": laptop.id,
                "suggested_product_id": thin_margin_product.id,
                "score": 90.0,
                "reason": "test",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertFalse(any(r["product_id"] == thin_margin_product.id for r in recs))

    def test_candidate_at_or_above_its_own_min_margin_is_kept(self):
        laptop = self._make_product("Upsell Laptop MinMargin2", 1000.0, 600.0)
        # own margin = (100-70)/100 = 30% >= floor 20% -> kept
        healthy_margin_product = self._make_product(
            "Upsell Healthy Margin", 100.0, 70.0, df_min_margin=20.0
        )
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": laptop.id,
                "suggested_product_id": healthy_margin_product.id,
                "score": 90.0,
                "reason": "test",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertTrue(any(r["product_id"] == healthy_margin_product.id for r in recs))

    # -- co-purchase history -----------------------------------------------

    def test_co_purchase_history_from_confirmed_orders(self):
        laptop = self._make_product("Upsell Laptop CoPurchase", 1000.0, 600.0)
        bag = self._make_product("Upsell Bag CoPurchase", 80.0, 30.0)

        past_order = self.env["sale.order"].create({"partner_id": self.beta.id})
        self._make_line(past_order, laptop)
        self._make_line(past_order, bag)
        past_order.action_confirm()
        self.assertEqual(past_order.state, "sale")

        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertTrue(any(r["product_id"] == bag.id for r in recs))
        bag_rec = next(r for r in recs if r["product_id"] == bag.id)
        self.assertIn("Frequently bought together", bag_rec["reason"])

    def test_co_purchase_ignores_non_confirmed_orders(self):
        laptop = self._make_product("Upsell Laptop Draft", 1000.0, 600.0)
        cable = self._make_product("Upsell Cable Draft", 20.0, 5.0)

        draft_order = self.env["sale.order"].create({"partner_id": self.beta.id})
        self._make_line(draft_order, laptop)
        self._make_line(draft_order, cable)
        # never confirmed - stays in draft

        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, laptop)

        recs = order.get_upsell_recommendations()
        self.assertFalse(any(r["product_id"] == cable.id for r in recs))

    # -- margin projection --------------------------------------------------

    def test_projected_and_delta_margin_are_genuinely_computed(self):
        # Order: 1x product at list 1000 / cost 600 -> margin 40%.
        base = self._make_product("Upsell Margin Base", 1000.0, 600.0)
        # Suggestion: list 500 / cost 100 -> much higher margin, should pull
        # the projected order margin up.
        suggestion = self._make_product("Upsell Margin Suggestion", 500.0, 100.0)
        self.env["dealflow.upsell.rule"].create(
            {
                "product_id": base.id,
                "suggested_product_id": suggestion.id,
                "score": 10.0,
                "reason": "test",
            }
        )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, base)
        self.assertAlmostEqual(order.df_margin_pct, 40.0, places=4)

        recs = order.get_upsell_recommendations()
        rec = next(r for r in recs if r["product_id"] == suggestion.id)

        # revenue 1000+500=1500, cost 600+100=700 -> margin (1500-700)/1500
        expected_projected = (1500.0 - 700.0) / 1500.0 * 100.0
        self.assertAlmostEqual(rec["projected_margin_pct"], expected_projected, places=4)
        self.assertAlmostEqual(
            rec["margin_delta_pct"], expected_projected - 40.0, places=4
        )
        self.assertGreater(rec["margin_delta_pct"], 0.0)

    # -- ranking + limit ------------------------------------------------

    def test_results_sorted_by_score_desc_and_limited(self):
        base = self._make_product("Upsell Rank Base", 1000.0, 600.0)
        low = self._make_product("Upsell Rank Low", 100.0, 60.0)
        high = self._make_product("Upsell Rank High", 100.0, 60.0)
        mid = self._make_product("Upsell Rank Mid", 100.0, 60.0)
        for product, score in ((low, 10.0), (high, 90.0), (mid, 50.0)):
            self.env["dealflow.upsell.rule"].create(
                {
                    "product_id": base.id,
                    "suggested_product_id": product.id,
                    "score": score,
                    "reason": "test",
                }
            )
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, base)

        recs = order.get_upsell_recommendations(limit=2)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["product_id"], high.id)
        self.assertEqual(recs[1]["product_id"], mid.id)

    # -- add to quote --------------------------------------------------

    def test_action_add_upsell_line_writes_real_line_and_updates_margin(self):
        base = self._make_product("Upsell Add Base", 1000.0, 600.0)
        suggestion = self._make_product("Upsell Add Suggestion", 500.0, 100.0)
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, base)
        margin_before = order.df_margin_pct
        line_count_before = len(order.order_line)

        line_id = order.action_add_upsell_line(suggestion.id)

        self.assertTrue(line_id)
        self.assertEqual(len(order.order_line), line_count_before + 1)
        new_line = self.env["sale.order.line"].browse(line_id)
        self.assertEqual(new_line.product_id.id, suggestion.id)
        self.assertEqual(new_line.order_id.id, order.id)
        self.assertNotEqual(order.df_margin_pct, margin_before)
