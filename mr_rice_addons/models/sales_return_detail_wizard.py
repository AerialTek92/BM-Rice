# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class SalesReturnDetailWizard(models.TransientModel):
    _name = 'sales.return.detail.wizard'
    _description = 'Sales Return Detail Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        self.ensure_one()
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_sales_return_detail').report_action(self, data=data)


class ReportSalesReturnDetail(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_sales_return_detail_template'
    _description = 'Sales Return Detail Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
        ]

        sale_orders = self.env['sale.order'].search(domain)
        report_lines = []

        for order in sale_orders:
            for line in order.order_line.filtered(
                    lambda l: l.product_id and not l.display_type and l.product_uom_qty < 0):
                report_lines.append({
                    'sret_no': order.name,
                    'date': order.date_order,
                    'customer': order.partner_id.name or '',
                    'item_name': line.product_id.name,
                    'pcs': abs(line.pcs) if line.pcs else 0.0,
                    'ctn': abs(line.ctn) if line.ctn else 0.0,
                    'qty_kgs': abs(line.product_uom_qty) if line.product_uom_qty else 0.0,
                    'rate': line.price_unit or 0.0,
                    'amount': abs(line.net_amount) if line.net_amount else 0.0,
                    # Aakhri 4 columns khali hain
                    'sale_to': '',
                    'qty2': '',
                    'rate2': '',
                    'amount2': '',
                })

        report_lines.sort(key=itemgetter('customer'))
        grouped_data = []

        for key, group in groupby(report_lines, key=itemgetter('customer')):
            g_lines = list(group)
            grouped_data.append({
                'customer': key,
                'items': g_lines,
                # Sirf Qty aur Amount ka total lagana hai (Picture ke mutabiq)
                'total_qty_kgs': sum(x['qty_kgs'] for x in g_lines),
                'total_amount': sum(x['amount'] for x in g_lines),
            })

        grand_total_qty = sum(x['total_qty_kgs'] for x in grouped_data)
        grand_total_amt = sum(x['total_amount'] for x in grouped_data)

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_qty': grand_total_qty,
            'grand_total_amt': grand_total_amt,
        }
