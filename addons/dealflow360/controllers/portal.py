from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)

QUOTATION_PAGE_SIZE = 20

# Genuinely separate from Odoo's native sale-portal quote/order screens
# (DEC-007/architecture.md §6-7): dedicated routes and templates that expose
# only what AT-08 allows (lines, totals, status, comments, counter-discount,
# confirm) - never margin, internal risk score or approval-chain internals.


class DealflowPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "quotation_count" in counters:
            values["quotation_count"] = request.env["sale.order"].search_count([])
        return values

    def _dealflow_document_check_access(self, order_id, access_token=None):
        """Same pattern Odoo's own portal controllers use for every
        access-token-guarded document (DEC-007's second layer): resolve the
        record as the current portal user (so the DEC-012 record rule
        applies), and only fall back to the share token if that raises.
        Never sudo() before this check - that would skip the rule entirely."""
        order = request.env["sale.order"].browse(order_id)
        order_sudo = order.sudo().exists()
        if not order_sudo:
            raise MissingError(_("This quotation does not exist."))
        try:
            order.check_access_rights("read")
            order.check_access_rule("read")
        except AccessError:
            if not access_token or not consteq(order_sudo.access_token or "", access_token):
                raise
        return order_sudo

    @http.route(["/my/quotations", "/my/quotations/page/<int:page>"], type="http", auth="user", website=True)
    def dealflow_portal_quotations(self, page=1, **kwargs):
        Order = request.env["sale.order"]
        # DEC-012's rule already scopes this search to the logged-in
        # customer's own partner (and child contacts) - no extra partner_id
        # domain needed or wanted here.
        domain = [("state", "!=", "cancel")]
        total = Order.search_count(domain)
        pager = portal_pager(
            url="/my/quotations",
            total=total,
            page=page,
            step=QUOTATION_PAGE_SIZE,
        )
        orders = Order.search(
            domain, order="date_order desc", limit=QUOTATION_PAGE_SIZE, offset=pager["offset"]
        )
        return request.render(
            "dealflow360.portal_my_quotations",
            {
                "orders": orders,
                "pager": pager,
                "page_name": "quotation",
                "default_url": "/my/quotations",
            },
        )

    @http.route(["/my/quotation/<int:order_id>"], type="http", auth="user", website=True)
    def dealflow_portal_quotation_detail(self, order_id, access_token=None, **kwargs):
        # AT-08: a cross-customer request must surface as 403/404, never the
        # document - so this deliberately does not catch AccessError /
        # MissingError into a redirect. Odoo's HTTP layer turns them into the
        # corresponding response.
        order_sudo = self._dealflow_document_check_access(order_id, access_token)
        negotiations = request.env["dealflow.negotiation"].sudo().search(
            [("order_id", "=", order_sudo.id)], order="create_date desc"
        )
        return request.render(
            "dealflow360.portal_my_quotation_detail",
            {
                "order": order_sudo,
                "negotiations": negotiations,
                "page_name": "quotation",
            },
        )

    @http.route(["/my/quotation/<int:order_id>/comment"], type="http", auth="user", methods=["POST"], website=True)
    def dealflow_portal_quotation_comment(self, order_id, access_token=None, **post):
        order_sudo = self._dealflow_document_check_access(order_id, access_token)
        message = (post.get("message") or "").strip()
        if message:
            line_id = post.get("line_id")
            prefix = ""
            if line_id:
                line = request.env["sale.order.line"].sudo().browse(int(line_id))
                if line.exists() and line.order_id == order_sudo:
                    prefix = _("Re: %s — ") % (line.name or line.product_id.display_name)
            order_sudo.message_post(
                body=prefix + message,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return request.redirect(f"/my/quotation/{order_sudo.id}")

    @http.route(["/my/quotation/<int:order_id>/counter"], type="http", auth="user", methods=["POST"], website=True)
    def dealflow_portal_quotation_counter(self, order_id, access_token=None, **post):
        order_sudo = self._dealflow_document_check_access(order_id, access_token)
        if order_sudo.state not in ("draft", "sent"):
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        try:
            pct = float(post.get("counter_discount", ""))
        except ValueError:
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        if not 0 <= pct <= 100:
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        negotiation = request.env["dealflow.negotiation"].sudo().create(
            {"order_id": order_sudo.id, "counter_discount": pct}
        )
        negotiation._apply()
        return request.redirect(f"/my/quotation/{order_sudo.id}")

    @http.route(["/my/quotation/<int:order_id>/confirm"], type="http", auth="user", methods=["POST"], website=True)
    def dealflow_portal_quotation_confirm(self, order_id, access_token=None, **post):
        order_sudo = self._dealflow_document_check_access(order_id, access_token)
        if order_sudo.state not in ("draft", "sent"):
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        pending_negotiation = request.env["dealflow.negotiation"].sudo().search(
            [("order_id", "=", order_sudo.id), ("state", "=", "requires_reapproval")],
            limit=1,
        )
        if pending_negotiation or order_sudo.df_risk_level != "none":
            # DF-004's approval chain will replace this flag once it lands
            # (task_plan.md DF-015) - until then a flagged order cannot be
            # customer-confirmed straight from the portal.
            order_sudo.message_post(
                body=_(
                    "Customer attempted to confirm from the portal while this "
                    "quotation is flagged %s risk; blocked pending manager "
                    "approval."
                )
                % order_sudo.df_risk_level
            )
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        try:
            order_sudo.action_confirm()
        except UserError:
            pass
        return request.redirect(f"/my/quotation/{order_sudo.id}")
