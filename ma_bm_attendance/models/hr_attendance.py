from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    enroll_number = fields.Char(
        string="Enroll Number",
        index=True,
    )

    check_in_code = fields.Char(
        string="Check In Code",
        default="0001",
    )

    check_out_code = fields.Char(
        string="Check Out Code",
        default="0002",
    )

    device_number = fields.Char(
        string="Device Number",
        default="001",
    )

    is_biometric = fields.Boolean(
        string="Biometric Import",
        default=False,
    )

    @api.onchange('employee_id')
    def _onchange_employee_id_enroll_number(self):
        """Fetch enroll number when employee is selected."""
        if self.employee_id:
            self.enroll_number = self.employee_id.custom_employee_id
        else:
            self.enroll_number = False

    @api.model_create_multi
    def create(self, vals_list):
        """Automatically set enroll number when attendance is created."""
        for vals in vals_list:
            if vals.get('employee_id'):
                employee = self.env['hr.employee'].browse(
                    vals['employee_id']
                )
                vals['enroll_number'] = employee.custom_employee_id

        return super().create(vals_list)

    def write(self, vals):
        """Update enroll number if employee is changed."""
        if 'employee_id' in vals:
            if vals['employee_id']:
                employee = self.env['hr.employee'].browse(
                    vals['employee_id']
                )
                vals['enroll_number'] = employee.custom_employee_id
            else:
                vals['enroll_number'] = False

        return super().write(vals)