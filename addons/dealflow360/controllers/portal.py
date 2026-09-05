from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)

QUOTATION_PAGE_SIZE = 20

# What /my/quotations can be filtered down to, and the ONE definition each of
# those filters has. The portal home counters below are computed from this same
# dict, which is the whole point: a card that says "3" and a list that shows 0
# rows is the bug this replaces, and it can only be fixed for good by making
# the badge and the page read from a single source.
#
# "open" is a quotation the customer can still act on. A confirmed order is not
# one (it is on "Your Orders"), and a cancelled one is not either.
QUOTATION_FILTERS = {
    "all": [("state", "!=", "cancel")],
    "to_review": [("state", "in", ("draft", "sent"))],
}
DEFAULT_QUOTATION_FILTER = "all"

# Genuinely separate from Odoo's native sale-portal quote/order screens
# (DEC-007/architecture.md §6-7): dedicated routes and templates that expose
# only what AT-08 allows (lines, totals, status, comments, counter-discount,
# confirm) - never margin, internal risk score or approval-chain internals.


class DealflowPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        """Portal home badge counts.

        Both counters below used to be one line - `quotation_count =
        search_count([])` - and that empty domain is the whole of bug "the
        dashboard says 3 pending quotes but the page is empty". It counted
        EVERY order the customer could see: confirmed ones, cancelled ones,
        orders already listed under "Your Orders". Meanwhile `sale`'s own
        "Quotations to review" alert reads this very counter and links to
        /my/quotes, whose domain is state == 'sent' - so the badge and the
        destination were counting two different things by construction and
        could not agree. Live-reproduced: badge 18, page 1 row.

        Each counter is now the search_count of exactly the domain the page it
        links to will run (see QUOTATION_FILTERS), so the number on the card is
        the number of rows behind it.
        """
        values = super()._prepare_home_portal_values(counters)
        Order = request.env["sale.order"]
        # DEC-012's record rule already scopes these to the logged-in
        # customer's own partner - no partner_id term needed or wanted.
        if "quotation_count" in counters:
            values["quotation_count"] = Order.search_count(
                QUOTATION_FILTERS["to_review"]
            )
        if "df_quotation_count" in counters:
            values["df_quotation_count"] = Order.search_count(
                QUOTATION_FILTERS["all"]
            )
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
    def dealflow_portal_quotations(self, page=1, filterby=None, **kwargs):
        Order = request.env["sale.order"]
        # DEC-012's rule already scopes this search to the logged-in
        # customer's own partner (and child contacts) - no extra partner_id
        # domain needed or wanted here.
        #
        # filterby comes off the portal home cards. An unknown value falls back
        # to "all" rather than erroring: it arrives from a URL the customer can
        # edit.
        if filterby not in QUOTATION_FILTERS:
            filterby = DEFAULT_QUOTATION_FILTER
        domain = QUOTATION_FILTERS[filterby]
        total = Order.search_count(domain)
        pager = portal_pager(
            url="/my/quotations",
            url_args={"filterby": filterby},
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
                "filterby": filterby,
            },
        )

    def _dealflow_confirm_blocked(self, order):
        """Whether the Confirm button should render disabled. Reflects only
        the yes/no fact that a chain is outstanding - never the role, step
        or score behind it (AT-08 forbids exposing approval-chain internals
        to the customer)."""
        if request.env["dealflow.negotiation"].sudo()._open_for_order(order):
            # The customer has asked for a change and nobody has answered yet.
            # Letting them confirm now would mean confirming terms they have
            # themselves said they do not accept.
            return True
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
        Negotiation = request.env["dealflow.negotiation"].sudo()
        if Negotiation._open_for_order(order_sudo):
            # One outstanding request at a time - otherwise a customer can
            # queue up proposals faster than a rep can answer them.
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        # RECORDED, not applied. This used to call negotiation._apply() inline,
        # which rewrote the order's prices on the spot with nobody in the loop:
        # a portal user could give themselves any discount inside their tier
        # ceiling and then confirm their own order. Acceptance is a sales-side
        # decision now (dealflow.negotiation.action_accept, reachable from the
        # internal Negotiations screen).
        Negotiation.create(
            {"order_id": order_sudo.id, "counter_discount": pct}
        )
        order_sudo.message_post(
            body=_(
                "Customer requested a %.2f%% discount through the portal."
            )
            % pct,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        return request.redirect(f"/my/quotation/{order_sudo.id}")

    @http.route(["/my/quotation/<int:order_id>/confirm"], type="http", auth="user", methods=["POST"], website=True)
    def dealflow_portal_quotation_confirm(self, order_id, access_token=None, **post):
        order_sudo = self._dealflow_document_check_access(order_id, access_token)
        if order_sudo.state not in ("draft", "sent"):
            return request.redirect(f"/my/quotation/{order_sudo.id}")
        if request.env["dealflow.negotiation"].sudo()._open_for_order(order_sudo):
            # Server-side, not just the disabled button. _dealflow_confirm_blocked
            # only controls how the form RENDERS; a POST straight to this route
            # ignores it entirely, so without this check a customer with an
            # unanswered request could still confirm the terms they had just
            # disputed. Caught by
            # test_customer_cannot_confirm_while_their_request_is_unanswered.
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
