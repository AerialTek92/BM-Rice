# -*- coding: utf-8 -*-

from odoo import models, fields
from typing import Dict, Any


class HrProductIssueWizard(models.TransientModel):
    _name = 'hr.product.issue.wizard'
    _description = 'Batch Issue Products to Employees'

    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True)
    date = fields.Date(string='Issue Date', default=fields.Date.today(), required=True)

    def action_create_issues(self) -> Dict[str, Any]:
        """Protocol 2.1: Create ONE single draft issuance batch with a line for each employee."""
        self.ensure_one()

        # Prepare a line for each selected employee
        line_vals = []
        for emp in self.employee_ids:
            line_vals.append((0, 0, {
                'employee_id': emp.id,
                # User will manually fill product and quantity later in the form
            }))

        self.env['hr.product.issue'].create({
            'date': self.date,
            'line_ids': line_vals,
        })

        return {
            'type': 'ir.actions.act_window_close'
        }