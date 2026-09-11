# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from typing import Any, Dict

# scheduled_date is a Datetime: an inclusive '<= date' comparison would silently drop
# everything after midnight of the last day. We use an exclusive upper bound instead.
DATE_RANGE_END_OFFSET_DAYS: int = 1


class DeliveryOrderWizard(models.TransientModel):
    _name = 'delivery.order.wizard'
    _description = 'Delivery Order Detail Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self) -> Dict[str, Any]:
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref(
            'arm_sales_management.action_report_delivery_order_detail_pdf'
        ).report_action(self, data=data)


class DeliveryOrderDetailReport(models.AbstractModel):
    # Shortened name to stay under the PostgreSQL 63-character table name limit
    _name = 'report.arm_sales_management.report_do_range'
    _description = 'Delivery Order Range Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        range_end_exclusive = data['date_to'] + timedelta(days=DATE_RANGE_END_OFFSET_DAYS)

        docs = self.env['stock.picking'].search([
            ('picking_type_code', '=', 'outgoing'),
            ('scheduled_date', '>=', data['date_from']),
            ('scheduled_date', '<', range_end_exclusive),
            ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned', 'done'])
        ], order='scheduled_date asc')

        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }