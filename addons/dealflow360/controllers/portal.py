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

    def _dealflow_portal_status(self, order, has_negotiation):
        """AT-08 wants the customer-facing status vocabulary Sent / Under
        Negotiation / Confirmed - sale.order.df_pipeline_stage doesn't cover
        this (it's an internal Kanban grouping with no 'sent' value at all,
        and 'negotiation' can only be driven by this portal's own
        dealflow.negotiation records - see the seam comment on
        models/sale_order.py). Computed here instead of adding a dependency
        on that field, since it lives in Atlas's models/ lane."""
        if order.state == "cancel":
            return _("Cancelled")
        if order.state == "sale":
            return _("Confirmed")
        if has_negotiation:
            return _("Under Negotiation")
        if order.state == "sent":
            return _("Sent")
        return _("Draft")

    def _dealflow_portal_status_badge_class(self, order, has_negotiation):
        """Same inputs as _dealflow_portal_status, kept separate so the CSS
        class never depends on the translated label text."""
        if order.state == "cancel":
            return "o_df_portal_badge_cancelled"
        if order.state == "sale":
            return "o_df_portal_badge_confirmed"
        if has_negotiation:
            return "o_df_portal_badge_negotiation"
        if order.state == "sent":
            return "o_df_portal_badge_sent"
        return "o_df_portal_badge_draft"

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
        negotiated_order_ids = set(
            request.env["dealflow.negotiation"]
            .sudo()
            .search([("order_id", "in", orders.ids)])
            .mapped("order_id.id")
        )
        statuses = {}
        status_classes = {}
        for order in orders:
            has_negotiation = order.id in negotiated_order_ids
            statuses[order.id] = self._dealflow_portal_status(order, has_negotiation)
            status_classes[order.id] = self._dealflow_portal_status_badge_class(order, has_negotiation)
        return request.render(
            "dealflow360.portal_my_quotations",
            {
                "orders": orders,
                "statuses": statuses,
                "status_classes": status_classes,
                "pager": pager,
                "page_name": "quotation",
                "default_url": "/my/quotations",
            },
        )

    def _dealflow_confirm_blocked(self, order):
        """Whether the Confirm button should render disabled. Reflects only
        the yes/no fact that a chain is outstanding - never the role, step
        or score behind it (AT-08 forbids exposing approval-chain internals
        to the customer)."""
        approval = order.df_approval_id
        return bool(approval) and approval.state != "approved"

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
        # Only message_type == 'comment' ever reaches the portal - internal
        # audit notes (the counter-discount/confirm-attempt log lines this
        # controller itself posts) default to 'note' and are filtered out
        # here by construction, not by an extra flag.
        comments = order_sudo.sudo().message_ids.filtered(
            lambda m: m.message_type == "comment"
        ).sorted("date")
        has_negotiation = bool(negotiations)
        return request.render(
            "dealflow360.portal_my_quotation_detail",
            {
                "order": order_sudo,
                "portal_status": self._dealflow_portal_status(order_sudo, has_negotiation),
                "portal_status_class": self._dealflow_portal_status_badge_class(order_sudo, has_negotiation),
                "negotiations": negotiations,
                "comments": comments,
                "confirm_blocked": self._dealflow_confirm_blocked(order_sudo),
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
        # DF-015: sale.order.action_confirm (models/sale_order.py) is now the
        # single source of truth for whether a flagged order may confirm -
        # it checks df_approval_id.state directly (approved -> proceeds,
        # pending -> raises). A pre-check here on df_risk_level/negotiation
        # history was wrong: risk level and the negotiation record's state
        # don't reset once a chain is approved, so that gate blocked
        # confirmation forever even after manager+finance approval.
        try:
            order_sudo.action_confirm()
        except UserError as exc:
            # Still pending an approval step - a genuine block with nothing to
            # persist.
            order_sudo.message_post(
                body=_("Customer attempted to confirm from the portal: %s")
                % str(exc)
            )
        else:
            # action_confirm no longer raises when it ROUTES an order for
            # approval (that raise rolled the routing back - see
            # models/sale_order.py); it returns a notification action and
            # leaves the order unconfirmed. Read the real state back rather
            # than inferring success from "no exception".
            if order_sudo.state not in ("sale", "done"):
                order_sudo.message_post(
                    body=_(
                        "Customer attempted to confirm from the portal. The "
                        "quotation exceeded its discount ceiling and has been "
                        "routed for approval instead."
                    )
                )
        return request.redirect(f"/my/quotation/{order_sudo.id}")
