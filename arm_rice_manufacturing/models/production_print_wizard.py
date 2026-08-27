# -*- coding: utf-8 -*-

from odoo import models, fields
from typing import Dict, Any


class ProductionPrintWizard(models.TransientModel):
    _name = 'production.print.wizard'
    _description = 'Print Production Logs Wizard'

    production_record_id = fields.Many2one('production.record', string='Production Record', required=True)

    def action_print_log_sheet(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref('arm_rice_manufacturing.action_report_production_log_sheet').report_action(self.production_record_id)

    def action_print_qa_report(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref('arm_rice_manufacturing.action_report_production_quality').report_action(self.production_record_id)