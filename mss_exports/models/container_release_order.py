from odoo import api, fields, models


class ContainerReleaseOrder(models.Model):
    _name = 'container.release.order'
    _description = 'Container Release Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='CRO No.',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )

    contract_no = fields.Many2one(
        'rice.sales.contract',
        string='Contract No.',
        required=True,
        ondelete='restrict',
    )

    shipping_line = fields.Char(
        string='Shipping Line',
        required=True,
    )

    container_count = fields.Integer(
        string='No. of Containers',
        required=True,
        default=1,
    )

    container_type = fields.Selection(
        [
            ('20ft', '20ft'),
            ('40ft', '40ft'),
        ],
        string='Container Type',
        required=True,
    )

    empty_pickup_depot = fields.Char(
        string='Empty Pickup Depot',
        required=True,
    )

    release_validity_date = fields.Date(
        string='Release Validity Date',
        required=True,
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
                    'container.release.order'
                ) or 'New'

        return super().create(vals_list)

    def action_confirm(self):
        self.write({
            'state': 'confirmed',
        })
        return True