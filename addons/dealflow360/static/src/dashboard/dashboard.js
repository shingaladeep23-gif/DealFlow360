/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Sales dashboard / home. Every number is a real ORM read over sale.order -
 * no hardcoded figures.
 *
 * Each card is a question the user actually has ("what needs signing off?"),
 * and clicking it opens the matching filtered list, so the dashboard is a way
 * INTO the work rather than a wall of statistics. Risk levels are rendered
 * through the field's own selection labels rather than their raw stored
 * values - the dashboard used to print "none"/"medium"/"high" straight from
 * the database, which meant nothing to a salesperson.
 */
// The stored values are none/medium/high; these are what a salesperson needs
// to read off a row - the consequence, not the severity band.
const RISK_LABELS = {
    none: "Within limits",
    medium: "Manager approval",
    high: "Manager + finance",
};

export class DealflowDashboard extends Component {
    static template = "dealflow360.Dashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            openQuotations: 0,
            pendingApprovals: 0,
            approvedDeals: 0,
            atRiskDeals: 0,
            recentOrders: [],
            loading: true,
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        const [
            openQuotations,
            pendingApprovals,
            approvedDeals,
            atRiskDeals,
            recentOrders,
        ] = await Promise.all([
                this.orm.searchCount("sale.order", [
                    ["state", "in", ["draft", "sent"]],
                ]),
                this.orm.searchCount("sale.order", [
                    ["df_pipeline_stage", "=", "pending_approval"],
                ]),
                // The card that was missing. A deal that has cleared every
                // approval step goes back to being the REP's move - the
                // customer has to accept it - but the dashboard only ever
                // showed what was open, what was stuck in someone else's queue
                // and what was over the limit. A fully approved quotation
                // appeared on none of them as anything distinguishable, so
                // "manager and finance approved it and then it vanished" was
                // the honest description of the rep's experience.
                this.orm.searchCount("sale.order", [
                    ["df_pipeline_stage", "=", "approved"],
                ]),
                this.orm.searchCount("sale.order", [
                    ["df_risk_level", "in", ["medium", "high"]],
                ]),
                this.orm.searchRead(
                    "sale.order",
                    [],
                    [
                        "name",
                        "partner_id",
                        "amount_total",
                        "currency_id",
                        "write_date",
                        "df_risk_level",
                    ],
                    { limit: 6, order: "write_date desc" }
                ),
            ]);
        Object.assign(this.state, {
            openQuotations,
            pendingApprovals,
            approvedDeals,
            atRiskDeals,
            recentOrders: recentOrders.map((order) => ({
                ...order,
                amountLabel: formatMonetary(order.amount_total, {
                    currencyId: order.currency_id && order.currency_id[0],
                }),
                riskLabel: RISK_LABELS[order.df_risk_level] || order.df_risk_level,
            })),
            loading: false,
        });
    }

    async openNewQuotation() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openQuotations(domain = []) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Quotations",
            res_model: "sale.order",
            view_mode: "kanban,tree,form",
            views: [[false, "kanban"], [false, "tree"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    openOrder(orderId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("dealflow_dashboard", DealflowDashboard);
