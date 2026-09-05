/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Subscriptions list. One recurring order line IS one subscription (there is
 * no separate subscription model), so this reads sale.order.line directly.
 * Filter badges are real search_count's, not decoration.
 */
export class DealflowSubscriptions extends Component {
    static template = "dealflow360.Subscriptions";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            counts: { active: 0, paused: 0, cancelled: 0 },
            rows: [],
            filter: "active",
            loading: true,
        });
        onWillStart(() => this.loadData());
    }

    get filteredRows() {
        return this.state.rows.filter((r) => r.df_sub_state === this.state.filter);
    }

    setFilter(value) {
        this.state.filter = value;
    }

    async loadData() {
        const domain = [["df_sub_state", "!=", false]];
        const [active, paused, cancelled, rows] = await Promise.all([
            this.orm.searchCount("sale.order.line", [["df_sub_state", "=", "active"]]),
            this.orm.searchCount("sale.order.line", [["df_sub_state", "=", "paused"]]),
            this.orm.searchCount("sale.order.line", [["df_sub_state", "=", "cancelled"]]),
            this.orm.searchRead(
                "sale.order.line",
                domain,
                [
                    "order_id",
                    "product_id",
                    "df_sub_state",
                    "df_sub_next_bill_date",
                    "df_mrr",
                    "currency_id",
                ],
                { limit: 80 }
            ),
        ]);

        const productIds = [...new Set(rows.map((r) => r.product_id[0]))];
        const products = productIds.length
            ? await this.orm.read(
                  "product.product",
                  productIds,
                  ["df_recurring_plan_id"]
              )
            : [];
        const planByProduct = {};
        for (const p of products) {
            planByProduct[p.id] = p.df_recurring_plan_id || false;
        }
        const planIds = [...new Set(products.map((p) => p.df_recurring_plan_id?.[0]).filter(Boolean))];
        const plans = planIds.length
            ? await this.orm.read("dealflow.recurring.plan", planIds, ["name", "interval"])
            : [];
        const planById = {};
        for (const pl of plans) {
            planById[pl.id] = pl;
        }

        // "monthly" straight out of the database reads like a raw enum on a
        // screen a salesperson uses; say how often it actually bills.
        const CYCLE_LABELS = {
            monthly: "Every month",
            quarterly: "Every 3 months",
            yearly: "Every year",
        };
        for (const row of rows) {
            const plan = planByProduct[row.product_id[0]];
            const planRec = plan ? planById[plan[0]] : false;
            row.planName = planRec ? planRec.name : "—";
            row.cycle = planRec ? CYCLE_LABELS[planRec.interval] || planRec.interval : "—";
            row.mrrLabel = formatMonetary(row.df_mrr, {
                currencyId: row.currency_id && row.currency_id[0],
            });
        }

        Object.assign(this.state, {
            counts: { active, paused, cancelled },
            rows,
            loading: false,
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

registry.category("actions").add("dealflow_subscriptions", DealflowSubscriptions);
