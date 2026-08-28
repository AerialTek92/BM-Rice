/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

class PurchaseDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.resProductStock = useRef("product_stock");
        this.resVendorOut = useRef("vendor_outstanding");
        this.resTopProduct = useRef("top_purchased");
        this.resMonthlyAmt = useRef("monthly_amount");

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });

        onMounted(() => {
            this.renderCharts();
        });
    }

    async renderCharts() {
        const data = await this.orm.call("purchase.order", "get_purchase_dashboard_data", []);

        // 1. Stock Balance (Vertical Bar)
        new window.Chart(this.resProductStock.el, {
            type: "bar",
            data: data.product_stock,
            options: {
                onClick: (ev, el) => { if(el.length > 0) this.openRecord("product.product", data.product_stock.ids[el[0].index]); }
            }
        });

        // 2. Vendor Outstanding (Vertical Bar)
        new window.Chart(this.resVendorOut.el, {
            type: "bar",
            data: data.vendor_outstanding,
            options: {
                onClick: (ev, el) => { if(el.length > 0) this.openRecord("res.partner", data.vendor_outstanding.ids[el[0].index]); }
            }
        });

        // 3. Top Purchased (Horizontal Bar)
        new window.Chart(this.resTopProduct.el, {
            type: "bar",
            data: data.top_purchased,
            options: {
                indexAxis: 'y',
                onClick: (ev, el) => { if(el.length > 0) this.openRecord("product.product", data.top_purchased.ids[el[0].index]); }
            }
        });

        // 4. Monthly Amount (Area Chart)
        new window.Chart(this.resMonthlyAmt.el, {
            type: "line",
            data: data.monthly_amount,
            options: { responsive: true }
        });
    }

    openRecord(model, resId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            res_id: resId,
            views: [[false, 'form']],
            target: 'current',
        });
    }
}

PurchaseDashboard.template = "bop_charts.PurchaseDashboardMain";
registry.category("actions").add("purchase_dashboard_tag", PurchaseDashboard);