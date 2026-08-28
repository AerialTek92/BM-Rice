from odoo import models, fields, api

class PurchaseOrderWizard(models.TransientModel):
    _name = 'purchase.order.wizard'
    _description = 'Purchase Order Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        # 'mr_rice_addons' ko apne folder name se zaroor check kar lena
        return self.env.ref('mr_rice_addons.action_report_purchase_order_detail').report_action(self, data=data)

class PurchaseOrderDetailReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_purchase_order_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.order'].search([
            ('date_order', '>=', data['date_from']),
            ('date_order', '<=', data['date_to']),
            ('state', 'in', ['purchase', 'done'])
        ], order='date_order asc')
        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }