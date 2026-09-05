/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Screen 7 - Approval Detail. Replaces the plain "state" column of a
 * dealflow.approval.step row: a colored badge normally, or Approve /
 * Reject / Request Revision buttons when this step is the actionable one
 * (state == 'pending'). Calls dealflow.approval.step.action_approve/
 * action_reject/action_request_revision directly (DF-004, models/
 * approval.py) - reject/revision require a mandatory reason, collected
 * via a plain prompt since adding a wizard model is out of this lane
 * (views/static only, no models/).
 */
export class DealflowApprovalStepActions extends Component {
    static template = "dealflow360.ApprovalStepActions";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get state() {
        return this.props.record.data[this.props.name];
    }
    get isPending() {
        return this.state === "pending";
    }
    get stateLabel() {
        return {
            waiting: "Waiting",
            pending: "Pending",
            approved: "Approved",
            rejected: "Rejected",
            revision: "Revision Requested",
        }[this.state];
    }
    get roleLabel() {
        return this.props.record.data.role === "finance" ? "Finance" : "Sales Manager";
    }

    async _reload() {
        await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }

    async onApprove() {
        await this.orm.call("dealflow.approval.step", "action_approve", [
            [this.props.record.resId],
        ]);
        this.notification.add(`Approved as ${this.roleLabel}.`, { type: "success" });
        await this._reload();
    }

    async onReject() {
        const reason = window.prompt("Reason for rejecting this quotation:");
        if (!reason) {
            return;
        }
        await this.orm.call("dealflow.approval.step", "action_reject", [
            [this.props.record.resId],
            reason,
        ]);
        this.notification.add("Quotation rejected.", { type: "danger" });
        await this._reload();
    }

    async onRequestRevision() {
        const reason = window.prompt("What needs to change before resubmitting?");
        if (!reason) {
            return;
        }
        await this.orm.call("dealflow.approval.step", "action_request_revision", [
            [this.props.record.resId],
            reason,
        ]);
        this.notification.add("Revision requested.", { type: "warning" });
        await this._reload();
    }
}

registry.category("fields").add("dealflow_approval_step_actions", {
    component: DealflowApprovalStepActions,
    supportedTypes: ["selection"],
});
