# -*- coding: utf-8 -*-

from odoo import models, fields


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    # Shift Information
    code = fields.Integer(
        string='Shift Code',
        copy=False,
    )

    depart = fields.Char(
        string='Department',
        default='',
    )

    short_name = fields.Char(
        string='Short Name',
    )

    # Time Settings
    mark_attendance_after = fields.Float(
        string='Mark Attendance After',
        widget='float_time',
    )

    mark_absent_after = fields.Float(
        string='Mark Absent After',
        widget='float_time',
    )

    mark_late_after = fields.Float(
        string='Mark Late After',
        widget='float_time',
    )

    # Half Day Settings
    half_day_start = fields.Float(
        string='Half Day Start',
        widget='float_time',
    )

    half_day_end = fields.Float(
        string='Half Day End',
        widget='float_time',
    )

    # Overtime / Early Out
    over_time_start = fields.Float(
        string='Over Time Start At',
        widget='float_time',

    )

    mark_early_out = fields.Float(
        string='Mark Early Out At',
        widget='float_time',
    )

    # Break Settings
    break_start = fields.Float(
        string='Break Start (Hours)',
        default=0.0,
    )

    break_end = fields.Float(
        string='Break End (Hours)',
        default=0.0,
    )

    leave_days_ids = fields.One2many(
        'resource.calendar.leave.days',
        'calendar_id',
        string='Leaves Days',
    )

    def action_fetch_time_off_types(self):
        LeaveType = self.env['hr.leave.type']
        LeaveDays = self.env['resource.calendar.leave.days']

        leave_types = LeaveType.search([])

        for calendar in self:
            existing_lines = {
                line.leave_type_id.id: line
                for line in calendar.leave_days_ids
                if line.leave_type_id
            }

            new_lines = []

            for leave_type in leave_types:

                # Existing line → update days
                if leave_type.id in existing_lines:
                    existing_lines[leave_type.id].days = leave_type.days

                # New line → create with days
                else:
                    new_lines.append({
                        'calendar_id': calendar.id,
                        'leave_type_id': leave_type.id,
                        'days': leave_type.days,
                    })

            if new_lines:
                LeaveDays.create(new_lines)

        return True


class ResourceCalendarLeaveDays(models.Model):
    _name = 'resource.calendar.leave.days'
    _description = 'Leave Days by Working Schedule'

    calendar_id = fields.Many2one(
        'resource.calendar',
        string='Working Schedule',
        required=True,
        ondelete='cascade',
    )

    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Time Off Type',
        required=True,
    )

    days = fields.Integer(
        string='Days',
        required=True,
        default=0,
    )