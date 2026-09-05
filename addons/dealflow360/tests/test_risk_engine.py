from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRiskEngine(TransactionCase):
    """DF-003b: DEC-003 blended risk scoring + DEC-010 configurable threshold +
    DEC-015 pricelist reference pricing. Nothing here existed before this
    task - the engine landed in 92993e8 with zero df_*risk* coverage."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)
        cls.hardware = cls.env.ref("dealflow360.product_category_hardware")
        cls.services = cls.env.ref("dealflow360.product_category_services")

    def _make_product(self, name, categ, list_price, standard_price=100.0):
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

    # -- DEC-003 worked example -------------------------------------------------

    def test_worked_example_scores_exactly_40_and_routes_medium(self):
        """The spec's own worked example (docs/decisions.md DEC-003): Gold
        customer, Hardware line 12% given / 15% allowed (0 excess, subtotal
        1000), Services line 18% given / 10% allowed (8 excess, subtotal 500).
        weights 0.667/0.333 -> blended=8/3, max=8 -> score=6*(8/3)+3*8=40
        exactly -> MEDIUM (not HIGH; the default threshold is score > 40)."""
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        hw = self._make_product("Risk HW 1000", self.hardware, 1000.0)
        svc = self._make_product("Risk SVC 500", self.services, 500.0)
        self._make_line(order, hw, 1, 12.0)
        self._make_line(order, svc, 1, 18.0)

        self.assertAlmostEqual(order.df_blended_risk_score, 40.0, places=6)
        self.assertEqual(order.df_risk_level, "medium")
        self.assertTrue(order.df_risk_summary)
        self.assertIn("Risk SVC 500", order.df_risk_summary)

    def test_risk_weighting_uses_pre_discount_reference_value(self):
        """Same pair as above. If weights were taken from the POST-discount
        price_subtotal (880/410) instead of the pre-discount reference value
        (1000/500) required by the spec, the score would be ~39.26, not 40 -
        see the comment on sale_order.py's _compute_df_risk. Assert the real
        engine matches the pre-discount answer and NOT the post-discount one."""
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        hw = self._make_product("Weight HW 1000", self.hardware, 1000.0)
        svc = self._make_product("Weight SVC 500", self.services, 500.0)
        hw_line = self._make_line(order, hw, 1, 12.0)
        svc_line = self._make_line(order, svc, 1, 18.0)

        post_discount_total = hw_line.price_subtotal + svc_line.price_subtotal
        post_discount_blended = (
            hw_line.df_excess_points * (hw_line.price_subtotal / post_discount_total)
            + svc_line.df_excess_points * (svc_line.price_subtotal / post_discount_total)
        )
        post_discount_score = min(
            100.0, 6 * post_discount_blended + 3 * max(hw_line.df_excess_points, svc_line.df_excess_points)
        )

        self.assertAlmostEqual(order.df_blended_risk_score, 40.0, places=6)
        self.assertNotAlmostEqual(order.df_blended_risk_score, post_discount_score, places=2)

    # -- min(100, ...) cap --------------------------------------------------

    def test_risk_score_caps_at_100(self):
        """A single wildly-over-ceiling line pushes 6*blended + 3*max well
        past 100; the score must clip at the cap, never exceed it."""
        # 1% rather than 0%: a category ceiling of 0 now means UNSET
        # (it falls back to the tier, then to dealflow.default_max_discount),
        # so a genuinely strict ceiling has to be a real positive number.
        strict = self.env["product.category"].create(
            {"name": "Strict Ceiling Test Category", "df_max_discount": 1.0}
        )
        product = self._make_product("Cap Test Product", strict, 1000.0)
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self._make_line(order, product, 1, 90.0)

        self.assertAlmostEqual(order.df_blended_risk_score, 100.0, places=6)
        self.assertEqual(order.df_risk_level, "high")

    # -- none / medium / high boundaries against configurable threshold ------

    def test_risk_level_none_when_every_line_within_ceiling(self):
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        hw = self._make_product("None Level HW", self.hardware, 1000.0)
        self._make_line(order, hw, 1, 15.0)  # exactly at the 15% ceiling

        self.assertEqual(order.df_blended_risk_score, 0.0)
        self.assertEqual(order.df_risk_level, "none")
        self.assertFalse(order.df_risk_summary)

    def test_risk_level_boundary_against_configurable_threshold(self):
        """DEC-010: the MEDIUM/HIGH boundary is data (ir.config_parameter
        'dealflow.risk_high_min'), not the hardcoded 40. Set it to 27 and
        prove both sides of the boundary respond to the configured value,
        not the default. Single line at a strict 1% ceiling, so
        excess == discount - 1 and score == 9 * excess (6+3 at weight 1)."""
        self.env["ir.config_parameter"].sudo().set_param("dealflow.risk_high_min", "27")
        # 1% rather than 0%: a category ceiling of 0 now means UNSET
        # (it falls back to the tier, then to dealflow.default_max_discount),
        # so a genuinely strict ceiling has to be a real positive number.
        strict = self.env["product.category"].create(
            {"name": "Boundary Test Category", "df_max_discount": 1.0}
        )
        product = self._make_product("Boundary Test Product", strict, 1000.0)
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        line = self._make_line(order, product, 1, 4.0)  # excess=3 -> score=27

        self.assertAlmostEqual(order.df_blended_risk_score, 27.0, places=6)
        self.assertEqual(
            order.df_risk_level, "medium", "score == threshold must stay MEDIUM (condition is score > threshold)"
        )

        line.write({"discount": 5.0})  # excess=4 -> score=36 > 27
        self.assertAlmostEqual(order.df_blended_risk_score, 36.0, places=6)
        self.assertEqual(order.df_risk_level, "high")

    # -- DEC-015 / DEC-009 pricelist reference pricing, both directions -----

    def test_reference_price_without_pricelist_uses_list_price(self):
        """No pricelist on the order -> the DEC-009 degrade path: reference
        price is the catalogue list_price, exactly as before this task."""
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        self.assertFalse(order.pricelist_id)
        hw = self._make_product("No Pricelist HW", self.hardware, 1000.0)
        line = self._make_line(order, hw, 1, 15.0)

        self.assertEqual(line._df_reference_price(), 1000.0)
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)

        line.write({"discount": 20.0})
        self.assertAlmostEqual(line.df_excess_points, 5.0, places=6)

    def test_reference_price_with_pricelist_is_not_double_counted(self):
        """DEC-015: reference price must come from
        pricelist._get_product_price(), confirmed against the installed
        Odoo 17 source (product_pricelist.py: _get_product_price ->
        _compute_price_rule(product, quantity, uom=, date=)). DEC-009: the
        pricelist's own reduction (10% here) must never itself count as rep
        discount - only additional discount on top of the pricelist price
        should register as excess."""
        pricelist = self.env["product.pricelist"].create(
            {
                "name": "Gold Tier Pricelist (test)",
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "applied_on": "3_global",
                            "compute_price": "percentage",
                            "percent_price": 10.0,
                        },
                    )
                ],
            }
        )
        order = self.env["sale.order"].create(
            {"partner_id": self.acme.id, "pricelist_id": pricelist.id}
        )
        hw = self._make_product("Pricelist HW", self.hardware, 1000.0)
        line = self._make_line(order, hw, 1, 0.0)

        # Sanity: Odoo really applied the pricelist to price_unit.
        self.assertAlmostEqual(line.price_unit, 900.0, places=2)
        # The reference price used for governance is the pricelist price...
        self.assertAlmostEqual(line._df_reference_price(), 900.0, places=2)
        # ...so a rep who charges exactly that price adds ZERO extra
        # discount, even though the customer is paying 10% less than list -
        # the pricelist's own cut must not double-count as rep discount.
        self.assertAlmostEqual(line.df_excess_points, 0.0, places=6)

        # Now the rep gives a further 20% on top of the pricelist price
        # (900 -> 720). Effective_ceiling is 15 (Hardware/Gold), so
        # rep_discount_pct(20) - ceiling(15) = 5 points of real excess.
        line.write({"discount": 20.0})
        self.assertAlmostEqual(line.df_excess_points, 5.0, places=4)
