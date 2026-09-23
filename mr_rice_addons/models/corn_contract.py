from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class OutstandingArrivalWizard(models.TransientModel):
    _name = 'outstanding.arrival.wizard'
    _description = 'Outstanding Arrival Report Wizard'

    as_on_date = fields.Date(string='As On Date', required=True, default=fields.Date.today())

    def action_print_report(self):
        self.ensure_one()
        data = {'as_on_date': self.as_on_date}
        return self.env.ref('mr_rice_addons.action_report_outstanding_arrival').report_action(self, data=data)


class ReportOutstandingArrival(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_outstanding_arrival_template'
    _description = 'Outstanding Arrival Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('state', 'in', ['purchase', 'done']),
            ('total_qty_remaining', '>', 0)
        ]

        orders = self.env['purchase.order'].search(domain, order='broker_id, delivery_date_from')
        report_lines = []

        for order in orders:
            report_lines.append({
                'broker': order.broker_id.name or 'N/A',
                'trucks': order.total_trucks,
                'qty': order.total_qty_remaining,
                'rate': order.unit_price,
                'date_from': order.delivery_date_from,
                'date_to': order.delivery_date_to,
            })

        # Broker ke hisaab se grouping
        report_lines.sort(key=itemgetter('broker'))
        grouped_data = []
        grand_total_trucks = 0
        grand_total_qty = 0.0

        for key, group in groupby(report_lines, key=itemgetter('broker')):
            g_lines = list(group)
            sub_total_trucks = sum(x['trucks'] for x in g_lines)
            sub_total_qty = sum(x['qty'] for x in g_lines)

            grand_total_trucks += sub_total_trucks
            grand_total_qty += sub_total_qty

            grouped_data.append({
                'broker': key,
                'items': g_lines,
                'sub_total_trucks': sub_total_trucks,
                'sub_total_qty': sub_total_qty,
            })

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_trucks': grand_total_trucks,
            'grand_total_qty': grand_total_qty,
        }
