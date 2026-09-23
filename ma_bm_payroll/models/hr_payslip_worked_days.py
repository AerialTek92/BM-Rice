# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    @api.depends(
        'is_paid',
        'number_of_hours',
        'payslip_id',
        'version_id.wage',
        'version_id.hourly_wage',
        'payslip_id.sum_worked_hours',
        'work_entry_type_id.amount_rate',
        'work_entry_type_id.is_extra_hours',
    )
    def _compute_amount(self):

        OvertimeSetupLine = self.env['overtime.setup.line']

        for worked_days in self:

            payslip = worked_days.payslip_id
            version = worked_days.version_id

            if payslip.edited or payslip.state != 'draft':
                continue

            if not version or worked_days.code == 'OUT':
                worked_days.amount = 0
                continue

            amount_rate = worked_days.work_entry_type_id.amount_rate

            # ==========================================================
            # ANNUAL LEAVE
            # Always amount = 0
            # ==========================================================
            if worked_days.work_entry_type_id.name == 'Annual Leave':
                worked_days.amount = 0
                continue

            # ==========================================================
            # OVERTIME CALCULATION
            # ==========================================================
            if worked_days.work_entry_type_id.is_extra_hours:

                ot_hours = worked_days.number_of_hours

                if not ot_hours:
                    worked_days.amount = 0
                    continue

                salary = version.contract_wage

                # ------------------------------------------------------
                # Find applicable overtime setup line
                # ------------------------------------------------------
                setup_line = OvertimeSetupLine.search([
                    ('start_date', '<=', payslip.date_from),
                    ('end_date', '>=', payslip.date_to),
                    ('salary_start', '<=', salary),
                    ('salary_end', '>=', salary),
                ], order='start_date desc, id desc', limit=1)

                if not setup_line:
                    worked_days.amount = 0
                    continue

                # ======================================================
                # TYPE = AMOUNT
                # ======================================================
                if setup_line.calculation_type == 'amount':

                    rate = 0.0

                    setup_values = [
                        (
                            setup_line.setup_1_hours,
                            setup_line.setup_1_rate,
                        ),
                        (
                            setup_line.setup_2_hours,
                            setup_line.setup_2_rate,
                        ),
                        (
                            setup_line.setup_3_hours,
                            setup_line.setup_3_rate,
                        ),
                        (
                            setup_line.setup_4_hours,
                            setup_line.setup_4_rate,
                        ),
                        (
                            setup_line.setup_5_hours,
                            setup_line.setup_5_rate,
                        ),
                        (
                            setup_line.setup_6_hours,
                            setup_line.setup_6_rate,
                        ),
                    ]

                    # --------------------------------------------------
                    # Select highest applicable OT slab
                    # --------------------------------------------------
                    for setup_hours, setup_rate in setup_values:

                        if setup_hours and ot_hours >= setup_hours:
                            rate = setup_rate

                    # --------------------------------------------------
                    # OT Amount
                    # --------------------------------------------------
                    worked_days.amount = (
                        ot_hours
                        * rate
                        * amount_rate
                        if worked_days.is_paid
                        else 0
                    )

                # ======================================================
                # TYPE = CALCULATION
                # ======================================================
                else:

                    # --------------------------------------------------
                    # Calculate working days in payroll period
                    # excluding Sundays
                    # --------------------------------------------------
                    working_days = 0

                    current_date = payslip.date_from

                    while current_date <= payslip.date_to:

                        if current_date.weekday() != 6:
                            working_days += 1

                        current_date += timedelta(days=1)

                    if not working_days:
                        worked_days.amount = 0
                        continue

                    # --------------------------------------------------
                    # Base hourly rate
                    #
                    # Salary / Working Days / 8
                    # --------------------------------------------------
                    hourly_rate = (
                            salary
                            / working_days
                            / 8
                    )

                    # --------------------------------------------------
                    # Percentage
                    # --------------------------------------------------
                    percentage = setup_line.percentage / 100

                    # --------------------------------------------------
                    # OT hourly rate
                    # --------------------------------------------------
                    ot_hourly_rate = hourly_rate * percentage

                    # --------------------------------------------------
                    # Final OT amount
                    # --------------------------------------------------
                    worked_days.amount = (
                        ot_hourly_rate
                        * ot_hours
                        * amount_rate
                        if worked_days.is_paid
                        else 0
                    )

            # ==========================================================
            # NORMAL WORKED DAYS
            # Attendance amount = Employee Wage
            # ==========================================================
            elif payslip.wage_type == "hourly":

                hourly_rate = version.hourly_wage

                worked_days.amount = (
                    hourly_rate
                    * worked_days.number_of_hours
                    * amount_rate
                    if worked_days.is_paid
                    else 0
                )

            else:

                # ------------------------------------------------------
                # Attendance should use Employee Wage directly
                # We are NOT calculating salary based on attendance
                # hours.
                # ------------------------------------------------------
                employee_wage = payslip.employee_id.wage

                worked_days.amount = (
                    employee_wage
                    * amount_rate
                    if worked_days.is_paid
                    else 0
                )