# -*- coding: utf-8 -*-

from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_worked_day_lines(self, domain=None, check_out_of_version=True):
        """
        Generate worked days lines for the payslip.

        OT worked-days lines are only generated when the employee's
        work location has OT Applicable enabled.
        """
        self.ensure_one()

        # --------------------------------------------------------------
        # Get normal Odoo worked-days lines
        # --------------------------------------------------------------
        res = super()._get_worked_day_lines(
            domain=domain,
            check_out_of_version=check_out_of_version,
        )

        # --------------------------------------------------------------
        # Check employee work location
        # --------------------------------------------------------------
        employee = self.employee_id
        work_location = employee.work_location_id

        # --------------------------------------------------------------
        # OT is not applicable
        #
        # Remove all extra-hours lines from the result.
        # These lines will therefore never be created on the payslip.
        # --------------------------------------------------------------
        if not work_location or not work_location.ot_applicable:

            work_entry_type_ids = [
                line.get('work_entry_type_id')
                for line in res
                if line.get('work_entry_type_id')
            ]

            extra_hours_type_ids = set(
                self.env['hr.work.entry.type'].browse(
                    work_entry_type_ids
                ).filtered(
                    lambda work_entry_type: work_entry_type.is_extra_hours
                ).ids
            )

            res = [
                line
                for line in res
                if line.get('work_entry_type_id') not in extra_hours_type_ids
            ]

        return res