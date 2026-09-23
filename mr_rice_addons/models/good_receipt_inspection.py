# from odoo import models, fields, api
#
#
# # --- WIZARD: Inspection Detail ---
# class GrnInspectionDetailWizard(models.TransientModel):
#     _name = 'grn.inspection.detail.wizard'
#     _description = 'GRN Inspection Detail Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_grn_inspection_detail').report_action(self, data=data)
#
#
# # --- REPORT LOGIC ---
# class GrnInspectionDetailReport(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_grn_inspection_detail_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         # Grn Inspection records search between dates
#         docs = self.env['grn.inspection'].search([
#             ('inspection_date', '>=', data['date_from']),
#             ('inspection_date', '<=', data['date_to']),
#             ('state', 'in', ['initial_pass', 'final_pass'])  # Sirf pass huye records
#         ], order='inspection_date asc')
#
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api


class GrnInspectionDetailWizard(models.TransientModel):
    _name = 'grn.inspection.detail.wizard'
    _description = 'GRN Inspection Detail Wizard'

    # Date Filters
    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('inspection_date', 'Inspection Date'),
        ('create_date', 'System Entry Date')
    ], string='Date Type', default='inspection_date', required=True)

    # Advanced Filters
    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')

    inspection_state = fields.Selection([
        ('all', 'All Passed'),
        ('initial_pass', 'Initial Pass'),
        ('final_pass', 'Final Pass')
    ], string='Status Filter', default='all')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('party_wise', 'Party Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_grn_inspection_detail').report_action(self, data=data)


class GrnInspectionDetailReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_grn_inspection_detail_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'inspection_date')

        # Base Domain
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
        ]

        # Status Filter
        if data.get('inspection_state') == 'all':
            domain.append(('state', 'in', ['initial_pass', 'final_pass']))
        else:
            domain.append(('state', '=', data['inspection_state']))

        # Wizard Filters
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))
        if data.get('product_id'):
            # Check if product exists in any of the inspection lines
            domain.append(('inspection_line_ids.product_id', '=', data['product_id'][0]))

        # Sort order
        order_by = 'inspection_date asc'
        if data.get('report_type') == 'party_wise':
            order_by = 'partner_id asc, inspection_date asc'

        docs = self.env['grn.inspection'].search(domain, order=order_by)

        return {
            'docs': docs,
            'data': data,  # Passing whole wizard data to template
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'target_product_id': data.get('product_id') and data['product_id'][0] or False,
        }
