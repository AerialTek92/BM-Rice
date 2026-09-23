from odoo import fields, models


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    balance_deducted = fields.Boolean(
        string='Balance Deducted',
        default=False,
        copy=False,
    )

    def action_approve(self):
        result = super().action_approve()

        for leave in self:
            if leave.state != 'validate':
                continue

            if not leave.employee_id:
                continue

            if not leave.holiday_status_id:
                continue

            if leave.balance_deducted:
                continue

            balance = self.env['hr.employee.leaves.days'].search([
                ('employee_id', '=', leave.employee_id.id),
                ('leave_type_id', '=', leave.holiday_status_id.id),
            ], limit=1)

            if not balance:
                continue

            balance.used_days += leave.number_of_days
            leave.balance_deducted = True

        return result