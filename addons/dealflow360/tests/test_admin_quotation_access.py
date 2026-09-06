"""The built-in `admin` account must be able to build a quotation.

Reproduced live during a demo: log in as Odoo's own `admin`, open a
quotation, and the form dies before you can type anything with

    AccessError: You are not allowed to access 'DealFlow360 Audit Log'
    (dealflow.audit.log) records. This operation is allowed for the
    following groups: DealFlow360/Admin, /Finance, /Sales Manager, /Sales Rep

base.group_system does not bypass ir.model.access - only the real superuser
does - and base.user_admin was never given any DealFlow360 role, so it had
read rights on none of the dealflow.* models. The quotation form renders
df_audit_log_ids and df_billing_schedule_ids, so it blew up on load.

data/admin_role_data.xml grants base.user_admin the DealFlow360 Admin role.
These tests are the guard against that grant being dropped or silently
skipped again (the record it targets is noupdate, which is why the fix has
to be a <function> call).
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAdminQuotationAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env.ref("base.user_admin")

    def test_admin_holds_the_dealflow_admin_role(self):
        """The grant in data/admin_role_data.xml actually landed."""
        self.assertTrue(
            self.admin_user.has_group("dealflow360.group_dealflow_admin"),
            "base.user_admin lost the DealFlow360 Admin role - every "
            "dealflow.* model becomes unreadable to the account demos are "
            "run from. Check data/admin_role_data.xml is still in the "
            "manifest and still uses <function> (a <record> override is "
            "skipped: base.user_admin is noupdate).",
        )

    def test_admin_can_read_every_dealflow_model(self):
        """No dealflow.* model may be invisible to the administrator."""
        admin_env = self.env(user=self.admin_user)
        denied = []
        for name in sorted(
            m for m in self.env.registry.models if m.startswith("dealflow.")
        ):
            if not admin_env[name].check_access_rights("read", raise_exception=False):
                denied.append(name)
        self.assertFalse(
            denied, "admin has no read access on: %s" % ", ".join(denied)
        )

    def test_admin_can_build_and_open_a_quotation(self):
        """The exact demo flow: create a quotation and load its form fields.

        Creating via the ORM was never the failure - the governance fields are
        stored computes, so they run compute_sudo and pass regardless. The
        failure is reading the form's one2manys back, which is what this
        asserts.
        """
        admin_env = self.env(user=self.admin_user)
        partner = admin_env["res.partner"].search(
            [("df_tier_id", "!=", False)], limit=1
        ) or admin_env["res.partner"].search([("customer_rank", ">", 0)], limit=1)
        self.assertTrue(partner, "no customer available to quote")
        product = admin_env["product.product"].search([("sale_ok", "=", True)], limit=1)
        self.assertTrue(product, "no saleable product available to quote")

        order = admin_env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 5,
                            "discount": 12.0,
                        },
                    )
                ],
            }
        )
        self.assertEqual(order.state, "draft")

        # The two fields the quotation form renders that reference dealflow.*
        # models - these are what raised the AccessError on form load.
        order.invalidate_recordset()
        order.read(["df_audit_log_ids", "df_billing_schedule_ids"])

    def test_quotation_form_view_loads_field_by_field(self):
        """Every field on the quotation form must be readable by admin.

        Reads each field individually rather than in one call so a failure
        names the offending field instead of just the first one.
        """
        import re

        admin_env = self.env(user=self.admin_user)
        SaleOrder = admin_env["sale.order"]
        order = SaleOrder.search([], limit=1, order="id desc")
        if not order:
            self.skipTest("no sale.order to render")

        arch = SaleOrder.get_view(view_type="form")["arch"]
        failures = []
        for fname in sorted(set(re.findall(r'<field name="([a-z_0-9]+)"', arch))):
            if fname not in SaleOrder._fields:
                continue
            try:
                order.read([fname])
            except Exception as exc:  # noqa: BLE001 - report all, not the first
                failures.append("%s (%s)" % (fname, type(exc).__name__))
        self.assertFalse(
            failures,
            "admin cannot read quotation form fields: %s" % ", ".join(failures),
        )
