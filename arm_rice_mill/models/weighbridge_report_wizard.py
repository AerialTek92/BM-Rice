# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WeighbridgeDateWizard(models.TransientModel):
    _name = 'weighbridge.date.wizard'
    _description = 'Weighbridge Date Wise Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        self.ensure_one()
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('arm_rice_mill.action_report_weighbridge_date_wise').report_action(self, data=data)


class ReportWeighbridgeDateWise(models.AbstractModel):
    _name = 'report.arm_rice_mill.report_weighbridge_date_wise_template'
    _description = 'Weighbridge Date Wise Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('date', '>=', data['date_from']),
            ('date', '<=', data['date_to']),
            ('state', '=', 'confirmed')
        ]

        tickets = self.env['weighbridge.ticket'].search(domain, order='date asc')

        # Grand Totals ke liye
        total_gross = 0.0
        total_tare = 0.0
        total_net = 0.0
        total_bags = 0

        report_lines = []
        for ticket in tickets:
            # Agar ek ticket par multiple materials hain toh unko comma se separate karenge
            materials = ', '.join(ticket.line_ids.mapped('product_id').mapped('name'))
            bags = sum(ticket.line_ids.mapped('bags'))

            report_lines.append({
                'date': ticket.date,
                'wb_no': ticket.name,
                'vehicle': ticket.vehicle_number or '',
                'material': materials or '',
                'customer': ticket.consignee_id.name or '',
                'supplier': ticket.partner_id.name or '',
                'gross_wt': ticket.gross_weight,
                'tare_wt': ticket.tare_weight,
                'net_wt': ticket.net_weight,
                'bags': bags,
            })

            total_gross += ticket.gross_weight
            total_tare += ticket.tare_weight
            total_net += ticket.net_weight
            total_bags += bags

        return {
            'data': data,
            'lines': report_lines,
            'total_gross': total_gross,
            'total_tare': total_tare,
            'total_net': total_net,
            'total_bags': total_bags,
        }
