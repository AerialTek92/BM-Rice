# from odoo import models, fields, api
#
# # --- WIZARD 1: Good Receipt Detail ---
# class StockPickingDetailWizard(models.TransientModel):
#     _name = 'stock.picking.detail.wizard' # ID badal di
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_stock_picking_detail').report_action(self, data=data)
#
# class ReportStockPickingDetail(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_stock_picking_template'
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         docs = self.env['stock.picking'].search([('date_done', '>=', data['date_from']), ('date_done', '<=', data['date_to']), ('state', '=', 'done')], order='date_done asc')
#         return {'docs': docs, 'date_from': data['date_from'], 'date_to': data['date_to']}


# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPickingDetailWizard(models.TransientModel):
    _name = 'stock.picking.detail.wizard'
    _description = 'Good Receipt Detail Wizard'

    # Date Filters
    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_done', 'Effective Date (Done)'),
        ('scheduled_date', 'Scheduled Date'),
        ('grn_date', 'GRN Date')
    ], string='Date Type', default='date_done', required=True)

    # Advanced Filters
    partner_id = fields.Many2one('res.partner', string='Supplier/Partner')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')

    picking_type_code = fields.Selection([
        ('incoming', 'Receipts (Vendor)'),
        ('outgoing', 'Deliveries (Customer)'),
        ('internal', 'Internal Transfers')
    ], string='Operation Type', default='incoming')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('party_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        # self.read()[0] dictionary return karta hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_stock_picking_detail').report_action(self, data=data)


class ReportStockPickingDetail(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_stock_picking_template'
    _description = 'Stock Picking Detail Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'date_done')

        # Base Domain
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
            ('state', '=', 'done')
        ]

        # Dynamic Filters from Wizard
        if data.get('picking_type_code'):
            domain.append(('picking_type_code', '=', data['picking_type_code']))

        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))

        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))

        if data.get('product_id'):
            domain.append(('move_ids.product_id', '=', data['product_id'][0]))

        # Sort order
        order_by = 'date_done asc'
        if data.get('report_type') == 'party_wise':
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
