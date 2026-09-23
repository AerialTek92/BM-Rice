# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OutstandingCornArrivalWizard(models.TransientModel):
    _name = 'outstanding.corn.arrival.wizard'
    _description = 'Outstanding Corn Arrival Report Wizard'

    as_on_date = fields.Date(string='As On Date', required=True, default=fields.Date.today())

    def action_print_report(self):
        self.ensure_one()
        data = {'as_on_date': self.as_on_date}
        return self.env.ref('mr_rice_addons.action_report_outstanding_corn_arrival').report_action(self, data=data)


class ReportOutstandingArrival(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_outstanding_corn_arrival_template'
    _description = 'Outstanding Arrival Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('state', 'in', ['purchase', 'done']),
            ('total_qty_remaining', '>', 0)
        ]

        orders = self.env['purchase.order'].search(domain, order='broker_id, date_order')
        report_lines = []

        for order in orders:
            soda_type = ', '.join([l.transaction_type for l in order.order_line if l.transaction_type])
            if not soda_type:
                soda_type = 'N/A'

            report_lines.append({
                'po_no': order.name or '',
                'po_date': order.date_order.date() if order.date_order else False,
                'broker': order.broker_id.name or 'N/A',
                'trucks': order.total_trucks,
                'qty': order.total_qty_remaining,
                'rate': order.unit_price,
                'date_from': order.delivery_date_from,
                'date_to': order.delivery_date_to,
                'soda_type': soda_type,
            })

        # Grand Totals
        grand_total_trucks = sum(x['trucks'] for x in report_lines)
        grand_total_qty = sum(x['qty'] for x in report_lines)

        return {
            'data': data,
            'lines': report_lines,
            'grand_total_trucks': grand_total_trucks,
            'grand_total_qty': grand_total_qty,
        }
