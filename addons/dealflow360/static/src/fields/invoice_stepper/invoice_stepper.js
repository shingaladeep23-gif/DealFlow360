/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Screen 13's status stepper, built from account.move's own native `state`
 * and `payment_state` - no new field. Odoo's real invoice lifecycle only has
 * three meaningful stops (Draft -> Posted -> Paid); the mockup's separate
 * "Issued"/"Invoiced" steps don't correspond to two different native states,
 * so they're collapsed into one "Posted" step here rather than inventing a
 * field to tell them apart.
 */
export class DealflowInvoiceStepper extends Component {
    static template = "dealflow360.InvoiceStepper";
    static props = { ...standardFieldProps };

    get state() {
        return this.props.record.data.state;
    }
    get paymentState() {
        return this.props.record.data[this.props.name];
    }
    get steps() {
        const cancelled = this.state === "cancel";
        const posted = this.state === "posted";
        const paid = ["paid", "in_payment", "reversed"].includes(this.paymentState);
        return [
            { label: "Confirmed", done: true },
            { label: "Posted", done: posted || paid },
            { label: "Paid", done: paid },
        ].map((s) => ({ ...s, cancelled }));
    }
}

registry.category("fields").add("dealflow_invoice_stepper", {
    component: DealflowInvoiceStepper,
    supportedTypes: ["selection"],
});
