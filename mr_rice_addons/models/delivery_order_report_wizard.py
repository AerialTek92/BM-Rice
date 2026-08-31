# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class DeliveryOrderDateWizard(models.TransientModel):
    _name = 'delivery.order.date.wizard'
    _description = 'Delivery Order Date Wise Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        self.ensure_one()
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_do_date_wise').report_action(self, data=data)


class ReportDeliveryOrderDateWise(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_do_date_wise_template'
    _description = 'Delivery Order Date Wise Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('picking_type_code', '=', 'outgoing'),
            ('state', '=', 'done'),
            ('delivery_order_date', '>=', data['date_from']),
            ('delivery_order_date', '<=', data['date_to']),
        ]

        pickings = self.env['stock.picking'].search(domain, order='partner_id, delivery_order_date')
        report_lines = []

        for picking in pickings:
            for move in picking.move_ids:
                if not move.product_id:
                    continue

                # User ki Python file ke mutabiq Qty logic
                do_qty = move.commercial_quantity if move.commercial_quantity > 0 else move.quantity
                rate = move.sale_line_id.price_unit if move.sale_line_id else 0.0
                amount = rate * do_qty

                report_lines.append({
                    'do_no': picking.name,
                    'do_date': picking.delivery_order_date,
                    'customer': picking.partner_id.name or '',
                    'memo_no': picking.sale_id.name if picking.sale_id else '',
                    'product_name': move.product_id.name,
                    'rate': rate,
                    'do_qty': do_qty,
                    'gatepass_qty': move.quantity,
                    'balance_qty': move.balance_qty,
                    'amount': amount,
                })

        # Customer ke hisaab se grouping aur sub-totals
        report_lines.sort(key=itemgetter('customer'))
        grouped_data = []

        for key, group in groupby(report_lines, key=itemgetter('customer')):
            g_lines = list(group)
            grouped_data.append({
                'customer': key,
                'items': g_lines,
                'total_do_qty': sum(x['do_qty'] for x in g_lines),
                'total_gp_qty': sum(x['gatepass_qty'] for x in g_lines),
                'total_bal_qty': sum(x['balance_qty'] for x in g_lines),
                'total_amount': sum(x['amount'] for x in g_lines),
            })

        # Grand Totals
        grand_total_do = sum(x['total_do_qty'] for x in grouped_data)
        grand_total_gp = sum(x['total_gp_qty'] for x in grouped_data)
        grand_total_bal = sum(x['total_bal_qty'] for x in grouped_data)
        grand_total_amt = sum(x['total_amount'] for x in grouped_data)

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_do': grand_total_do,
            'grand_total_gp': grand_total_gp,
            'grand_total_bal': grand_total_bal,
            'grand_total_amt': grand_total_amt,
        }
