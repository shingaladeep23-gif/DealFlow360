/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Read-only gauge for DEC-003's blended discount-risk score. Bind it to
 * df_blended_risk_score; it reads the sibling df_risk_level/df_risk_summary
 * fields off the same record so Screen 4 (Quotation Detail) and Screen 7
 * (Approval Detail, DF-006) can share one widget instead of two hand-built
 * badges that could drift out of sync with DEC-003's wording.
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
        return { none: "No Risk", medium: "Medium Risk", high: "High Risk" }[this.level];
    }
}

registry.category("fields").add("dealflow_risk_gauge", {
    component: DealflowRiskGauge,
    supportedTypes: ["float"],
});
