/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Screen 7's approval chain stepper: Submitted -> one node per
 * dealflow.approval.step (role, colored by state) -> Confirmed. Chain
 * length varies (MEDIUM = 1 step, HIGH = 2 steps, per DEC-003/DEC-010),
 * which is why this is a dedicated dynamic widget rather than reusing the
 * fixed 4-node invoice_stepper.
 */
export class DealflowApprovalStepper extends Component {
    static template = "dealflow360.ApprovalStepper";
    static props = { ...standardFieldProps };

    get steps() {
        const stepRecords = this.props.record.data[this.props.name].records;
        const chainState = this.props.record.data.state;
        const roleLabel = (role) => (role === "finance" ? "Finance" : "Sales Manager");
        const nodes = [{ label: "Submitted", status: "done" }];
        for (const rec of stepRecords) {
            const s = rec.data.state;
            nodes.push({
                label: roleLabel(rec.data.role),
                status: s === "approved" ? "done" : s === "pending" ? "current" : s,
            });
        }
        nodes.push({
            label: "Confirmed",
            status: chainState === "approved" ? "done" : "upcoming",
        });
        return nodes;
    }
}

registry.category("fields").add("dealflow_approval_stepper", {
    component: DealflowApprovalStepper,
    supportedTypes: ["one2many"],
});
