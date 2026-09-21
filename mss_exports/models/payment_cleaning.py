from odoo import api, fields, models


class PaymentCleaning(models.Model):
    _name = 'payment.cleaning'
    _description = 'Payment / Cleaning'
    _order = 'payment_received_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    invoice_no = fields.Char(
        string='Invoice No.',
        required=True,
    )

    payment_received_date = fields.Date(
        string='Payment Received Date',
    )

    amount_received = fields.Monetary(
        string='Amount Received (USD)',
        currency_field='currency_id',
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.ref('base.USD'),
    )

    bank_reference_no = fields.Char(
        string='Bank Reference No.',
    )

    document_set_sent_date = fields.Date(
        string='Document Set Sent Date',
        help='Invoice + Packing List + BL + DO sent to bank.',
    )

    cleaning_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('done', 'Done'),
        ],
        string='Cleaning / Reconciliation Status',
        required=True,
        default='pending',
    )

    remarks = fields.Text(
        string='Remarks',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'payment.cleaning'
                ) or 'New'

        return super().create(vals_list)

    def action_mark_done(self):
        for record in self:
            record.cleaning_status = 'done'

    def action_mark_pending(self):
        for record in self:
            record.cleaning_status = 'pending'