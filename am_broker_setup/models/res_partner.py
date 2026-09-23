# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from typing import Any, Dict, List

PARTNER_TYPE_SEQUENCE_MAP = {
    'customer': 'res.partner.cust',
    'vendor': 'res.partner.vend',
    'transporter': 'res.partner.trn',
    'export_customer': 'res.partner.expc',
}

EMPLOYEE_PARTNER_TYPE = 'employee'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Partner Type Selection - 'vendor' is the merged VENDOR / BROKER type
    # (brokers are vendors with brokerage rates; one pool, one picker).
    # 'employee' keeps the company's own people out of every typed picker.
    partner_assign_type = fields.Selection([
        ('customer', 'Customer'),
        ('vendor', 'Vendor / Broker'),
        ('export_customer', 'Export Customer'),
        ('employee', 'Employee')
    ], string="Partner Type", default='customer')

    # Broker Specific Fields (shown on the merged Vendor / Broker type)
    broker_category = fields.Selection([
        ('local', 'Local'),
        ('international', 'International'),
        ('commercial', 'Commercial')
    ], string="Broker Category")

    stax_reg_no = fields.Char(string='STax Reg No')
    ntn_no = fields.Char(string='NTN No')
    brokerage_rate = fields.Float(string='Brokerage Rate (Per Bag)', digits=(16, 2))
    wh_tax_rate = fields.Float(string='W.H.Tax Rate')

    broker_account = fields.Many2one(
        'account.account',
        string='Broker Account',
        company_dependent=True,
    )

    withholding_tax_account = fields.Many2one(
        'account.account',
        string='Withholding Tax Account',
        company_dependent=True,
    )

    withholding_tax_rate = fields.Float(
        string="Withholding Tax Rate (%)",
        digits=(16, 4),
        default=0.0,
        help="Withholding tax percentage applicable to this vendor.",
    )
    income_tax_rate = fields.Float(
        string="Income Tax Rate (%)",
        digits=(16, 4),
        default=0.0,
        help="Income tax percentage applicable to this vendor.",
    )

    income_tax_account = fields.Many2one(
        "account.account",
        string="Income Tax Account",
        help="Account used for income tax payable.",
    )


    # Vendor Specific Fields (For the Notebook)
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


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ResUsers':
        """Internal users' partners are typed 'employee' - they never
        appear in any typed picker. Portal users keep their type."""
        users = super().create(vals_list)
        internal_users = users.filtered(lambda user: not user.share)
        if internal_users:
            internal_users.partner_id.write({'partner_assign_type': EMPLOYEE_PARTNER_TYPE})
        return users


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'HrEmployee':
        """Employees created from the HR module: their work-contact partner
        is typed 'employee' so they stay out of every typed picker."""
        employees = super().create(vals_list)
        work_contacts = employees.mapped('work_contact_id').filtered(bool)
        if work_contacts:
            work_contacts.write({'partner_assign_type': EMPLOYEE_PARTNER_TYPE})
        return employees