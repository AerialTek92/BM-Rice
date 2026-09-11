# -*- coding: utf-8 -*-

from odoo import models, fields


class OvertimeSetup(models.Model):
    _name = 'overtime.setup'
    _description = 'Over Time Setup'
    _order = 'id desc'

    name = fields.Char(
        string='Description',
        required=True,
        copy=False,
        default='Overtime Setup'
    )

    line_ids = fields.One2many(
        'overtime.setup.line',
        'setup_id',
        string='Overtime Setup Lines',
        copy=True,
    )


class OvertimeSetupLine(models.Model):
    _name = 'overtime.setup.line'
    _description = 'Over Time Setup Line'
    _order = 'start_date desc'

    setup_id = fields.Many2one(
        'overtime.setup',
        string='Overtime Setup',
        required=True,
        ondelete='cascade',
    )

    # Period Dates
    start_date = fields.Date(
        string='Start Date',
        required=True
    )

    end_date = fields.Date(
        string='End Date',
        required=True
    )

    # Salary Period
    salary_start = fields.Integer(
        string='Salary Start',
        required=True,
    )

    salary_end = fields.Integer(
        string='Salary End',
        required=True,
    )

    # Calculation / Amount
    calculation_type = fields.Selection(
        [
            ('calculation', 'Calculation'),
            ('amount', 'Amount'),
        ],
        string='Type',
        default='calculation',
    )

    percentage = fields.Float(
        string='%'
    )

    # Setup 1
    setup_1_hours = fields.Float(string='Setup 1 Hours')
    setup_1_rate = fields.Float(string='Setup 1 Rate')

    # Setup 2
    setup_2_hours = fields.Float(string='Setup 2 Hours')
    setup_2_rate = fields.Float(string='Setup 2 Rate')

    # Setup 3
    setup_3_hours = fields.Float(string='Setup 3 Hours')
    setup_3_rate = fields.Float(string='Setup 3 Rate')

    # Setup 4
    setup_4_hours = fields.Float(string='Setup 4 Hours')
    setup_4_rate = fields.Float(string='Setup 4 Rate')

    # Setup 5
    setup_5_hours = fields.Float(string='Setup 5 Hours')
    setup_5_rate = fields.Float(string='Setup 5 Rate')

    # Setup 6
    setup_6_hours = fields.Float(string='Setup 6 Hours')
    setup_6_rate = fields.Float(string='Setup 6 Rate')