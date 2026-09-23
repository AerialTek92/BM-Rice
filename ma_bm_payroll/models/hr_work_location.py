# -*- coding: utf-8 -*-

from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    ot_applicable = fields.Boolean(
        string='OT Applicable',
        default=False,
        help='Enable this if overtime is applicable for employees at this work location.'
    )