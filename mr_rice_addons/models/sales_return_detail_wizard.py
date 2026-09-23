# # -*- coding: utf-8 -*-
# from odoo import models, fields, api
# from itertools import groupby
# from operator import itemgetter
#
#
# class SalesReturnDetailWizard(models.TransientModel):
#     _name = 'sales.return.detail.wizard'
#     _description = 'Sales Return Detail Report Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         self.ensure_one()
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_sales_return_detail').report_action(self, data=data)
#
#
# class ReportSalesReturnDetail(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_sales_return_detail_template'
#     _description = 'Sales Return Detail Report'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         domain = [
#             ('state', 'in', ['sale', 'done']),
#             ('date_order', '>=', data['date_from']),
#             ('date_order', '<=', data['date_to']),
#         ]
#
#         sale_orders = self.env['sale.order'].search(domain)
#         report_lines = []
#
#         for order in sale_orders:
#             for line in order.order_line.filtered(
#                     lambda l: l.product_id and not l.display_type and l.product_uom_qty < 0):
#                 report_lines.append({
#                     'sret_no': order.name,
#                     'date': order.date_order,
#                     'customer': order.partner_id.name or '',
#                     'item_name': line.product_id.name,
#                     'pcs': abs(line.pcs) if line.pcs else 0.0,
#                     'ctn': abs(line.ctn) if line.ctn else 0.0,
#                     'qty_kgs': abs(line.product_uom_qty) if line.product_uom_qty else 0.0,
#                     'rate': line.price_unit or 0.0,
#                     'amount': abs(line.net_amount) if line.net_amount else 0.0,
#                     # Aakhri 4 columns khali hain
#                     'sale_to': '',
#                     'qty2': '',
#                     'rate2': '',
#                     'amount2': '',
#                 })
#
#         report_lines.sort(key=itemgetter('customer'))
#         grouped_data = []
#
#         for key, group in groupby(report_lines, key=itemgetter('customer')):
#             g_lines = list(group)
#             grouped_data.append({
#                 'customer': key,
#                 'items': g_lines,
#                 # Sirf Qty aur Amount ka total lagana hai (Picture ke mutabiq)
#                 'total_qty_kgs': sum(x['qty_kgs'] for x in g_lines),
#                 'total_amount': sum(x['amount'] for x in g_lines),
#             })
#
#         grand_total_qty = sum(x['total_qty_kgs'] for x in grouped_data)
#         grand_total_amt = sum(x['total_amount'] for x in grouped_data)
#
#         return {
#             'data': data,
#             'grouped_data': grouped_data,
#             'grand_total_qty': grand_total_qty,
#             'grand_total_amt': grand_total_amt,
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class SalesReturnDetailWizard(models.TransientModel):
    _name = 'sales.return.detail.wizard'
    _description = 'Sales Return Detail Report Wizard'

    # Original & Reference Fields
    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_order', 'Order Date'),
        ('create_date', 'System Date')
    ], string='Date Type', default='date_order', required=True)

    partner_id = fields.Many2one('res.partner', string='Customer')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')
    sale_ids = fields.Many2many('sale.order', string='Sales Memos', domain="[('state', 'in', ['sale', 'done'])]")
    contract_type = fields.Selection([('local', 'Local'), ('export', 'Export')], string='Contract Type')

    def action_print_report(self):
        self.ensure_one()
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_sales_return_detail').report_action(self, data=data)


class ReportSalesReturnDetail(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_sales_return_detail_template'
    _description = 'Sales Return Detail Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_f = data.get('date_filter_type') or 'date_order'

        # Base Domain for Returns (Negative Quantity)
        domain = [
            ('state', 'in', ['sale', 'done']),
            (date_f, '>=', data['date_from']),
            (date_f, '<=', data['date_to']),
        ]

        # Wizard Filters
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))
        if data.get('contract_type'):
            domain.append(('contract_type', '=', data['contract_type']))
        if data.get('sale_ids'):
            domain.append(('id', 'in', data['sale_ids']))

        sale_orders = self.env['sale.order'].search(domain)
        report_lines = []

        for order in sale_orders:
            # Filter lines with negative quantity (returns)
            lines = order.order_line.filtered(lambda l: l.product_id and not l.display_type and l.product_uom_qty < 0)

            # Product Filter
            if data.get('product_id'):
                lines = lines.filtered(lambda l: l.product_id.id == data['product_id'][0])

            for line in lines:
                report_lines.append({
                    'sret_no': order.name,
                    'date': order.date_order,
                    'customer': order.partner_id.name or '',
                    'item_name': line.product_id.name,
                    'pcs': abs(line.pcs) if getattr(line, 'pcs', False) else 0.0,
                    'ctn': abs(line.ctn) if getattr(line, 'ctn', False) else 0.0,
                    'qty_kgs': abs(line.product_uom_qty) if line.product_uom_qty else 0.0,
                    'rate': line.price_unit or 0.0,
                    'amount': abs(line.net_amount) if getattr(line, 'net_amount', False) else 0.0,
                    'sale_to': '', 'qty2': '', 'rate2': '', 'amount2': '',
                })

        # Your original Grouping Logic
        report_lines.sort(key=itemgetter('customer'))
        grouped_data = []

        for key, group in groupby(report_lines, key=itemgetter('customer')):
            g_lines = list(group)
            grouped_data.append({
                'customer': key,
                'items': g_lines,
                'total_qty_kgs': sum(x['qty_kgs'] for x in g_lines),
                'total_amount': sum(x['amount'] for x in g_lines),
            })

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_qty': sum(x['total_qty_kgs'] for x in grouped_data),
            'grand_total_amt': sum(x['total_amount'] for x in grouped_data),
        }
