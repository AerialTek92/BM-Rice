from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
from typing import Any, List

# Constants
EXIT_STATE_DONE = 'done'


class SettlementStatus:
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'
    APPROVED = 'approved'
    PAID = 'paid'
    CLOSED = 'closed'

    SELECTION = [
        (DRAFT, 'Draft'),
        (CONFIRMED, 'Confirmed'),
        (APPROVED, 'Approved'),
        (PAID, 'Paid'),
        (CLOSED, 'Closed')
    ]


class HrFinalSettlement(models.Model):
    _name = 'hr.final.settlement'
    _description = 'Final Settlement Master'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Settlement Reference', required=True, copy=False, readonly=True, default='Draft')
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    exit_id = fields.Many2one('hr.exit', string='Exit Record',
                              domain="[('employee_id', '=', employee_id), ('state', '=', 'done')]", required=True)

    last_working_day = fields.Date(string='Last Working Day', related='exit_id.last_working_day')
    settlement_date = fields.Date(string='Settlement Date', default=fields.Date.today)
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)

    # Computes
    total_earnings = fields.Monetary(string='Total Earnings', compute='_compute_totals', store=True)
    total_deductions = fields.Monetary(string='Total Deductions', compute='_compute_totals', store=True)
    net_payable = fields.Monetary(string='Net Payable', compute='_compute_totals', store=True)

    # Lines
    earning_line_ids = fields.One2many('hr.final.earning.line', 'settlement_id', string='Earnings')
    deduction_line_ids = fields.One2many('hr.final.deduction.line', 'settlement_id', string='Deductions')
    gratuity_line_ids = fields.One2many('hr.final.gratuity', 'settlement_id', string='Gratuity Calculation')
    leave_encashment_ids = fields.One2many('hr.final.leave.encashment', 'settlement_id', string='Leave Encashment')
    pf_line_ids = fields.One2many('hr.final.pf', 'settlement_id', string='Provident Fund')

    state = fields.Selection(selection=SettlementStatus.SELECTION, string='Status', default=SettlementStatus.DRAFT,
                             tracking=True)

    # FIXED: Support for Odoo 19 Batch Create
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Draft') == 'Draft':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.final.settlement') or 'Draft'
        return super(HrFinalSettlement, self).create(vals_list)

    @api.onchange('employee_id')
    def _onchange_employee_id(self) -> None:
        if not self.employee_id: return
        exit_record = self.env['hr.exit'].search(
            [('employee_id', '=', self.employee_id.id), ('state', '=', EXIT_STATE_DONE)], limit=1)
        if exit_record:
            self.exit_id = exit_record.id

    @api.depends('earning_line_ids.amount', 'deduction_line_ids.amount', 'gratuity_line_ids.amount',
                 'leave_encashment_ids.amount', 'pf_line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            e = sum(rec.earning_line_ids.mapped('amount')) + sum(rec.gratuity_line_ids.mapped('amount')) + \
                sum(rec.leave_encashment_ids.mapped('amount')) + sum(rec.pf_line_ids.mapped('amount'))
            d = sum(rec.deduction_line_ids.mapped('amount'))
            rec.total_earnings = e
            rec.total_deductions = d
            rec.net_payable = e - d

    def action_fetch_outstanding_dues(self):
        self.ensure_one()
        loans = self.env['hr.loan.request'].search(
            [('employee_id', '=', self.employee_id.id), ('state', '=', 'paid'), ('is_settled', '=', False)])
        advances = self.env['hr.salary.advance'].search(
            [('employee_id', '=', self.employee_id.id), ('state', '=', 'paid'), ('is_settled', '=', False)])

        lines = []
        for loan in loans:
            if not self.deduction_line_ids.filtered(lambda l: l.loan_id == loan):
                lines.append(Command.create(
                    {'name': f"Loan Recovery: {loan.name}", 'amount': loan.loan_amount, 'is_recovery': True,
                     'loan_id': loan.id}))
        for adv in advances:
            if not self.deduction_line_ids.filtered(lambda l: l.advance_id == adv):
                lines.append(Command.create(
                    {'name': f"Advance Recovery: {adv.name}", 'amount': adv.advance_amount, 'is_recovery': True,
                     'advance_id': adv.id}))
        self.write({'deduction_line_ids': lines})

    def action_confirm(self):
        for line in self.deduction_line_ids:
            if line.loan_id: line.loan_id.is_settled = True
            if line.advance_id: line.advance_id.is_settled = True
        self.write({'state': SettlementStatus.CONFIRMED})

    def action_approve(self):
        self.write({'state': SettlementStatus.APPROVED})

    def action_mark_paid(self):
        self.write({'state': SettlementStatus.PAID})

    def action_close(self):
        self.write({'state': SettlementStatus.CLOSED})


# --- Settlement Line Models ---

class HrSettlementLineMixin(models.AbstractModel):
    _name = 'hr.final.settlement.line.mixin'
    _description = 'Abstract Settlement Line'
    settlement_id = fields.Many2one('hr.final.settlement', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='settlement_id.currency_id')
    amount = fields.Monetary(string='Amount', default=0.0)


class HrFinalEarningLine(models.Model):
    _name = 'hr.final.earning.line'
    _inherit = ['hr.final.settlement.line.mixin']
    name = fields.Char(string='Description', required=True)
    quantity = fields.Float(default=1.0)
    rate = fields.Float()

    @api.onchange('quantity', 'rate')
    def _onchange_amount(self):
        self.amount = self.quantity * self.rate


class HrFinalDeductionLine(models.Model):
    _name = 'hr.final.deduction.line'
    _inherit = ['hr.final.settlement.line.mixin']
    name = fields.Char(string='Description', required=True)
    is_recovery = fields.Boolean(default=False)
    loan_id = fields.Many2one('hr.loan.request')
    advance_id = fields.Many2one('hr.salary.advance')


class HrFinalLeaveEncashment(models.Model):
    _name = 'hr.final.leave.encashment'
    _inherit = ['hr.final.settlement.line.mixin']
    leave_type_id = fields.Many2one('hr.leave.type', required=True)
    remaining_days = fields.Float()
    encash_rate = fields.Monetary()

    @api.onchange('remaining_days', 'encash_rate')
    def _onchange_amount(self):
        self.amount = self.remaining_days * self.encash_rate


class HrFinalGratuity(models.Model):
    _name = 'hr.final.gratuity'
    _inherit = ['hr.final.settlement.line.mixin']
    joining_date = fields.Date(required=True)
    last_working_day = fields.Date(related='settlement_id.last_working_day')
    gross_salary = fields.Monetary()
    years_of_service = fields.Float(compute='_compute_gratuity', store=True)

    @api.depends('joining_date', 'last_working_day', 'gross_salary')
    def _compute_gratuity(self):
        for rec in self:
            if rec.joining_date and rec.last_working_day:
                delta = relativedelta(rec.last_working_day, rec.joining_date)
                years = delta.years + (1 if delta.months > 6 else 0)
                rec.years_of_service = float(years)
                rec.amount = (rec.gross_salary / 26) * 30 * float(years)


class HrFinalProvidentFund(models.Model):
    _name = 'hr.final.pf'
    _inherit = ['hr.final.settlement.line.mixin']
    basic_salary = fields.Monetary(required=True)
    percentage = fields.Float(default=10.0)

    @api.onchange('basic_salary', 'percentage')
    def _onchange_amount(self):
        # FIXED: Use self instead of rec inside onchange
        self.amount = self.basic_salary * (self.percentage / 100.0)

