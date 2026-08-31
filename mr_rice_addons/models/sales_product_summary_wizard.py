# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SalesProductSummaryWizard(models.TransientModel):
    _name = 'sales.product.summary.wizard'
    _description = 'Sales Product Summary Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        self.ensure_one()
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_sales_product_summary').report_action(self, data=data)


class ReportSalesProductSummary(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_sales_product_summary_template'
    _description = 'Sales Product Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
        ]

        sale_orders = self.env['sale.order'].search(domain)
        product_dict = {}

        for order in sale_orders:
            for line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
                # Aapne XML mein product_template_id likha hai, toh yahan product ka naam is key mein daal rahe hain
                product_name = line.product_id.name

                if product_name not in product_dict:
                    product_dict[product_name] = {
                        'product_template_id': product_name,
                        'bags': '',  # Jaisa aapne kaha, yeh khali rahega
                        'ctn': 0.0,
                        'product_uom_qty': 0.0,
                        'discount_special': 0.0,
                        'net_amount': 0.0,
                    }

                # Aapke exact field names
                product_dict[product_name]['ctn'] += line.ctn or 0.0
                product_dict[product_name]['product_uom_qty'] += line.product_uom_qty or 0.0
                product_dict[product_name]['discount_special'] += line.discount_special or 0.0
                product_dict[product_name]['net_amount'] += line.net_amount or 0.0

        # List mein convert kar ke sort kar rahe hain
        grouped_data = list(product_dict.values())
        grouped_data.sort(key=lambda x: x['product_template_id'])

        # Grand Totals (Aapke XML ke mutabiq names)
        grand_total_bags = ''
        grand_total_ctn = sum(x['ctn'] for x in grouped_data)
        grand_total_weight = sum(x['product_uom_qty'] for x in grouped_data)  # XML mein grand_total_weight hai
        grand_total_disct = sum(x['discount_special'] for x in grouped_data)
        grand_total_net = sum(x['net_amount'] for x in grouped_data)

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_bags': grand_total_bags,
            'grand_total_ctn': grand_total_ctn,
            'grand_total_weight': grand_total_weight,
            'grand_total_disct': grand_total_disct,
            'grand_total_net': grand_total_net,
        }
