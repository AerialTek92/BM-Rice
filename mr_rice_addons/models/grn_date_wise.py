from odoo import models, fields, api


class StockPickingDateWizard(models.TransientModel):
    _name = 'stock.picking.date.wizard'
    _description = 'GRN Date Wise Report Wizard'

    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_grn_date_wise').report_action(self, data=data)


# --- REPORT LOGIC: Data fetch karne ke liye ---
class GrnDateWiseReportLogic(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_grn_date_wise_template'

    @api.model
    def _get_report_values(self, docids, data=None):
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