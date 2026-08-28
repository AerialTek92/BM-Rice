from odoo import models, fields, api

# --- WIZARD 1: Good Receipt Detail ---
class StockPickingDetailWizard(models.TransientModel):
    _name = 'stock.picking.detail.wizard' # ID badal di
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)

    def action_print_report(self):
        data = {'date_from': self.date_from, 'date_to': self.date_to}
        return self.env.ref('mr_rice_addons.action_report_stock_picking_detail').report_action(self, data=data)

class ReportStockPickingDetail(models.AbstractModel):
    _name = 'report.mr_rice_addons.report_stock_picking_template'
    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.picking'].search([('date_done', '>=', data['date_from']), ('date_done', '<=', data['date_to']), ('state', '=', 'done')], order='date_done asc')
        return {'docs': docs, 'date_from': data['date_from'], 'date_to': data['date_to']}