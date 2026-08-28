from odoo import models, fields, api


# --- WIZARD: Inspection Detail ---
class GrnInspectionDetailWizard(models.TransientModel):
    _name = 'grn.inspection.detail.wizard'
    _description = 'GRN Inspection Detail Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_grn_inspection_detail').report_action(self, data=data)


# --- REPORT LOGIC ---
class GrnInspectionDetailReport(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_grn_inspection_detail_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # Grn Inspection records search between dates
        docs = self.env['grn.inspection'].search([
            ('inspection_date', '>=', data['date_from']),
            ('inspection_date', '<=', data['date_to']),
            ('state', 'in', ['initial_pass', 'final_pass'])  # Sirf pass huye records
        ], order='inspection_date asc')

        return {
            'docs': docs,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
        }