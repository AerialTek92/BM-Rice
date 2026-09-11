from odoo import models, fields


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