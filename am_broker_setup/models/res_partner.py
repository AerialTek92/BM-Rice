# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from typing import Dict, Any, List

PARTNER_TYPE_SEQUENCE_MAP = {
    'customer': 'res.partner.cust',
    'vendor': 'res.partner.vend',
    'broker': 'res.partner.brk',
    'transporter': 'res.partner.trn',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # 1. Partner Type Selection
    partner_assign_type = fields.Selection([
        ('customer', 'Customer'),
        ('vendor', 'Vendor'),
        ('broker', 'Broker')
    ], string="Partner Type", default='customer')

    # 2. Broker Specific Fields
    broker_category = fields.Selection([
        ('local', 'Local'),
        ('international', 'International'),
        ('commercial', 'Commercial')
    ], string="Broker Category")

    stax_reg_no = fields.Char(string='STax Reg No')
    ntn_no = fields.Char(string='NTN No')
    brokerage_rate = fields.Float(string='Brokerage Rate (Per Bag)', digits=(16, 2))
    wh_tax_rate = fields.Float(string='W.H.Tax Rate')

    # 3. Vendor Specific Fields (For the Notebook)
    ho_address = fields.Text(string="Address")
    ho_contact_person = fields.Char(string="Contact Person")
    ho_contact_no = fields.Char(string="Contact No")
    ho_fax_no = fields.Char(string="Fax No")

    factory_address = fields.Text(string="Address")
    factory_contact_person = fields.Char(string="Contact Person")
    factory_contact_no = fields.Char(string="Contact No")
    factory_fax_no = fields.Char(string="Fax No")
    partner_code = fields.Char(string="Partner Code", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ResPartner':
        for vals in vals_list:
            ptype = vals.get('partner_assign_type')
            sequence_code = PARTNER_TYPE_SEQUENCE_MAP.get(ptype)

            if sequence_code:
                vals['partner_code'] = self.env['ir.sequence'].next_by_code(sequence_code)

        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list: List[str]) -> Dict[str, Any]:
        res = super().default_get(fields_list)

        search_mode = self._context.get('res_partner_search_mode')

        if search_mode == 'customer':
            res['partner_assign_type'] = 'customer'
        elif search_mode == 'supplier':
            res['partner_assign_type'] = 'vendor'

        return res

    @api.constrains('wh_tax_rate')
    def _check_wh_tax_rate(self) -> None:
        for rec in self:
            if rec.wh_tax_rate < 0.0 or rec.wh_tax_rate > 100.0:
                raise ValidationError(_("The W.H.Tax Rate must be a percentage between 0 and 100."))