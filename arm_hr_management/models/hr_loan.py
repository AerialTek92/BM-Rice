from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
from typing import Any, List


class LoanStatus:
    """Namespace for Loan Request Status constants."""
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


class HrLoanLine(models.Model):
    _name = 'hr.loan.line'
    _description = 'Loan Installment'
    _order = 'payment_date asc'

    loan_id = fields.Many2one('hr.loan.request', string='Loan Reference', ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', related='loan_id.employee_id', store=True)
    payment_date = fields.Date(string='Payment Date', required=True)
    amount = fields.Float(string='Installment Amount', required=True)
    is_paid = fields.Boolean(string='Is Paid', default=False)
    # Payslip dependency agar ho to (optional)
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', readonly=True)


class HrLoanRequest(models.Model):
    _name = 'hr.loan.request'
    _description = 'Loan Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(string='Loan Reference', required=True, copy=False, readonly=True, default='New')
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', store=True, readonly=True)
    work_location_ids = fields.Many2many('res.partner', string='Location Of Work',
                                         domain="[('partner_share', '=', True)]")
    job_id = fields.Many2one('hr.job', related='employee_id.job_id', store=True, readonly=True)

    request_date = fields.Date(string='Request Date', default=fields.Date.today, required=True)
    payment_start_date = fields.Date(string='Payment Start Date', required=True, default=fields.Date.today)

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id,
                                  readonly=True)
    loan_amount = fields.Monetary(string='Loan Amount', required=True, currency_field='currency_id')
    installment_count = fields.Integer(string='No Of Installments', default=1)
    installment_ids = fields.One2many('hr.loan.line', 'loan_id', string='Installments', readonly=True)

    journal_id = fields.Many2one('account.journal', string='Payment Journal',
                                 domain="[('type', 'in', ('bank', 'cash'))]")

    # Odoo 19: Use active instead of deprecated
    emp_account_id = fields.Many2one('account.account', string='Loan Account', domain="[('active', '=', True)]")

    move_id = fields.Many2one('account.move', string='Accounting Entry', readonly=True)
    is_settled = fields.Boolean(string="Fully Settled", default=False)
    state = fields.Selection(selection=LoanStatus.SELECTION, string='Status', default=LoanStatus.DRAFT, tracking=True)

    # FIXED: Odoo 19 Batch Create Support
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.loan.request') or 'New'
        return super(HrLoanRequest, self).create(vals_list)

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
        if not self.journal_id or not self.emp_account_id:
            raise UserError(_("Please define Journal and Loan Account."))

        partner = self.employee_id.work_contact_id or self.employee_id.address_home_id
        if not partner:
            raise UserError(_("Employee needs a linked Address for Accounting entries."))

        credit_account = self.journal_id.default_account_id
        if not credit_account:
            raise UserError(_("Journal must have a default account."))

        move_vals = {
            'ref': f"{self.name} - {self.employee_id.name}",
            'date': fields.Date.today(),
            'journal_id': self.journal_id.id,
            'move_type': 'entry',
            'line_ids': [
                Command.create({
                    'name': f"Loan: {self.name}",
                    'account_id': self.emp_account_id.id,
                    'debit': self.loan_amount,
                    'credit': 0.0,
                    'partner_id': partner.id,
                }),
                Command.create({
                    'name': f"Payment: {self.name}",
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.loan_amount,
                }),
            ]
        }

        move = self.env['account.move'].create(move_vals)
        self.write({'move_id': move.id, 'state': LoanStatus.PAID})
        self._generate_installment_schedule()
        return self.action_open_account_move()

    def _generate_installment_schedule(self) -> None:
        self.ensure_one()
        if self.installment_count <= 0:
            return

        amt = self.loan_amount / self.installment_count
        lines = []
        for i in range(self.installment_count):
            lines.append(Command.create({
                'payment_date': self.payment_start_date + relativedelta(months=i),
                'amount': amt,
                'is_paid': False,
            }))
        self.write({'installment_ids': lines})

    # Workflow Actions
    def action_submit(self):
        self.write({'state': LoanStatus.SUBMITTED})

    def action_approve(self):
        self.write({'state': LoanStatus.APPROVED})

    def action_refuse(self):
        self.write({'state': LoanStatus.REFUSED})

    def action_reset_draft(self):
        self.write({'state': LoanStatus.DRAFT})
