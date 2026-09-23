from odoo import models, fields,api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    device_user_id = fields.Char(
        string='Device Enrollment No.',
        help='Auto-set when employee is created from biometric upload.'
    )
    
    # NEW: Custom Employee ID for manual entry and easy searching
    custom_employee_id = fields.Char(
        string='Employee ID',
        copy=False,
        tracking=True,
        help='Enter a unique Employee ID to easily search and open this employee later.'
    )

    leave_days_ids = fields.One2many(
        'hr.employee.leaves.days',
        'employee_id',
        string='Leave Days',
    )

    @api.onchange('resource_calendar_id')
    def _onchange_resource_calendar_id_leave_days(self):
        for employee in self:
            commands = [(5, 0, 0)]

            if employee.resource_calendar_id:
                for calendar_line in employee.resource_calendar_id.leave_days_ids:
                    if not calendar_line.leave_type_id:
                        continue

                    commands.append(
                        (0, 0, {
                            'leave_type_id': calendar_line.leave_type_id.id,
                            'days': calendar_line.days,
                        })
                    )

            employee.leave_days_ids = commands

from odoo import api, fields, models


class HrEmployeeLeavesDays(models.Model):
    _name = 'hr.employee.leaves.days'
    _description = 'Employee Leave Days'
    _rec_name = 'leave_type_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
    )

    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Time Off Type',
        required=True,
        ondelete='cascade',
    )

    days = fields.Float(
        string='Days',
        default=0.0,
    )

    used_days = fields.Float(
        string='Used Days',
        default=0.0,
    )

    remaining = fields.Float(
        string='Remaining',
        compute='_compute_remaining',
        store=True,
    )

    @api.depends('days', 'used_days')
    def _compute_remaining(self):
        for line in self:
            line.remaining = line.days - line.used_days