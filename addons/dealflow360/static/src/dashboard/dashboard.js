/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Screen 2 - Sales Dashboard / Home. Every number here is a real ORM read
 * over sale.order (see docs/ui_spec.md Screen 2) - no hardcoded figures.
 * "Pending Approvals" reads df_pipeline_stage='pending_approval', which is
 * a real stored field but only ever populated once DF-004's approval
 * routing lands (see models/sale_order.py::_compute_df_pipeline_stage) -
 * until then it honestly reads 0, which is correct, not a placeholder.
 * There is no dealflow.audit.log model yet, so "Recent Activity" is built
 * from real sale.order write_date ordering instead of inventing one.
 */
export class DealflowDashboard extends Component {
    static template = "dealflow360.Dashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            openQuotations: 0,
            pendingApprovals: 0,
            atRiskDeals: 0,
            recentOrders: [],
            loading: true,
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        const [openQuotations, pendingApprovals, atRiskDeals, recentOrders] =
            await Promise.all([
                this.orm.searchCount("sale.order", [
                    ["state", "in", ["draft", "sent"]],
                ]),
                this.orm.searchCount("sale.order", [
                    ["df_pipeline_stage", "=", "pending_approval"],
                ]),
                this.orm.searchCount("sale.order", [
                    ["df_risk_level", "in", ["medium", "high"]],
                ]),
                this.orm.searchRead(
                    "sale.order",
                    [],
                    ["name", "partner_id", "amount_total", "write_date", "df_risk_level"],
                    { limit: 6, order: "write_date desc" }
                ),
            ]);
        Object.assign(this.state, {
            openQuotations,
            pendingApprovals,
            atRiskDeals,
            recentOrders,
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
