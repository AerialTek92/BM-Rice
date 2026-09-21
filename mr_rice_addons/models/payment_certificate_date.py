# from odoo import models, fields, api
#
#
# # --- WIZARD: Payment Certificate Date Wise ---
# class PaymentCertificateDateWizard(models.TransientModel):
#     _name = 'payment.certificate.date.wizard'
#     _description = 'Payment Certificate Date Wise Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_payment_certificate_date_wise').report_action(self, data=data)
#
#
# # --- REPORT LOGIC ---
# class PaymentCertificateDateReport(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_payment_cert_date_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         # Payments search based on date
#         docs = self.env['payment.certificate'].search([
#             ('date', '>=', data['date_from']),
#             ('date', '<=', data['date_to']),
#         ], order='date asc')
#
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PaymentCertificateDateWizard(models.TransientModel):
    _name = 'payment.certificate.date.wizard'
    _description = 'Payment Certificate Date Wise Wizard'

    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('pc_date', 'PC Date'),
        ('grn_date', 'GRN Date')
    ], string='Date Type', default='pc_date', required=True)

    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'broker')]")
    product_id = fields.Many2one('product.product', string='Product')
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Orders')

    truck_no = fields.Char(string='Truck No')
    rate = fields.Float(string='Rate')
    show_company = fields.Boolean(string='Show Company', default=True)

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_payment_certificate_date_wise').report_action(self, data=data)


class PaymentCertificateDateReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_payment_cert_date_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = 'date' if data.get('date_filter_type') == 'pc_date' else 'grn_date'

        domain = [
            (date_field, '>=', data.get('date_from')),
            (date_field, '<=', data.get('date_to'))
        ]

        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))
        if data.get('product_id'):
            domain.append(('product_id', '=', data['product_id'][0]))
        if data.get('purchase_ids'):
            domain.append(('purchase_id', 'in', data.get('purchase_ids')))
        if data.get('truck_no'):
            domain.append(('vehicle_number', 'ilike', data['truck_no']))
        if data.get('rate') > 0:
            domain.append(('rate', '=', data['rate']))

        docs = self.env['payment.certificate'].search(domain, order=f'{date_field} asc')
        return {
            'doc_ids': docids,
            'doc_model': 'payment.certificate',
            'docs': docs,
            'data': data,
        }
