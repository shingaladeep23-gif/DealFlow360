"""A1: "Internal users can sign up and log in with standard credentials."

Odoo's auth_signup creates every self-registered account by copying the portal
user template (base.template_portal_user_id), so a signup landed in
User types / Portal with share=True and got a 403 on the backend. That is the
right behaviour for a CUSTOMER being invited to a portal, and the wrong one for
A1, which is about staff joining the workspace.

The two are distinguishable without guessing. Odoo's own signup already
separates them:

  * an INVITED signup carries a partner_id in its values - the portal
    invitation/reset flow resolves the token to an existing partner first.
    That is a customer, and it keeps the native portal behaviour untouched;
  * an UNINVITED signup has no partner. It only happens at all when an
    administrator has set the signup scope to "Free sign up"
    (auth_signup.invitation_scope = b2c) - Odoo raises SignupError otherwise -
    so opening the door is an explicit, revocable configuration decision, not
    something this module forces on.

An uninvited signup therefore becomes an internal user with the Sales Rep role,
which is the least-privileged of the four DealFlow roles: it builds quotations
and submits them for approval, and it can neither approve anything nor reach
the configuration screens.
"""
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _signup_create_user(self, values):
        uninvited = not values.get("partner_id")
        user = super()._signup_create_user(values)
        if not uninvited:
            return user
        record = user if isinstance(user, models.BaseModel) else self.browse(user)
        if not record:
            return user
        # (6, 0, ...) rather than (4, ...): the account was copied from the
        # PORTAL template, so base.group_portal has to come off. share is
        # computed from groups_id, so adding base.group_user is also what
        # flips share back to False and gets the backend to open at all.
        record.sudo().write(
            {
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "dealflow360.group_dealflow_sales_rep"
                            ).id,
                        ],
                    )
                ]
            }
        )
        return user
