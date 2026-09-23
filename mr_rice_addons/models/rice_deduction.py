# from odoo import models, fields, api
#
#
# # --- WIZARD: Rice Allowance Deduction ---
# class RiceAllowanceDeductionWizard(models.TransientModel):
#     _name = 'rice.allowance.deduction.wizard'
#     _description = 'Rice Allowance Deduction Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_rice_allowance_deduction').report_action(self, data=data)
#
#
# # --- REPORT LOGIC ---
# class RiceAllowanceDeductionReport(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_rice_deduction_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         # Hum wo stock.picking (GRNs) dhoondenge jahan deductions hui hain
#         docs = self.env['stock.picking'].search([
#             ('date_done', '>=', data['date_from']),
#             ('date_done', '<=', data['date_to']),
#             ('picking_type_code', '=', 'incoming'),
#             ('state', '=', 'done')
#         ], order='date_done asc')
#
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api


# --- WIZARD: Rice Allowance Deduction ---
class RiceAllowanceDeductionWizard(models.TransientModel):
    _name = 'rice.allowance.deduction.wizard'
    _description = 'Rice Allowance Deduction Wizard'

    # Date Range with Default Today
    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_done', 'Effective Date (Validation)'),
        ('scheduled_date', 'Scheduled Date')
    ], string='Date Type', default='date_done', required=True)

    # Advanced Filters
    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Orders',
                                    domain="[('state', 'in', ['purchase', 'done'])]")

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        # self.read()[0] dictionary return karta hai jo logic mein 'data' variable ban jati hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_rice_allowance_deduction').report_action(self, data=data)


# --- REPORT LOGIC ---
class RiceAllowanceDeductionReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_rice_deduction_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'date_done')

        # Base Domain (GRNs only)
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done')
        ]

        # Dynamic Filters Application
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))

        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))

        if data.get('purchase_ids'):
            domain.append(('purchase_id', 'in', data['purchase_ids']))

        if data.get('product_id'):
            domain.append(('move_ids.product_id', '=', data['product_id'][0]))

        # Sort order based on report type
        order_by = 'date_done asc'
        if data.get('report_type') == 'supplier_wise':
            order_by = 'partner_id asc, date_done asc'

        docs = self.env['stock.picking'].search(domain, order=order_by)

        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'data': data,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }
