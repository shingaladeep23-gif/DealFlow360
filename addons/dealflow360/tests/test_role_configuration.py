"""Section 3's role duties have to be REACHABLE, not just described.

Every test here is a "no role can do this" finding reproduced against the four
personas, not a hypothetical:

  * a Sales Manager could not write a discount tier at all (AccessError), and
    no Configuration menu opened for them - against section 3's "Sales Manager:
    configures discount tiers and approval chains";
  * A3's manager-vs-manager+finance threshold was configurable by nobody: the
    fields existed, no menu opened them for any role, and df.admin got an
    AccessError trying to save, because Odoo gates res.config.settings on
    base.group_system;
  * all four personas had write denied on stock.warehouse, so A4 in its
    entirety - create warehouses, configure replenishment, define shipping
    cost weighting - was unreachable by every business-facing role;
  * Finance was blocked from the backorder decisions section 3 assigns to it.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRoleConfiguration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].search([("name", "=", "Acme Corp")], limit=1)

        def _user(login, group_xmlid):
            return cls.env["res.users"].create(
                {
                    "name": login,
                    "login": "%s@dealflow360.test" % login,
                    "email": "%s@dealflow360.test" % login,
                    "groups_id": [(6, 0, [cls.env.ref(group_xmlid).id])],
                }
            )

        cls.admin = _user("cfg_admin", "dealflow360.group_dealflow_admin")
        cls.manager = _user("cfg_manager", "dealflow360.group_dealflow_sales_manager")
        cls.finance = _user("cfg_finance", "dealflow360.group_dealflow_finance")
        cls.rep = _user("cfg_rep", "dealflow360.group_dealflow_sales_rep")

    # -- Sales Manager: discount tiers and approval chains -------------------

    def test_sales_manager_can_configure_a_discount_tier(self):
        tier = self.env.ref("dealflow360.discount_tier_gold")
        tier.with_user(self.manager).write({"max_discount": 16.0})
        self.assertEqual(tier.max_discount, 16.0)

    def test_sales_rep_still_cannot_configure_a_discount_tier(self):
        """The manager's new write access must not have leaked down to the
        role that is governed BY the tiers."""
        tier = self.env.ref("dealflow360.discount_tier_gold")
        with self.assertRaises(AccessError):
            tier.with_user(self.rep).write({"max_discount": 90.0})

    def test_sales_manager_can_save_the_approval_threshold(self):
        """A3: "configure which range needs manager vs manager+finance"."""
        policy = (
            self.env["dealflow.governance.policy"].with_user(self.manager).create({})
        )
        policy.risk_high_min = 27.0
        policy.action_save()

        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param("dealflow.risk_high_min"),
            "27.0",
        )

    def test_admin_can_save_the_approval_threshold(self):
        policy = (
            self.env["dealflow.governance.policy"].with_user(self.admin).create({})
        )
        policy.health_stalled_days = 5
        policy.action_save()
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dealflow.health_stalled_days"),
            "5",
        )

    def test_the_policy_form_opens_on_what_is_currently_in_force(self):
        """Defaults, not field defaults: opening the screen and saving must not
        silently reset a threshold nobody touched."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dealflow.risk_high_min", "33.0"
        )
        policy = (
            self.env["dealflow.governance.policy"].with_user(self.manager).create({})
        )
        self.assertAlmostEqual(policy.risk_high_min, 33.0, places=2)

    def test_a_saved_threshold_actually_re_scores_open_deals(self):
        """The thresholds are read by STORED computes with no @api.depends on
        them - an ir.config_parameter is not a field - so without an explicit
        recompute a saved setting changed nothing anybody could see."""
        laptop = self.env["product.product"].create(
            {
                "name": "Threshold Test Laptop",
                "categ_id": self.env.ref("dealflow360.product_category_hardware").id,
                "type": "consu",
                "list_price": 1000.0,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.acme.id,
                # 18% against a 15% ceiling is 3 points over: 6*3 + 3*3 = 27,
                # comfortably under the default 40 threshold, so this starts
                # as a manager-only approval and there is a real boundary to
                # move. (20% would already score 45 and be HIGH out of the box.)
                "order_line": [
                    (0, 0, {"product_id": laptop.id, "product_uom_qty": 1, "discount": 18.0})
                ],
            }
        )
        self.assertEqual(order.df_risk_level, "medium")
        score = order.df_blended_risk_score

        policy = (
            self.env["dealflow.governance.policy"].with_user(self.manager).create({})
        )
        policy.risk_high_min = score - 1.0
        policy.action_save()

        order.invalidate_recordset(["df_risk_level"])
        self.assertEqual(
            order.df_risk_level,
            "high",
            "lowering the finance threshold below this deal's score must send "
            "it to finance",
        )

    def test_sales_rep_cannot_reach_the_approval_policy(self):
        with self.assertRaises(AccessError):
            self.env["dealflow.governance.policy"].with_user(self.rep).create({})

    # -- Admin: A4 backend setup ---------------------------------------------

    def test_admin_can_create_a_warehouse(self):
        warehouse = (
            self.env["stock.warehouse"]
            .with_user(self.admin)
            .create({"name": "Role Test Depot", "code": "RTD"})
        )
        self.assertTrue(warehouse.id)

    def test_admin_can_set_the_shipping_cost_weighting(self):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        warehouse.with_user(self.admin).write(
            {"df_shipping_cost_weight": 1.4, "df_shipping_base_cost": 22.0}
        )
        self.assertAlmostEqual(warehouse.df_shipping_cost_weight, 1.4, places=2)

    def test_admin_can_create_a_replenishment_rule(self):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        product = self.env["product.product"].search(
            [("type", "=", "product")], limit=1
        )
        rule = (
            self.env["stock.warehouse.orderpoint"]
            .with_user(self.admin)
            .create(
                {
                    "warehouse_id": warehouse.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "product_id": product.id,
                    "product_min_qty": 5.0,
                    "product_max_qty": 50.0,
                }
            )
        )
        self.assertTrue(rule.id)

    # -- A1: an internal user can sign up ------------------------------------

    def test_uninvited_signup_creates_an_internal_user_not_a_portal_one(self):
        """A1: "Internal users can sign up and log in with standard
        credentials". auth_signup copies the PORTAL template, so a signup
        landed in User types / Portal with share=True and got a 403 on the
        backend."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        login = "signup_staff@dealflow360.test"
        self.env["res.users"].sudo().signup(
            {
                "login": login,
                "name": "Signed Up Staff",
                "email": login,
                "password": "Str0ngPassw0rd!",
            }
        )

        user = self.env["res.users"].sudo().search([("login", "=", login)])
        self.assertEqual(len(user), 1)
        self.assertFalse(user.share, "a self-signup must not be a portal user")
        self.assertTrue(user.has_group("base.group_user"))
        self.assertTrue(user.has_group("dealflow360.group_dealflow_sales_rep"))
        self.assertFalse(
            user.has_group("base.group_portal"),
            "the portal group copied from the template must come off",
        )

    def test_signup_grants_only_the_least_privileged_role(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        login = "signup_staff2@dealflow360.test"
        self.env["res.users"].sudo().signup(
            {
                "login": login,
                "name": "Signed Up Staff Two",
                "email": login,
                "password": "Str0ngPassw0rd!",
            }
        )
        user = self.env["res.users"].sudo().search([("login", "=", login)])
        for group in (
            "dealflow360.group_dealflow_sales_manager",
            "dealflow360.group_dealflow_finance",
            "dealflow360.group_dealflow_admin",
        ):
            self.assertFalse(
                user.has_group(group),
                "signing up must not hand out an approval or admin role",
            )

    # -- the fulfillment list must not offer rows the viewer cannot open -----

    def test_a_rep_only_sees_splits_for_their_own_orders(self):
        """Live-reproduced as df.rep: 16 splits listed, one of which raised a
        hard Access Error modal on click, because the list was not filtered by
        the sale.order rule still enforced on drill-down."""
        other_rep = self.env["res.users"].create(
            {
                "name": "cfg_rep_two",
                "login": "cfg_rep_two@dealflow360.test",
                "email": "cfg_rep_two@dealflow360.test",
                "groups_id": [
                    (6, 0, [self.env.ref("dealflow360.group_dealflow_sales_rep").id])
                ],
            }
        )
        mine = self.env["sale.order"].create(
            {"partner_id": self.acme.id, "user_id": self.rep.id}
        )
        theirs = self.env["sale.order"].create(
            {"partner_id": self.acme.id, "user_id": other_rep.id}
        )
        my_split = self.env["dealflow.warehouse.split"].create({"order_id": mine.id})
        their_split = self.env["dealflow.warehouse.split"].create(
            {"order_id": theirs.id}
        )

        visible = self.env["dealflow.warehouse.split"].with_user(self.rep).search([])
        self.assertIn(my_split, visible)
        self.assertNotIn(their_split, visible)

    def test_a_sales_manager_still_sees_every_split(self):
        order = self.env["sale.order"].create(
            {"partner_id": self.acme.id, "user_id": self.rep.id}
        )
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        visible = (
            self.env["dealflow.warehouse.split"].with_user(self.manager).search([])
        )
        self.assertIn(split, visible)

    # -- Finance: backorder decisions ----------------------------------------

    def test_finance_can_act_on_a_fulfillment_split(self):
        """Section 3 gives Finance "warehouse fulfillment splits and backorder
        decisions". It could read every split and then do nothing with one."""
        order = self.env["sale.order"].create({"partner_id": self.acme.id})
        split = self.env["dealflow.warehouse.split"].create({"order_id": order.id})
        split.with_user(self.finance).write({"state": "draft"})
        self.assertEqual(split.state, "draft")
