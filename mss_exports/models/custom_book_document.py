from odoo import api, fields, models


class CustomBookDocument(models.Model):
    _name = 'custom.book.document'
    _description = 'Custom Book Document'
    _order = 'filing_date desc, id desc'

    # =========================================================
    # BASIC INFORMATION
    # =========================================================

    name = fields.Char(
        string='Custom Doc No.',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    gd_no = fields.Char(
        string='GD No.',
        help='Goods Declaration Number',
    )

    hs_code = fields.Char(
        string='HS Code',
    )

    custom_station = fields.Char(
        string='Custom Station',
    )

    filing_date = fields.Date(
        string='Filing Date',
        default=fields.Date.context_today,
    )

    filed_by = fields.Char(
        string='Filed By',
        help='Clearing Agent Name',
    )

    export_registration_no = fields.Char(
        string='Export Registration No.',
    )

    duty_tax_status = fields.Selection(
        [
            ('exempt', 'Exempt'),
            ('paid', 'Paid'),
        ],
        string='Duty/Tax Status',
    )

    # =========================================================
    # FIU APPLICATION
    # =========================================================

    fiu_application_id = fields.Many2one(
        'bank.application',
        string='Linked FIU No.',
        ondelete='restrict',
        index=True,
    )

    # =========================================================
    # FIU DISPLAY
    # =========================================================

    fiu_no = fields.Char(
        string='FIU No.',
        related='fiu_application_id.name',
        store=True,
        readonly=True,
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
                    'custom.book.document'
                ) or 'New'

        return super().create(vals_list)