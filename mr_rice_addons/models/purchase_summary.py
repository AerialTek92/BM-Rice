from odoo import models, fields, api


# --- WIZARD: Summary select karne ke liye ---
class PurchaseOrderSummaryWizard(models.TransientModel):
    _name = 'purchase.order.summary.wizard'
    _description = 'Purchase Order Summary Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        # ID Match honi chahiye XML Action se
        return self.env.ref('mr_rice_addons.action_report_purchase_order_summary').report_action(self, data=data)


# --- REPORT LOGIC: Data fetch karne ke liye ---
class PurchaseOrderSummaryReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_purchase_summary_template'

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