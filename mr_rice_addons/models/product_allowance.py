# from odoo import models, fields, api
#
# class StockPickingProductWizard(models.TransientModel):
#     _name = 'stock.picking.product.wizard' # ID badal di
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_stock_picking_product').report_action(self, data=data)
#
# class ReportStockPickingProduct(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_stock_picking_product'
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         docs = self.env['stock.picking'].search([('date_done', '>=', data['date_from']), ('date_done', '<=', data['date_to']), ('state', '=', 'done')], order='date_done asc')
#         return {'docs': docs, 'date_from': data['date_from'], 'date_to': data['date_to']}


# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPickingProductWizard(models.TransientModel):
    _name = 'stock.picking.product.wizard'
    _description = 'Product Allowance Actual Vs Billing Wizard'

    # Date Filters
    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_done', 'Effective Date (Done)'),
        ('scheduled_date', 'Scheduled Date')
    ], string='Date Type', default='date_done', required=True)

    # Advanced Filters
    partner_id = fields.Many2one('res.partner', string='Partner (Supplier/Customer)')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Product')

    picking_type_code = fields.Selection([
        ('incoming', 'Receipts (Vendor)'),
        ('outgoing', 'Deliveries (Customer)')
    ], string='Operation Type', default='incoming')

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('product_wise', 'Product Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        self.ensure_one()
        # self.read()[0] dictionary return karta hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_stock_picking_product').report_action(self, data=data)


class ReportStockPickingProduct(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_stock_picking_product'
    _description = 'Product Allowance Actual Vs Billing Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = data.get('date_filter_type', 'date_done')

        # Base Domain
        domain = [
            (date_field, '>=', data['date_from']),
            (date_field, '<=', data['date_to']),
            ('state', '=', 'done')
        ]

        # Applying Wizard Filters
        if data.get('picking_type_code'):
            domain.append(('picking_type_code', '=', data['picking_type_code']))

        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))

        if data.get('broker_id'):
            # Note: broker_id should exist on stock.picking
            domain.append(('broker_id', '=', data['broker_id'][0]))

        if data.get('product_id'):
            domain.append(('move_ids.product_id', '=', data['product_id'][0]))

        # Sort order
        order_by = 'date_done asc'
        if data.get('report_type') == 'product_wise':
            order_by = 'product_id asc, date_done asc'

        docs = self.env['stock.picking'].search(domain, order=order_by)

        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,
            'data': data,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }
