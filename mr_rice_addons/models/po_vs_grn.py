from odoo import models, fields, api


# --- WIZARD: PO v/s GRN ---
class PoVsGrnWizard(models.TransientModel):
    _name = 'po.vs.grn.wizard'
    _description = 'PO v/s GRN Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_po_vs_grn').report_action(self, data=data)


# --- REPORT LOGIC ---
class PoVsGrnReportLogic(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_po_vs_grn_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        # POs search based on date
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