# -*- coding: utf-8 -*-

from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_payslip_done(self):
        """Protocol 3.2 (OCP): Extend native payslip confirmation to link deductions."""
        res = super().action_payslip_done()
        HrProductIssueLine = self.env['hr.product.issue.line']

        for payslip in self:
            lines = HrProductIssueLine.search([
                ('employee_id', '=', payslip.employee_id.id),
                ('state', '=', 'confirmed'),
                ('issue_id.date', '>=', payslip.date_from),
                ('issue_id.date', '<=', payslip.date_to)
            ])
            if lines:
                lines.write({
                    'state': 'deducted',
                    'payslip_id': payslip.id
                })
        return res

    def action_payslip_cancel(self):
        """Protocol 3.2 (OCP): Extend native cancellation to reset deductions."""
        res = super().action_payslip_cancel()
        HrProductIssueLine = self.env['hr.product.issue.line']

        for payslip in self:
            lines = HrProductIssueLine.search([('payslip_id', '=', payslip.id)])
            if lines:
                lines.write({
                    'state': 'confirmed',
                    'payslip_id': False
                })
        return res

    class HrEmployee(models.Model):
        _inherit = 'hr.employee'
        version_revision = fields.Integer(string='Version Revision Fix', default=0)

    class HrEmployeePublic(models.Model):
        _inherit = 'hr.employee.public'
        version_revision = fields.Integer(string='Version Revision Fix', readonly=True)
