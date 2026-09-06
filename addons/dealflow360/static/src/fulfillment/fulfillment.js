/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Screen 6 - Fulfillment and Stock (List). A single Odoo tree view can't
 * span two different models (stock.quant + dealflow.warehouse.split), so
 * this combines both via two real ORM reads in one OWL page, same pattern
 * as the Sales Dashboard (dashboard.js). Every row is real: live
 * stock.quant on-hand/reserved, and DF-010's actual allocation splits.
 */
export class DealflowFulfillment extends Component {
    static template = "dealflow360.Fulfillment";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            stockRows: [],
            splits: [],
            loading: true,
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        // stock.quant.warehouse_id is not SQL-groupable in this Odoo build
        // (ValueError: Cannot convert field stock.quant.warehouse_id to SQL
        // from read_group) - read raw quants and aggregate client-side
        // instead of using server-side read_group on that field.
        const [quants, splits] = await Promise.all([
            this.orm.searchRead(
                "stock.quant",
                [["location_id.usage", "=", "internal"], ["quantity", "!=", 0]],
                ["warehouse_id", "product_id", "quantity", "reserved_quantity"],
                { limit: 300 }
            ),
            // No explicit domain: the record rules in
            // security/dealflow_security.xml scope this to the splits the
            // viewer can actually OPEN. Before those existed this list showed
            // every split in the database while the sale.order behind it was
            // still scoped by Odoo's "Own Documents Only" rule, so clicking a
            // colleague's row raised a hard Access Error modal.
            //
            // df_can_consolidate / df_consolidatable_qty are live computes
            // over real stock.quant, which is what lets B6's "stock has
            // arrived" prompt appear here without anyone pressing anything.
            this.orm.searchRead(
                "dealflow.warehouse.split",
                [],
                [
                    "order_id",
                    "partner_id",
                    "state",
                    "shipment_count",
                    "has_backorder",
                    "df_estimated_shipping_cost",
                    "df_can_consolidate",
                    "df_consolidatable_qty",
                    "currency_id",
                ],
                { order: "create_date desc", limit: 20 }
            ),
        ]);
        const byKey = {};
        for (const q of quants) {
            if (!q.warehouse_id || !q.product_id) {
                continue;
            }
            const key = q.warehouse_id[0] + ":" + q.product_id[0];
            if (!byKey[key]) {
                byKey[key] = {
                    warehouse: q.warehouse_id[1],
                    product: q.product_id[1],
                    onHand: 0,
                    reserved: 0,
                };
            }
            byKey[key].onHand += q.quantity;
            byKey[key].reserved += q.reserved_quantity;
        }
        const stockRows = Object.values(byKey)
            .map((row) => ({ ...row, available: row.onHand - row.reserved }))
            .sort((a, b) => a.warehouse.localeCompare(b.warehouse) || a.product.localeCompare(b.product));

        Object.assign(this.state, { stockRows, splits, loading: false });
    }

    /** B6 asks this screen to show an estimated shipment cost, so it has to
     *  read as money rather than as a bare float. */
    formatCost(split) {
        return formatMonetary(split.df_estimated_shipping_cost || 0, {
            currencyId: split.currency_id && split.currency_id[0],
        });
    }

    openSplit(splitId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dealflow.warehouse.split",
            res_id: splitId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("dealflow_fulfillment", DealflowFulfillment);
