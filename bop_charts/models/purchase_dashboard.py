from odoo import api, models, fields
from dateutil.relativedelta import relativedelta


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.model
    def get_purchase_dashboard_data(self):
        return {
            "product_stock": self._get_product_closing_balance(),
            "vendor_outstanding": self._get_vendor_outstanding_payment(),
            "top_purchased": self._get_top_purchased_products(),
            "monthly_amount": self._get_monthly_purchase_amount(),
        }

    # 1. Product Stock (Only > 0)
    def _get_product_closing_balance(self):
        products = self.env['product.product'].search([('active', '=', True)])
        filtered_products = [p for p in products if p.qty_available > 0]
        sorted_products = sorted(filtered_products, key=lambda p: p.qty_available, reverse=True)[:10]
        return {
            "labels": [p.name for p in sorted_products],
            "ids": [p.id for p in sorted_products],
            "datasets": [{
                "label": "Stock Balance",
                "data": [p.qty_available for p in sorted_products],
                "backgroundColor": "#007bff",
            }]
        }

    # 2. Vendor Outstanding (Only > 0)
    def _get_vendor_outstanding_payment(self):
        vendors = self.env['res.partner'].search([('is_company', '=', True), ('active', '=', True)])
        filtered_vendors = [v for v in vendors if v.total_due > 0]
        sorted_vendors = sorted(filtered_vendors, key=lambda v: v.total_due, reverse=True)[:10]
        return {
            "labels": [v.name for v in sorted_vendors],
            "ids": [v.id for v in sorted_vendors],
            "datasets": [{
                "label": "Outstanding Amount",
                "data": [v.total_due for v in sorted_vendors],
                "backgroundColor": "#dc3545",
            }]
        }

    # 3. Top Purchased Products (Horizontal Bar)
    def _get_top_purchased_products(self):
        lines = self.env['purchase.order.line'].read_group(
            [('state', 'in', ['purchase', 'done']), ('product_qty', '>', 0)],
            ['product_id', 'product_qty'],
            ['product_id'],
            limit=10, orderby='product_qty desc'
        )
        return {
            "labels": [line['product_id'][1] for line in lines],
            "ids": [line['product_id'][0] for line in lines],
            "datasets": [{
                "label": "Qty Purchased",
                "data": [line['product_qty'] for line in lines],
                "backgroundColor": "#ffc107",
            }]
        }

    # 4. Monthly Purchase Amount (Area Chart)
    def _get_monthly_purchase_amount(self):
        labels, data = [], []
        today = fields.Date.context_today(self)
        for i in range(5, -1, -1):
            date_cursor = today - relativedelta(months=i)
            month_label = date_cursor.strftime('%B %Y')
            start = date_cursor.replace(day=1)
            end = start + relativedelta(months=1, days=-1)

            orders = self.search([
                ('date_approve', '>=', start), ('date_approve', '<=', end),
                ('state', 'in', ['purchase', 'done'])
            ])

            labels.append(month_label)
            data.append(sum(orders.mapped('amount_total')))

        return {
            "labels": labels,
            "datasets": [{
                "label": "Purchase Amount",
                "data": data,
                "borderColor": "#28a745",
                "backgroundColor": "rgba(40, 167, 69, 0.2)",
                "fill": True,
                "tension": 0.4
            }]
        }
