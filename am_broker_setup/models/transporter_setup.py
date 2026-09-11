# -*- coding: utf-8 -*-

from odoo import models, fields, api
from typing import Dict, Any, List

DEFAULT_CODE_NEW = 'New'


class TransporterSetup(models.Model):
    _name = 'transporter.setup'
    _description = 'Transporter'
    _order = 'code'

    name = fields.Char(string="Name", required=True, tracking=True)
    code = fields.Char(
        string="Code", required=True, copy=False,
        readonly=True, default=lambda self: DEFAULT_CODE_NEW
    )

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'TransporterSetup':
        for vals in vals_list:
            if vals.get('code', DEFAULT_CODE_NEW) == DEFAULT_CODE_NEW:
                vals['code'] = self.env['ir.sequence'].next_by_code('res.partner.trn') or '/'
        return super().create(vals_list)