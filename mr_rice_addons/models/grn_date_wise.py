# from odoo import models, fields, api
#
#
# class StockPickingDateWizard(models.TransientModel):
#     _name = 'stock.picking.date.wizard'
#     _description = 'GRN Date Wise Report Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_grn_date_wise').report_action(self, data=data)
#
#
# # --- REPORT LOGIC: Data fetch karne ke liye ---
# class GrnDateWiseReportLogic(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_grn_date_wise_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
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


class StockPickingDateWizard(models.TransientModel):
    _name = 'stock.picking.date.wizard'
    _description = 'GRN Date Wise Report Wizard'

    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today)

    location_id = fields.Many2one('stock.location', string='Location', domain=[('usage', '=', 'internal')])
    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'broker')]")
    product_id = fields.Many2one('product.product', string='Product')

    # Many2many selection for Multiple POs
    purchase_ids = fields.Many2many('purchase.order', string='Purchase Orders')

    truck_no = fields.Char(string='Truck No')
    pending_pay_cert = fields.Boolean(string='Pending Pay Certificate')
    show_company = fields.Boolean(string='Show Company', default=True)

    # Range Filters
    moisture_from = fields.Float(string='Moisture From')
    moisture_to = fields.Float(string='Moisture To')
    broken_from = fields.Float(string='Broken From')
    broken_to = fields.Float(string='Broken To')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_grn_date_wise').report_action(self, data=data)


class GrnDateWiseReportLogic(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_grn_date_wise_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('date_done', '>=', data.get('date_from')),
            ('date_done', '<=', data.get('date_to')),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done')
        ]

        if data.get('location_id'):
            domain.append(('location_dest_id', '=', data['location_id'][0]))
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('purchase_id.broker_id', '=', data['broker_id'][0]))
        if data.get('product_id'):
            domain.append(('product_id', '=', data['product_id'][0]))
        if data.get('purchase_ids'):
            domain.append(('purchase_id', 'in', data.get('purchase_ids')))
        if data.get('truck_no'):
            domain.append(('vehicle_number', 'ilike', data['truck_no']))
        if data.get('pending_pay_cert'):
            domain.append(('has_payment_cert', '=', False))

        # Moisture & Broken Ranges
        if data.get('moisture_to') > 0:
            domain.append(('actual_moisture', '>=', data.get('moisture_from')))
            domain.append(('actual_moisture', '<=', data.get('moisture_to')))
        if data.get('broken_to') > 0:
            domain.append(('actual_broken', '>=', data.get('broken_from')))
            domain.append(('actual_broken', '<=', data.get('broken_to')))

        docs = self.env['stock.picking'].search(domain, order='date_done asc')
        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'date_from': data.get('date_from'),
            'date_to': data.get('date_to'),
            'data': data,
        }
