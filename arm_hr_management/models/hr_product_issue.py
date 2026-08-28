# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List


class HrProductIssue(models.Model):
    _name = 'hr.product.issue'
    _description = 'Employee Product Issuance Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(string='Issue Date', default=fields.Date.today(), required=True, tracking=True)

    line_ids = fields.One2many('hr.product.issue.line', 'issue_id', string='Issued Products')

    total_amount = fields.Monetary(string='Total Batch Amount', compute='_compute_total_amount', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed')
    ], string='Batch Status', default='draft', tracking=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'HrProductIssue':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.product.issue') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.subtotal')
    def _compute_total_amount(self) -> None:
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('subtotal'))

    def action_confirm(self) -> None:
        """Protocol 2.1: Validate and confirm the batch for payroll deduction."""
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Please add at least one product line before confirming."))

            # FIX: Validate that all lines have a product and quantity assigned
            missing_products = rec.line_ids.filtered(lambda l: not l.product_id)
            if missing_products:
                raise UserError(_("Please assign a product to all employees before confirming."))

            rec.state = 'confirmed'
            # Update underlying lines to confirmed
            rec.line_ids.write({'state': 'confirmed'})

    def action_set_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'
            # Only reset lines that haven't been deducted yet
            rec.line_ids.filtered(lambda l: l.state == 'confirmed').write({'state': 'draft'})


class HrProductIssueLine(models.Model):
    _name = 'hr.product.issue.line'
    _description = 'Employee Product Issuance Line'

    issue_id = fields.Many2one('hr.product.issue', string='Issue Ref', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)

    # FIX: Removed required=True so the wizard can create empty rows
    product_id = fields.Many2one('product.product', string='Product')

    quantity = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Monetary(string='Unit Price')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one('res.currency', related='issue_id.currency_id', readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('deducted', 'Deducted in Payroll')
    ], string='Line Status', default='draft', tracking=True)

    payslip_id = fields.Many2one('hr.payslip', string='Payslip', readonly=True, copy=False)

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self) -> None:
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.onchange('product_id')
    def _onchange_product_id_map_rate(self) -> None:
        """Protocol 1.6: Automatically map the product's sales price."""
        if self.product_id:
            self.price_unit = self.product_id.list_price