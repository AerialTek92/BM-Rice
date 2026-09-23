from odoo import api, fields, models


class BankApplication(models.Model):
    _name = 'bank.application'
    _description = 'Bank Application / FIU'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fiu_date desc, id desc'

    # =========================================================
    # REFERENCE
    # =========================================================

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )

    # =========================================================
    # FIU INFORMATION
    # =========================================================

    fiu_no = fields.Char(
        string='FIU No.',
        required=True,
        copy=False,
        tracking=True,
    )

    fiu_date = fields.Date(
        string='FIU Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    application_type = fields.Selection(
        [
            ('e_form', 'E-Form'),
            ('other', 'Other'),
        ],
        string='Application Type',
        required=True,
        default='e_form',
        tracking=True,
    )

    # =========================================================
    # VESSEL BOOKING
    # =========================================================

    booking_id = fields.Many2one(
        'vessel.booking',
        string='Vessel Booking',
        required=True,
        ondelete='restrict',
        tracking=True,
    )

    # =========================================================
    # CONTRACT
    # =========================================================

    contract_no = fields.Many2one(
        'rice.sales.contract',
        string='Contract No.',
        related='booking_id.contract_no',
        store=True,
        readonly=True,
    )

    contract_date = fields.Date(
        string='Contract Date',
        related='contract_no.contract_date',
        store=True,
        readonly=True,
    )

    # =========================================================
    # BANK INFORMATION
    # =========================================================

    bank_name = fields.Char(
        string='Bank Name',
        required=True,
        tracking=True,
    )

    invoice_value = fields.Monetary(
        string='Invoice Value (USD)',
        currency_field='currency_id',
        tracking=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.ref(
            'base.USD',
            raise_if_not_found=False,
        ),
        readonly=True,
    )

    payment_terms = fields.Text(
        string='Payment Terms',
    )

    iban = fields.Char(
        string='IBAN / Account No.',
    )

    swift_code = fields.Char(
        string='SWIFT Code',
    )

    # =========================================================
    # STATUS
    # =========================================================

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )

    # =========================================================
    # CREATE
    # =========================================================

    @api.model_create_multi
    def create(self, vals_list):

        for vals in vals_list:

            if vals.get('name', 'New') == 'New':

                vals['name'] = self.env[
                    'ir.sequence'
                ].next_by_code(
                    'bank.application'
                ) or 'New'

        return super().create(vals_list)

    # =========================================================
    # ACTIONS
    # =========================================================

    def action_submit(self):

        self.write({
            'state': 'submitted',
        })

        return True

    def action_approve(self):

        self.write({
            'state': 'approved',
        })

        return True

    def action_reset_to_draft(self):

        self.write({
            'state': 'draft',
        })

        return True