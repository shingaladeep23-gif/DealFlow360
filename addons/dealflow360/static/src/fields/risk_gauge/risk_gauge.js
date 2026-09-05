/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Read-only gauge for the discount-risk score. Bind it to
 * df_blended_risk_score; it reads the sibling df_risk_level/df_risk_summary
 * off the same record, so the quotation and approval screens share one widget
 * rather than two hand-built badges that could drift apart.
 */
export class DealflowRiskGauge extends Component {
    static template = "dealflow360.RiskGauge";
    static props = { ...standardFieldProps };

    get score() {
        return this.props.record.data[this.props.name] || 0;
    }
    get level() {
        return this.props.record.data.df_risk_level || "none";
    }
    get summary() {
        return this.props.record.data.df_risk_summary;
    }
    get levelLabel() {
        // Matches df_risk_level's own selection labels. The gauge used to
        // invent its own wording ("High Risk") and sit right above the field
        // label ("Needs manager + finance"), so one deal carried two
        // different names for the same state.
        return {
            none: "Within limits",
            medium: "Over limit",
            high: "Well over limit",
        }[this.level];
    }
}

registry.category("fields").add("dealflow_risk_gauge", {
    component: DealflowRiskGauge,
    supportedTypes: ["float"],
});
