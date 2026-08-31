# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class InvoiceDateWizard(models.TransientModel):
    _name = 'invoice.date.wizard'
    _description = 'Invoice Date Wise Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        self.ensure_one()
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_invoice_date_wise').report_action(self, data=data)


class ReportInvoiceDateWise(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_invoice_date_wise_template'
    _description = 'Invoice Date Wise Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Ab data sale.order se fetch hoga (account.move nahi)
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
        ]

        sale_orders = self.env['sale.order'].search(domain, order='partner_id, date_order')
        report_lines = []

        for order in sale_orders:
            # Delivery Order se Bag aur D/O No fetch kar rahe hain
            picking = order.picking_ids[:1] if order.picking_ids else False
            bags = picking.bags if picking and picking.bags else 0.0
            do_no = picking.name if picking else ''

            # Agar invoice bana hua hai toh uska number, warna Sale Order ka number
            bill_no = order.invoice_ids[:1].name if order.invoice_ids else order.name

            for line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
                report_lines.append({
                    'bill_no': bill_no,
                    'date': order.date_order,
                    'customer': order.partner_id.name or '',
                    'item_name': line.product_id.name,
                    'bags': bags,
                    'ctn': line.ctn or 0.0,
                    'qty': line.product_uom_qty or 0.0,
                    'rate': line.price_unit or 0.0,
                    'disct_per': line.discount or 0.0,
                    'disct_sp': line.discount_special or 0.0,
                    'net_amount': line.net_amount or 0.0,
                    'do_no': do_no,
                })

        # Customer ke hisaab se grouping
        report_lines.sort(key=itemgetter('customer'))
        grouped_data = []

        for key, group in groupby(report_lines, key=itemgetter('customer')):
            g_lines = list(group)
            grouped_data.append({
                'customer': key,
                'items': g_lines,
                'total_bags': sum(x['bags'] for x in g_lines),
                'total_ctn': sum(x['ctn'] for x in g_lines),
                'total_qty': sum(x['qty'] for x in g_lines),
                'total_net': sum(x['net_amount'] for x in g_lines),
            })

        # Grand Totals
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
