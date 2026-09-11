from odoo import models, fields,api


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    code = fields.Char(
        string='Code'
    )

    days = fields.Integer(
        string='Days'
    )

    detail = fields.Text(
        string='Detail'
    )

    rate = fields.Float(
        string='Rate'
    )

    short = fields.Char(
        string='Short'
    )

    use_daily_working_hours = fields.Boolean(
        string='Use Daily Working Hours',
        help=(
            'When enabled, work entries generated for this leave type '
            'will follow the employee resource calendar working hours.'
        ),
    )

    @api.onchange('work_entry_type_id')
    def _onchange_work_entry_type_id(self):
        for record in self:
            if record.work_entry_type_id:
                record.code = record.work_entry_type_id.external_code
                record.short = record.work_entry_type_id.display_code
                record.rate = record.work_entry_type_id.amount_rate * 100
            else:
                record.code = False
                record.short = False
                record.rate = False