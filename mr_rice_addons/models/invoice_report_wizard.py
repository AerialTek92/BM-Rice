# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class InvoiceDateWizard(models.TransientModel):
    _name = 'invoice.date.wizard'
    _description = 'Invoice Date Wise Report Wizard'

    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', domain=[('partner_assign_type', '=', 'customer')])
    product_id = fields.Many2one('product.product', string='Product')
    category_id = fields.Many2one('product.category', string='Item Group')

    def action_print_report(self):
        self.ensure_one()
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'product_id': self.product_id.id if self.product_id else False,
            'category_id': self.category_id.id if self.category_id else False,
        }
        return self.env.ref('mr_rice_addons.action_report_invoice_date_wise').report_action(self, data=data)


class ReportInvoiceDateWise(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_invoice_date_wise_template'
    _description = 'Invoice Date Wise Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # 1. Domain setup
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
        ]

        # Partner Filter
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id']))

        sale_orders = self.env['sale.order'].search(domain, order='partner_id asc, date_order asc')

        all_lines = []
        for order in sale_orders:
            # Delivery Info
            picking = order.picking_ids[:1] if order.picking_ids else False
            do_no = picking.name if picking else ''

            # Bill No logic
            bill_no = order.invoice_ids[:1].name if order.invoice_ids else order.name

            # Line filtering (Product & Category)
            lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
            if data.get('product_id'):
                lines = lines.filtered(lambda l: l.product_id.id == data['product_id'])
            if data.get('category_id'):
                lines = lines.filtered(lambda l: l.product_id.categ_id.id == data['category_id'])

            for line in lines:
                all_lines.append({
                    'bill_no': bill_no,
                    'date': order.date_order.date(),
                    'customer': order.partner_id.name or 'Unknown',
                    'item_name': line.product_id.name,
                    'bags': line.pcs or 0.0,
                    'ctn': line.ctn or 0.0,
                    'qty': line.product_uom_qty or 0.0,
                    'rate': line.price_unit or 0.0,
                    'disct_per': line.discount or 0.0,
                    'disct_sp': line.discount_special or 0.0,
                    'net_amount': line.net_amount or 0.0,
                    'do_no': do_no,
                })

        # 2. Grouping Logic (Matching your XML)
        grouped_data = []
        all_lines.sort(key=itemgetter('customer'))

        for key, group in groupby(all_lines, key=itemgetter('customer')):
            g_lines = list(group)
            grouped_data.append({
                'customer': key,
                'items': g_lines,
                'total_bags': sum(x['bags'] for x in g_lines),
                'total_ctn': sum(x['ctn'] for x in g_lines),
                'total_qty': sum(x['qty'] for x in g_lines),
                'total_net': sum(x['net_amount'] for x in g_lines),
            })

        # 3. Grand Totals
        grand_total_bags = sum(x['total_bags'] for x in grouped_data)
        grand_total_ctn = sum(x['total_ctn'] for x in grouped_data)
        grand_total_qty = sum(x['total_qty'] for x in grouped_data)
        grand_total_net = sum(x['total_net'] for x in grouped_data)

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_bags': grand_total_bags,
            'grand_total_ctn': grand_total_ctn,
            'grand_total_qty': grand_total_qty,
            'grand_total_net': grand_total_net,
        }
