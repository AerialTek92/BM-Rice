# from odoo import models, fields, api
#
#
# # --- WIZARD: PO v/s GRN ---
# class PoVsGrnWizard(models.TransientModel):
#     _name = 'po.vs.grn.wizard'
#     _description = 'PO v/s GRN Report Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_po_vs_grn').report_action(self, data=data)
#
#
# # --- REPORT LOGIC ---
# class PoVsGrnReportLogic(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_po_vs_grn_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         # POs search based on date
#         docs = self.env['purchase.order'].search([
#             ('date_order', '>=', data['date_from']),
#             ('date_order', '<=', data['date_to']),
#             ('state', 'in', ['purchase', 'done'])
#         ], order='date_order asc')
#
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api


# --- WIZARD: PO v/s GRN ---
class PoVsGrnWizard(models.TransientModel):
    _name = 'po.vs.grn.wizard'
    _description = 'PO v/s GRN Report Wizard'

    # Date Filters
    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_order', 'Order Date'),
        ('date_approve', 'Approval Date')
    ], string='Date Type', default='date_order', required=True)

    # Advanced Filters (As per reference style)
    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        # read()[0] dictionary return karta hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_po_vs_grn').report_action(self, data=data)


# --- REPORT LOGIC ---
class PoVsGrnReportLogic(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_po_vs_grn_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'date_order')

        # Base Domain (Confirmed POs only)
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
            ('state', 'in', ['purchase', 'done'])
        ]

        # Dynamic Filters Application from Wizard
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))

        if data.get('broker_id'):
            # Note: broker_id field purchase.order model par honi chahiye
            domain.append(('broker_id', '=', data['broker_id'][0]))

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
