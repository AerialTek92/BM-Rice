# from odoo import models, fields, api
#
# class PurchaseOrderWizard(models.TransientModel):
#     _name = 'purchase.order.wizard'
#     _description = 'Purchase Order Report Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         # 'mr_rice_addons' ko apne folder name se zaroor check kar lena
#         return self.env.ref('mr_rice_addons.action_report_purchase_order_detail').report_action(self, data=data)
#
# class PurchaseOrderDetailReport(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_purchase_order_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         docs = self.env['purchase.order'].search([
#             ('date_order', '>=', data['date_from']),
#             ('date_order', '<=', data['date_to']),
#             ('state', 'in', ['purchase', 'done'])
#         ], order='date_order asc')
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PurchaseOrderWizard(models.TransientModel):
    _name = 'purchase.order.wizard'
    _description = 'Purchase Order Report Wizard'

    # Date Range with professional defaults
    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_order', 'Order Date'),
        ('date_approve', 'Approval Date')
    ], string='Date Type', default='date_order', required=True)

    # Advanced Filters (Based on your reference file style)
    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')
    purchase_indent_ids = fields.Many2many('purchase.indent', string='Purchase Indents')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        # self.read()[0] se saara wizard data dictionary ban kar report logic ko chala jata hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_purchase_order_detail').report_action(self, data=data)


class PurchaseOrderDetailReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_purchase_order_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'date_order')

        # Base Domain (Confirmed POs only)
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
            ('state', 'in', ['purchase', 'done'])
        ]

        # Conditional Filters Application
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))

        if data.get('broker_id'):
            # Note: broker_id field purchase.order par honi chahiye
            domain.append(('broker_id', '=', data['broker_id'][0]))

        if data.get('purchase_indent_ids'):
            domain.append(('purchase_indent_id', 'in', data['purchase_indent_ids']))

        if data.get('product_id'):
            domain.append(('order_line.product_id', '=', data['product_id'][0]))

        # Dynamic Sorting
        order_by = 'date_order asc'
        if data.get('report_type') == 'supplier_wise':
            order_by = 'partner_id asc, date_order asc'

        docs = self.env['purchase.order'].search(domain, order=order_by)

        return {
            'doc_ids': docids,
            'doc_model': 'purchase.order',
            'docs': docs,
            'data': data,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }
