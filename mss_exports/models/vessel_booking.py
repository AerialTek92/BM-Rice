from odoo import api, fields, models


class VesselBooking(models.Model):
    _name = 'vessel.booking'
    _description = 'Vessel Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'etd desc, id desc'

    name = fields.Char(
        string='Booking No.',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    vessel_name_voyage = fields.Char(
        string='Vessel Name & Voyage',
        required=True,
    )

    shipping_line = fields.Char(
        string='Shipping Line',
        related='cro_id.shipping_line',
        store=True,
        readonly=True,
    )

    booking_type = fields.Selection(
        [
            ('nominated', 'Nominated'),
            ('actual_buyer', 'Actual Buyer'),
        ],
        string='Booking Type',
        required=True,
    )

    cnf_basis = fields.Boolean(
        string='CNF Basis',
    )

    pob = fields.Char(
        string='POB (Point of Booking)',
        required=True,
    )

    port_of_loading = fields.Char(
        string='Port of Loading',
        required=True,
    )

    port_of_discharge = fields.Char(
        string='Port of Discharge',
        required=True,
    )

    etd = fields.Date(
        string='ETD',
        required=True,
    )

    container_count = fields.Integer(
        string='No. of Containers Booked',
        related='cro_id.container_count',
        store=True,
        readonly=True,
    )

    cro_id = fields.Many2one(
        'container.release.order',
        string=' Container Release Order No.',
        required=True,
        ondelete='restrict',
    )

    contract_no = fields.Many2one(
        'rice.sales.contract',
        string='Contract No.',
        related='cro_id.contract_no',
        store=True,
        readonly=True,
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'vessel.booking'
                ) or 'New'

        return super().create(vals_list)

    def action_confirm(self):
        self.write({
            'state': 'confirmed',
        })
        return True