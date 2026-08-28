from odoo import models, fields, api


# --- WIZARD: Corn Future Contract ---
class CornFutureContractWizard(models.TransientModel):
    _name = 'corn.future.contract.wizard'
    _description = 'Corn Future Contract Summary Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_corn_future_contract').report_action(self, data=data)


# --- REPORT LOGIC ---
class CornFutureContractReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_corn_future_contract_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Yahan hum wo Purchase Orders dhoondenge jo "Corn" ke contracts hain
        # Aap product_id ya kisi category ke hisab se mazeed filter bhi laga sakte hain
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