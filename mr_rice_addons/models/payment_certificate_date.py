from odoo import models, fields, api


# --- WIZARD: Payment Certificate Date Wise ---
class PaymentCertificateDateWizard(models.TransientModel):
    _name = 'payment.certificate.date.wizard'
    _description = 'Payment Certificate Date Wise Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_payment_certificate_date_wise').report_action(self, data=data)


# --- REPORT LOGIC ---
class PaymentCertificateDateReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_payment_cert_date_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Payments search based on date
        docs = self.env['payment.certificate'].search([
            ('date', '>=', data['date_from']),
            ('date', '<=', data['date_to']),
        ], order='date asc')

        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }