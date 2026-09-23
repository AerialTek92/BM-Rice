# from odoo import models, fields, api
#
#
# # --- WIZARD: Payment Certificate Summary ---
# class PaymentCertificateWizard(models.TransientModel):
#     _name = 'payment.certificate.wizard'
#     _description = 'Payment Certificate Summary Wizard'
#
#     date_from = fields.Date(string='Date From', required=True)
#     date_to = fields.Date(string='Date To', required=True)
#
#     def action_print_report(self):
#         data = {'date_from': self.date_from, 'date_to': self.date_to}
#         # ID Match honi chahiye XML Action se
#         return self.env.ref('mr_rice_addons.action_report_payment_certificate_summary').report_action(self, data=data)
#
#
# # --- REPORT LOGIC ---
# class PaymentCertificateReport(models.AbstractModel):
#     _name = 'report.mr_rice_addons.report_payment_certificate_template'
#
#     @api.model
#     def _get_report_values(self, docids, data=None):
#         # Yahan hum payments dhoondenge jo specific dates mein hain
#         docs = self.env['account.payment'].search([
#             ('date', '>=', data['date_from']),
#             ('date', '<=', data['date_to']),
#             ('state', 'in', ['posted', 'reconciled'])
#         ], order='date asc')
#
#         return {
#             'docs': docs,
#             'date_from': data['date_from'],
#             'date_to': data['date_to'],
#         }


# report/payment_certificate_report.py
from odoo import models, fields, api


class PaymentCertificateWizard(models.TransientModel):
    _name = 'payment.certificate.wizard'
    _description = 'Payment Certificate Summary Wizard'

    date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)

    date_filter_type = fields.Selection([
        ('date', 'PC Date'),
        ('grn_date', 'GRN Date')
    ], string='Date Type', default='date', required=True)

    partner_id = fields.Many2one('res.partner', string='Supplier')
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'vendor')]")

    report_type = fields.Selection([
        ('date_wise', 'Date Wise'),
        ('supplier_wise', 'Supplier Wise')
    ], string='Report Type', default='date_wise')

    def action_print_report(self):
        # read()[0] dictionary return karta hai jo report template mein 'data' ban kar jati hai
        data = self.read()[0]
        return self.env.ref('mr_rice_addons.action_report_payment_certificate_summary').report_action(self, data=data)


class PaymentCertificateReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_payment_certificate_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_field = 'date' if data.get('date_filter_type') == 'pc_date' else 'grn_date'

        domain = [
            (date_field, '>=', data.get('date_from')),
            (date_field, '<=', data.get('date_to')),
            ('state', '!=', 'draft')
        ]

        if data.get('partner_id'):
            domain.append(('partner_id', '=', data['partner_id'][0]))
        if data.get('broker_id'):
            domain.append(('broker_id', '=', data['broker_id'][0]))

        docs = self.env['payment.certificate'].search(domain, order='broker_id asc, date asc')

        broker_data = {}
        for doc in docs:
            broker = doc.broker_id.name or "No Broker"
            if broker not in broker_data:
                broker_data[broker] = {
                    'net_weight': 0.0, 'bags': 0, 'amount': 0.0,
                    'moisture': 0.0, 'broken': 0.0, 'fill_bag': 0.0, 'damage': 0.0, 'other_ded': 0.0,
                    'wht': 0.0, 'brokerage': 0.0, 'transport': 0.0, 'other_add': 0.0,
                    'net_amount': 0.0
                }

            b = broker_data[broker]
            b['net_weight'] += doc.net_weight
            b['bags'] += doc.bags
            b['amount'] += doc.gross_amount

            # Deductions
            b['moisture'] += doc.moisture_deduction
            b['broken'] += doc.broken_deduction
            b['fill_bag'] += doc.filling_bags_deduction
            b['damage'] += doc.less_damage
            b['other_ded'] += (doc.less_other_deductions + doc.less_weighing_charges)

            # Additions (WHT yahan plus mein add ho raha hai)
            b['wht'] += doc.less_wh_tax_brokerage
            b['brokerage'] += doc.add_brokerage
            b['transport'] += doc.add_transportation
            b['other_add'] += (doc.add_bardana + doc.add_labour + doc.add_commission + doc.add_other)

            # MANUALLY CALCULATING NET AMOUNT FOR REPORT:
            # Formula: Gross Amount - Deductions + Additions (including WHT)
            deductions = b['moisture'] + b['broken'] + b['fill_bag'] + b['damage'] + b['other_ded']
            additions = b['wht'] + b['brokerage'] + b['transport'] + b['other_add']

            b['net_amount'] = b['amount'] - deductions + additions

        return {
            'doc_ids': docids,
            'doc_model': 'payment.certificate',
            'broker_summary': broker_data,
            'data': data,
            'print_date': fields.Datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        }
