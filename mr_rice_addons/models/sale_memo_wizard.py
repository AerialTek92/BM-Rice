# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleMemoRiceWizard(models.TransientModel):
    _name = 'sale.memo.rice.wizard'
    _description = 'Sale Memo Rice Date Wise Wizard'

    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', domain=[('partner_assign_type', '=', 'customer')])
    broker_id = fields.Many2one('res.partner', string='Broker', domain=[('partner_assign_type', '=', 'broker')])
    product_id = fields.Many2one('product.product', string='Product')
    category_id = fields.Many2one('product.category', string='Item Group')

    def action_print_report(self):
        self.ensure_one()
        # Data dictionary mein saare wizard values pass kar rahe hain
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'broker_id': self.broker_id.id if self.broker_id else False,
            'product_id': self.product_id.id if self.product_id else False,
            'category_id': self.category_id.id if self.category_id else False,
        }
        return self.env.ref('mr_rice_addons.action_report_sale_memo_detail').report_action(self, data=data)


class ReportSaleMemoDetail(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_sale_memo_detail_template'
    _description = 'Sale Memo Detail Report Logic'

    @api.model
    def _get_report_values(self, docids, data=None):
        # 1. Base Domain (Hamesha date range aur confirmed sales check karega)
        domain = [
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
            ('state', 'in', ['sale', 'done'])
        ]

        # 2. Dynamic Filtering (Agar wizard mein select kiya hai to add karo, warna ignore)
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id']))

        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id']))

        # Sale Orders search karo filters ke sath
        orders = self.env['sale.order'].search(domain, order='date_order asc, name asc')

        report_lines = []

        for order in orders:
            # Order ki lines filter karein (Product aur Category filter lines level par honge)
            lines = order.order_line.filtered(lambda l: not l.display_type)

            if data.get('product_id'):
                lines = lines.filtered(lambda l: l.product_id.id == data['product_id'])

            if data.get('category_id'):
                lines = lines.filtered(lambda l: l.product_id.categ_id.id == data['category_id'])

            # Agar koi line bachi hai (filters ke baad) toh hi add karein
            for index, line in enumerate(lines):
                report_lines.append({
                    'memo': order.name if index == 0 else '',  # Sirf pehli row mein Order No
                    'date': order.date_order.date() if index == 0 else '',
                    'customer': order.partner_id.name if index == 0 else '',
                    'item_name': line.product_id.name,
                    'bag': line.pcs or 0.0,
                    'ctn': line.ctn or 0.0,
                    'qty_kg': line.product_uom_qty or 0.0,
                    'rate': line.price_unit or 0.0,
                    'disct_per': line.discount or 0.0,
                    'disct_sp': line.discount_special or 0.0,
                    'net_amount': line.net_amount or 0.0,
                    'do_qty': line.qty_delivered or 0.0,
                    'balance': line.product_uom_qty - line.qty_delivered,
                })

        return {
            'data': data,
            'docs': report_lines,
        }
