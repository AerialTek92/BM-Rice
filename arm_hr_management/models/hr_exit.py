from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------
STATE_DRAFT = 'draft'
STATE_CONFIRMED = 'confirmed'
STATE_HR_APPROVED = 'hr_approved'
STATE_DONE = 'done'
STATE_CANCEL = 'cancel'

EXIT_TYPES = [
    ('resignation', 'Resignation'),
    ('termination', 'Termination'),
    ('contract_end', 'End of Contract')
]

STATES = [
    (STATE_DRAFT, 'Draft'),
    (STATE_CONFIRMED, 'Confirmed'),
    (STATE_HR_APPROVED, 'HR Approved'),
    (STATE_DONE, 'Done'),
    (STATE_CANCEL, 'Cancelled')
]


class HrExit(models.Model):
    """
    Odoo 19 Compatible: Manages the employee exit process.
    (Contract logic commented out as requested)
    """
    _name = 'hr.exit'
    _description = 'Employee Exit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identity
    name = fields.Char(
        string='Exit Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    # Employee Details
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)

    # --- Commented out hr_contract field ---
    # contract_id = fields.Many2one(
    #     'hr.contract',
    #     string='Contract',
    #     domain="[('employee_id', '=', employee_id), ('state', 'in', ['open', 'close'])]"
    # )

    # Dates & Type
    exit_type = fields.Selection(EXIT_TYPES, string='Exit Type', required=True)
    resignation_date = fields.Date(string='Resignation Date')
    last_working_day = fields.Date(string='Last Working Day', required=True)

    # Notice Period Logic
    notice_period_days = fields.Integer(string='Notice Period (Days)')
    notice_recovery_amount = fields.Monetary(
        string='Notice Recovery Amount',
        currency_field='currency_id'
    )

    # --- Commented out currency link to contract ---
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)

    reason = fields.Text(string='Exit Reason')
    state = fields.Selection(STATES, string='Status', default=STATE_DRAFT, tracking=True)

    # FIXED: Odoo 19 Batch Create Support for Sequence
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.exit') or 'New'
        return super(HrExit, self).create(vals_list)

    # --- Commented out contract auto-population ---
    # @api.onchange('employee_id')
    # def _onchange_employee_id(self) -> None:
    #     if not self.employee_id:
    #         return
    #     running_contract = self.env['hr.contract'].search([
    #         ('employee_id', '=', self.employee_id.id),
    #         ('state', '=', 'open')
    #     ], limit=1)
    #     if running_contract:
    #         self.contract_id = running_contract.id

    # Workflow Actions
    def action_confirm(self) -> None:
        self.write({'state': STATE_CONFIRMED})

    def action_hr_approve(self) -> None:
        self.write({'state': STATE_HR_APPROVED})

    def action_done(self) -> None:
        # self._expire_contract()  # Commented out
        self.write({'state': STATE_DONE})

    def action_cancel(self) -> None:
        self.write({'state': STATE_CANCEL})

    def action_draft(self) -> None:
        self.write({'state': STATE_DRAFT})

    # --- Commented out all contract/work entry cleanup helpers ---
    # def _expire_contract(self) -> None:
    #     if not self.contract_id:
    #         return
    #     self._clean_future_work_entries()
    #     self.contract_id.write({
    #         'state': 'close',
    #         'date_end': self.last_working_day
    #     })

    # def _clean_future_work_entries(self) -> None:
    #     if 'hr.work.entry' not in self.env:
    #         return
    #     future_entries = self.env['hr.work.entry'].search([
    #         ('contract_id', '=', self.contract_id.id),
    #         ('date_start', '>', self.last_working_day),
    #         ('state', '!=', 'draft')
    #     ])
    #     if future_entries:
    #         try:
    #             future_entries.write({'state': 'draft'})
    #         except Exception:
    #             raise UserError(_("Could not clean work entries. Check related payslips."))
