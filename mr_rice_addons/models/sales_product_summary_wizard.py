# # -*- coding: utf-8 -*-
# from odoo import models, fields, api
# from itertools import groupby
# from operator import itemgetter
#
#
# class SalesProductSummaryWizard(models.TransientModel):
#     _name = 'sales.product.summary.wizard'
#     _description = 'Sales Product Summary Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         self.ensure_one()
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         return self.env.ref('mr_rice_addons.action_report_sales_product_summary').report_action(self, data=data)
#
#
# class ReportSalesProductSummary(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_sales_product_summary_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         domain = [
#             ('state', 'in', ['sale', 'done']),
#             ('date_order', '>=', data['date_from']),
#             ('date_order', '<=', data['date_to']),
#         ]
#         sale_orders = self.env['sale.order'].search(domain)
#
#         lines_data = []
#         for order in sale_orders:
#             for line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
#                 lines_data.append({
#                     'template_name': line.product_id.product_tmpl_id.name,
#                     'product_name': line.product_id.name,
#                     'pcs': line.pcs or 0.0,
#                     'ctn': line.ctn or 0.0,
#                     'qty': line.product_uom_qty or 0.0,
#                     'disct': line.discount_special or 0.0,
#                     'net': line.net_amount or 0.0,
#                 })
#
#         lines_data.sort(key=itemgetter('template_name', 'product_name'))
#         grouped_data = []
#         for template, t_group in groupby(lines_data, key=itemgetter('template_name')):
#             v_list = list(t_group)
#             v_summary = []
#             v_list.sort(key=itemgetter('product_name'))
#             for prod, p_group in groupby(v_list, key=itemgetter('product_name')):
#                 p_lines = list(p_group)
#                 v_summary.append({
#                     'name': prod,
#                     'pcs': sum(x['pcs'] for x in p_lines),
#                     'ctn': sum(x['ctn'] for x in p_lines),
#                     'qty': sum(x['qty'] for x in p_lines),
#                     'disct': sum(x['disct'] for x in p_lines),
#                     'net': sum(x['net'] for x in p_lines),
#                 })
#
#             grouped_data.append({
#                 'template': template,
#                 'variants': v_summary,
#                 't_pcs': sum(x['pcs'] for x in v_summary),
#                 't_ctn': sum(x['ctn'] for x in v_summary),
#                 't_qty': sum(x['qty'] for x in v_summary),
#                 't_net': sum(x['net'] for x in v_summary),
#             })
#
#         return {
#             'data': data,
#             'grouped_data': grouped_data,
#             'grand_total_bags': sum(x['t_pcs'] for x in grouped_data),
#             'grand_total_ctn': sum(x['t_ctn'] for x in grouped_data),
#             'grand_total_weight': sum(x['t_qty'] for x in grouped_data),
#             'grand_total_disct': sum(sum(v['disct'] for v in x['variants']) for x in grouped_data),
#             'grand_total_net': sum(x['t_net'] for x in grouped_data),
#         }


# -*- coding: utf-8 -*-
from odoo import models, fields, api
from itertools import groupby
from operator import itemgetter


class SalesProductSummaryWizard(models.TransientModel):
    _name = 'sales.product.summary.wizard'
    _description = 'Sales Product Summary Wizard'

    # Date Filters
    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date_order', 'Order Date'),
        ('commitment_date', 'Delivery Date')
    ], string='Date Type', default='date_order', required=True)

    # Advanced Filters (Based on your reference requirement)
    partner_id = fields.Many2one('res.partner', string='Customer')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")
    product_id = fields.Many2one('product.product', string='Specific Product')
    sale_ids = fields.Many2many('sale.order', string='Sales Memos', domain="[('state', 'in', ['sale', 'done'])]")
    contract_type = fields.Selection([('local', 'Local'), ('export', 'Export')], string='Contract Type')

    def action_print_report(self):
        self.ensure_one()
        # self.read()[0] se saara filter data Abstract model ko chala jayega
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_sales_product_summary').report_action(self, data=data)


class ReportSalesProductSummary(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_sales_product_summary_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_f = data.get('date_filter_type') or 'date_order'

        # Dynamic Domain Building
        domain = [
            ('state', 'in', ['sale', 'done']),
            (date_f, '>=', data['date_from']),
            (date_f, '<=', data['date_to']),
        ]

        # Applying Wizard Filters
        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))
        if data.get('contract_type'):
            domain.append(('contract_type', '=', data['contract_type']))
        if data.get('sale_ids'):
            domain.append(('id', 'in', data['sale_ids']))

        sale_orders = self.env['sale.order'].search(domain)

        lines_data = []
        for order in sale_orders:
            # Product level filtering
            order_lines = order.order_line.filtered(lambda l: l.product_id and not l.display_type)
            if data.get('product_id'):
                order_lines = order_lines.filtered(lambda l: l.product_id.id == data['product_id'][0])

            for line in order_lines:
                lines_data.append({
                    'template_name': line.product_id.product_tmpl_id.name,
                    'product_name': line.product_id.name,
                    'pcs': getattr(line, 'pcs', 0.0),  # Safer access
                    'ctn': getattr(line, 'ctn', 0.0),
                    'qty': line.product_uom_qty or 0.0,
                    'disct': getattr(line, 'discount_special', 0.0),
                    'net': getattr(line, 'net_amount', 0.0),
                })

        # --- Your Original Grouping Logic (No changes here) ---
        lines_data.sort(key=itemgetter('template_name', 'product_name'))
        grouped_data = []
        for template, t_group in groupby(lines_data, key=itemgetter('template_name')):
            v_list = list(t_group)
            v_summary = []
            v_list.sort(key=itemgetter('product_name'))
            for prod, p_group in groupby(v_list, key=itemgetter('product_name')):
                p_lines = list(p_group)
                v_summary.append({
                    'name': prod,
                    'pcs': sum(x['pcs'] for x in p_lines),
                    'ctn': sum(x['ctn'] for x in p_lines),
                    'qty': sum(x['qty'] for x in p_lines),
                    'disct': sum(x['disct'] for x in p_lines),
                    'net': sum(x['net'] for x in p_lines),
                })

            grouped_data.append({
                'template': template,
                'variants': v_summary,
                't_pcs': sum(x['pcs'] for x in v_summary),
                't_ctn': sum(x['ctn'] for x in v_summary),
                't_qty': sum(x['qty'] for x in v_summary),
                't_net': sum(x['net'] for x in v_summary),
            })

        return {
            'data': data,
            'grouped_data': grouped_data,
            'grand_total_bags': sum(x['t_pcs'] for x in grouped_data),
            'grand_total_ctn': sum(x['t_ctn'] for x in grouped_data),
            'grand_total_weight': sum(x['t_qty'] for x in grouped_data),
            'grand_total_disct': sum(sum(v['disct'] for v in x['variants']) for x in grouped_data),
            'grand_total_net': sum(x['t_net'] for x in grouped_data),
        }
