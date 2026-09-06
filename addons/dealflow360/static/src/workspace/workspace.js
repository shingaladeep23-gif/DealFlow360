/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * B1 - the Sales Workspace (rep experience).
 *
 * The problem statement describes a workspace with its own top menu
 * (Quotations, Pipeline) and three actions (Reload Data, Go to Back-end,
 * Close Workspace). None of it existed: the product shipped the stock Odoo
 * backend menu and nothing else, so "Sales Frontend (Rep Workspace
 * Experience)" was the section of the spec with the least behind it after
 * reporting.
 *
 * Both tabs read real sale.order rows. The pipeline groups by the stored
 * df_pipeline_stage rather than re-deriving stages client-side, so the board
 * and the Kanban view can never disagree about where a deal sits.
 */
const STAGES = [
    { key: "draft", label: "Draft" },
    { key: "pending_approval", label: "Waiting for approval" },
    { key: "approved", label: "Approved" },
    { key: "negotiation", label: "In negotiation" },
    { key: "confirmed", label: "Confirmed" },
];

const RISK_LABELS = {
    none: "Within limits",
    medium: "Manager approval",
    high: "Manager + finance",
};

// B2 asks a quotation card to carry its STAGE. The card used to show the risk
// level instead, which answers a different question: risk says whether the
// deal needs a signature, stage says where it has actually got to. A rep
// scanning the list wants "waiting for approval" / "confirmed", not "manager +
// finance" on a deal that was signed off last week. Risk is still on the card,
// as the colour stripe down its edge.
const STAGE_LABELS = Object.fromEntries(
    [
        ["draft", "Draft"],
        ["pending_approval", "Waiting for approval"],
        ["approved", "Approved"],
        ["negotiation", "In negotiation"],
        ["confirmed", "Confirmed"],
    ]
);

export class DealflowWorkspace extends Component {
    static template = "dealflow360.Workspace";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.stages = STAGES;
        this.state = useState({
            tab: "quotations",
            orders: [],
            loading: true,
            reloading: false,
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        const orders = await this.orm.searchRead(
            "sale.order",
            [["state", "in", ["draft", "sent", "sale"]]],
            [
                "name",
                "partner_id",
                "amount_total",
                "currency_id",
                "state",
                "df_pipeline_stage",
                "df_risk_level",
                "df_margin_pct",
                "df_health_status",
            ],
            { order: "date_order desc", limit: 200 }
        );
        Object.assign(this.state, {
            orders: orders.map((order) => ({
                ...order,
                amountLabel: formatMonetary(order.amount_total, {
                    currencyId: order.currency_id && order.currency_id[0],
                }),
                riskLabel: RISK_LABELS[order.df_risk_level] || order.df_risk_level,
                stageLabel:
                    STAGE_LABELS[order.df_pipeline_stage] || order.df_pipeline_stage,
            })),
            loading: false,
        });
    }

    get quotations() {
        // "the list of active and draft quotations" - a confirmed order is no
        // longer a quotation, so it belongs on the pipeline board only.
        return this.state.orders.filter((o) => o.state !== "sale");
    }

    ordersInStage(stageKey) {
        return this.state.orders.filter((o) => o.df_pipeline_stage === stageKey);
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    /** B1: "Reload Data - Refreshes pricing, stock and approval data." */
    async reloadData() {
        this.state.reloading = true;
        try {
            const result = await this.orm.call(
                "sale.order",
                "action_df_reload_workspace_data",
                []
            );
            await this.loadData();
            this.notification.add(
                `Refreshed ${result.orders_refreshed} deal(s); ${result.at_risk} need attention.`,
                { type: "success" }
            );
        } finally {
            this.state.reloading = false;
        }
    }

    /** B1: "Go to Back-end - Opens the configuration and settings screen." */
    goToBackend() {
        this.action.doAction("dealflow360.action_dealflow_discount_tier", {
            clearBreadcrumbs: true,
        });
    }

    /** B1: "Close Workspace - Ends the current working session view." */
    closeWorkspace() {
        this.action.doAction("dealflow360.action_dealflow_dashboard", {
            clearBreadcrumbs: true,
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

    newQuotation() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("dealflow_workspace", DealflowWorkspace);
