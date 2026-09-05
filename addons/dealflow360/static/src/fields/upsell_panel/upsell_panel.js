/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

/**
 * Screen 4's embedded upsell/cross-sell panel (DF-009). Bound to the
 * always-present read-only "id" field purely as a mount point - this is
 * not a real field widget, it drives its own RPCs against DF-008's
 * sale.order.get_upsell_recommendations()/action_add_upsell_line()
 * (models/upsell.py). Ranking, projected margin and reason text are all
 * computed server-side; this widget only renders and triggers "Add to
 * Quote", then reloads the record so every DF-002/DF-003 field on the
 * form (margin, risk gauge, order lines) reflects the real new line
 * immediately - no client-side recomputation of governance logic here.
 */
export class DealflowUpsellPanel extends Component {
    static template = "dealflow360.UpsellPanel";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ recommendations: [], loading: true, adding: null });
        onWillStart(() => this.loadRecommendations());
        onWillUpdateProps(() => this.loadRecommendations());
    }

    get orderId() {
        return this.props.record.resId;
    }

    async loadRecommendations() {
        if (!this.orderId) {
            // Unsaved new quotation - no order to recommend against yet.
            Object.assign(this.state, { recommendations: [], loading: false });
            return;
        }
        this.state.loading = true;
        const recommendations = await this.orm.call(
            "sale.order",
            "get_upsell_recommendations",
            [[this.orderId]],
            { limit: 5 }
        );
        Object.assign(this.state, { recommendations, loading: false });
    }

    async addToQuote(productId) {
        this.state.adding = productId;
        try {
            await this.orm.call("sale.order", "action_add_upsell_line", [
                [this.orderId],
                productId,
            ]);
            await this.props.record.load();
            this.notification.add("Added to quote.", { type: "success" });
            await this.loadRecommendations();
        } finally {
            this.state.adding = null;
        }
    }
}

registry.category("fields").add("dealflow_upsell_panel", {
    component: DealflowUpsellPanel,
    supportedTypes: ["integer"],
});
