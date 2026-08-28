from odoo import models, fields, api


# --- WIZARD: Rice Allowance Deduction ---
class RiceAllowanceDeductionWizard(models.TransientModel):
    _name = 'rice.allowance.deduction.wizard'
    _description = 'Rice Allowance Deduction Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_rice_allowance_deduction').report_action(self, data=data)


# --- REPORT LOGIC ---
class RiceAllowanceDeductionReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_rice_deduction_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Hum wo stock.picking (GRNs) dhoondenge jahan deductions hui hain
        docs = self.env['stock.picking'].search([
            ('date_done', '>=', data['date_from']),
            ('date_done', '<=', data['date_to']),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done')
        ], order='date_done asc')

        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }