from odoo import models, fields, api


# --- WIZARD: Payment Certificate Summary ---
class PaymentCertificateWizard(models.TransientModel):
    _name = 'payment.certificate.wizard'
    _description = 'Payment Certificate Summary Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        # ID Match honi chahiye XML Action se
        return self.env.ref('mr_rice_addons.action_report_payment_certificate_summary').report_action(self, data=data)


# --- REPORT LOGIC ---
class PaymentCertificateReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_payment_certificate_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Yahan hum payments dhoondenge jo specific dates mein hain
        docs = self.env['account.payment'].search([
            ('date', '>=', data['date_from']),
            ('date', '<=', data['date_to']),
            ('state', 'in', ['posted', 'reconciled'])
        ], order='date asc')

        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }