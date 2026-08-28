from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
from typing import Any


class AdvanceStatus:
    """Namespace for Salary Advance Status constants."""
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    REFUSED = 'refused'
    PAID = 'paid'

    SELECTION = [
        (DRAFT, 'Draft'),
        (SUBMITTED, 'Submitted'),
        (APPROVED, 'Approved'),
        (REFUSED, 'Refused'),
        (PAID, 'Paid'),
    ]


class HrSalaryAdvance(models.Model):
    """
    Odoo 19 Fixed: Model for Employee Salary Advances with Accounting.
    """
    _name = 'hr.salary.advance'
    _description = 'Salary Advance Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New'
    )

    # Employee Details
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        string='Department',
        store=True,
        readonly=True
    )
    work_location_ids = fields.Many2many(
        'res.partner',
        string='Location Of Work',
        domain="[('partner_share', '=', True)]"
    )
    job_id = fields.Many2one(
        'hr.job',
        related='employee_id.job_id',
        string='Job Position',
        store=True,
        readonly=True
    )

    # Advance Specifics
    request_date = fields.Date(string='Request Date', default=fields.Date.today, required=True)
    repayment_date = fields.Date(string='Repayment Date', required=True, default=fields.Date.today)

    # Financials
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )
    advance_amount = fields.Monetary(
        string='Advance Amount',
        required=True,
        currency_field='currency_id'
    )

    # Accounting Integration
    journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="The journal used to record the payment (e.g., Bank)."
    )

    emp_account_id = fields.Many2one(
        'account.account',
        string='Advance Account',
        domain="[('active', '=', True)]",
        help="The asset account for Employee Advances (Debit)."
    )

    move_id = fields.Many2one(
        'account.move',
        string='Accounting Entry',
        readonly=True
    )
    is_settled = fields.Boolean(
        string="Fully Settled",
        default=False
    )
    state = fields.Selection(
        selection=AdvanceStatus.SELECTION,
        string='Status',
        copy=False,
        default=AdvanceStatus.DRAFT,
        tracking=True
    )

    # FIXED: Odoo 19 Batch Create Fix
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.salary.advance') or 'New'
        return super(HrSalaryAdvance, self).create(vals_list)

    def action_open_account_move(self) -> dict:
        self.ensure_one()
        return {
            'name': _('Journal Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }

    def action_generate_journal_entry(self):
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Please define a Payment Journal."))
        if not self.emp_account_id:
            raise UserError(_("Please define an Advance Asset Account."))
        if self.advance_amount <= 0:
            raise UserError(_("Advance amount must be greater than zero."))

        partner = self.employee_id.work_contact_id or self.employee_id.address_home_id
        if not partner:
            raise UserError(_("Employee must have a Work or Private Address for Accounting entries."))

        credit_account = self.journal_id.default_account_id
        if not credit_account:
            raise UserError(_("The selected Journal does not have a default Credit Account."))

        move_vals = {
            'ref': f"{self.name} - {self.employee_id.name}",
            'date': self.request_date,
            'journal_id': self.journal_id.id,
            'move_type': 'entry',
            'line_ids': [
                Command.create({
                    'name': f"Advance: {self.name}",
                    'account_id': self.emp_account_id.id,
                    'debit': self.advance_amount,
                    'credit': 0.0,
                    'partner_id': partner.id,
                }),
                Command.create({
                    'name': f"Payment: {self.name}",
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.advance_amount,
                }),
            ]
        }

        move = self.env['account.move'].create(move_vals)
        self.write({
            'move_id': move.id,
            'state': AdvanceStatus.PAID
        })
        return self.action_open_account_move()

    # Workflow Actions
    def action_submit(self):
        self.write({'state': AdvanceStatus.SUBMITTED})

    def action_approve(self):
        self.write({'state': AdvanceStatus.APPROVED})

    def action_refuse(self):
        self.write({'state': AdvanceStatus.REFUSED})

    def action_reset_draft(self):
        self.write({'state': AdvanceStatus.DRAFT})
