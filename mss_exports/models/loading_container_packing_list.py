from odoo import api, fields, models


class LoadingContainerPackingList(models.Model):
    _name = 'loading.container.packing.list'
    _description = 'Loading Container Packing List'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # =========================================================
    # BASIC INFORMATION
    # =========================================================

    name = fields.Char(
        string='Packing List No.',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )

    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    export_registration_no = fields.Char(
        string='Export Registration No.'
    )

    invoice_no = fields.Char(
        string='Invoice No.'
    )

    bl_no = fields.Char(
        string='BL No.'
    )

    sob_date = fields.Date(
        string='SOB Date'
    )

    fiu_no = fields.Char(
        string='FIU No.'
    )

    # =========================================================
    # CONTRACT
    # =========================================================

    contract_no = fields.Many2one(
        'rice.sales.contract',
        string='Contract No.',
        required=True,
        ondelete='restrict',
        tracking=True,
    )

    contract_date = fields.Date(
        string='Contract Date',
        related='contract_no.contract_date',
        store=True,
        readonly=True,
    )

    # =========================================================
    # SELLER
    # =========================================================

    seller = fields.Char(
        string='Seller',
        related='contract_no.company_id.name',
        store=True,
        readonly=True,
    )

    seller_address = fields.Char(
        string='Seller Address',
        related='contract_no.company_id.partner_id.contact_address',
        store=True,
        readonly=True,
    )

    # =========================================================
    # NOTIFY PARTY
    # =========================================================

    notify_party = fields.Char(
        string='Notify Party',
        related='contract_no.partner_id.name',
        store=True,
        readonly=True,
    )

    notify_party_address = fields.Char(
        string='Notify Party Address',
        related='contract_no.partner_id.contact_address',
        store=True,
        readonly=True,
    )

    # =========================================================
    # CONTRACT INFORMATION
    # =========================================================

    quality_description = fields.Char(
        string='Quality Description',
        related='contract_no.quality_description',
        store=True,
        readonly=True,
    )

    packing_details = fields.Text(
        string='Packing Details',
        related='contract_no.packing_details',
        store=True,
        readonly=True,
    )

    inspection_agency = fields.Char(
        string='Inspection Agency',
        related='contract_no.inspection_agency',
        store=True,
        readonly=True,
    )

    # =========================================================
    # VESSEL BOOKING
    # =========================================================

    booking_id = fields.Many2one(
        'vessel.booking',
        string='Booking No.',
        required=True,
        ondelete='restrict',
        tracking=True,
    )

    vessel_name_voyage = fields.Char(
        string='Vessel Name & Voyage',
        related='booking_id.vessel_name_voyage',
        store=True,
        readonly=True,
    )

    shipping_line = fields.Char(
        string='Shipping Line',
        related='booking_id.shipping_line',
        store=True,
        readonly=True,
    )

    booking_type = fields.Selection(
        string='Booking Type',
        related='booking_id.booking_type',
        store=True,
        readonly=True,
    )

    cnf_basis = fields.Boolean(
        string='CNF Basis',
        related='booking_id.cnf_basis',
        store=True,
        readonly=True,
    )

    pob = fields.Char(
        string='POB',
        related='booking_id.pob',
        store=True,
        readonly=True,
    )

    port_of_loading = fields.Char(
        string='Port of Loading',
        related='booking_id.port_of_loading',
        store=True,
        readonly=True,
    )

    port_of_discharge = fields.Char(
        string='Port of Discharge',
        related='booking_id.port_of_discharge',
        store=True,
        readonly=True,
    )

    etd = fields.Date(
        string='ETD',
        related='booking_id.etd',
        store=True,
        readonly=True,
    )

    cro_id = fields.Many2one(
        'container.release.order',
        string='CRO No.',
        related='booking_id.cro_id',
        store=True,
        readonly=True,
    )

    expected_container_count = fields.Integer(
        string='Expected Containers',
        related='booking_id.container_count',
        store=True,
        readonly=True,
    )

    # =========================================================
    # PRODUCT / PACKING INFORMATION
    # =========================================================

    shipping_mark = fields.Char(
        string='Shipping Mark'
    )

    brand = fields.Char(
        string='Brand'
    )

    grain_type = fields.Char(
        string='Grain Type'
    )

    variety = fields.Char(
        string='Variety'
    )

    bag_net_weight = fields.Float(
        string='Bag Net Weight (kg)',
        default=50.0,
    )

    bag_tare_weight = fields.Float(
        string='Bag Tare Weight (kg)',
        default=0.13,
    )

    # =========================================================
    # PRODUCT INFORMATION LINES
    # =========================================================

    product_line_ids = fields.One2many(
        'loading.container.packing.list.product.line',
        'packing_list_id',
        string='Product Information',
    )

    # =========================================================
    # CONTAINER LINES
    # =========================================================

    line_ids = fields.One2many(
        'loading.container.packing.list.line',
        'packing_list_id',
        string='Loading Containers',
    )

    # =========================================================
    # CONTAINER TOTALS
    # =========================================================

    loaded_container_count = fields.Integer(
        string='Loaded Containers',
        compute='_compute_totals',
        store=True,
    )

    remaining_container_count = fields.Integer(
        string='Remaining Containers',
        compute='_compute_totals',
        store=True,
    )

    extra_container_count = fields.Integer(
        string='Extra Containers',
        compute='_compute_totals',
        store=True,
    )

    # =========================================================
    # WEIGHT / QUANTITY TOTALS
    # =========================================================

    total_bags = fields.Integer(
        string='Total Bags',
        compute='_compute_totals',
        store=True,
    )

    total_gross_weight = fields.Float(
        string='Total Gross Weight (kg)',
        compute='_compute_totals',
        store=True,
    )

    total_net_weight = fields.Float(
        string='Total Net Weight (kg)',
        compute='_compute_totals',
        store=True,
    )

    total_tare_weight = fields.Float(
        string='Total Tare Weight (kg)',
        compute='_compute_totals',
        store=True,
    )

    total_vgm = fields.Float(
        string='Total VGM (kg)',
        compute='_compute_totals',
        store=True,
    )

    quantity_metric_tons = fields.Float(
        string='Quantity (MT)',
        compute='_compute_totals',
        store=True,
    )

    # =========================================================
    # STATUS
    # =========================================================

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
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
                    'loading.container.packing.list'
                ) or 'New'

            # Booking se Contract automatically set
            if vals.get('booking_id') and not vals.get('contract_no'):

                booking = self.env[
                    'vessel.booking'
                ].browse(
                    vals['booking_id']
                )

                if booking.contract_no:
                    vals['contract_no'] = booking.contract_no.id

        records = super().create(vals_list)

        for record in records:
            if record.contract_no:
                record._create_product_lines_from_contract()

        return records

    # =========================================================
    # WRITE
    # =========================================================

    def write(self, vals):

        result = super().write(vals)

        if 'contract_no' in vals:

            for record in self:

                record.product_line_ids.unlink()

                if record.contract_no:
                    record._create_product_lines_from_contract()

        return result

    # =========================================================
    # CREATE PRODUCT LINES FROM CONTRACT
    # =========================================================

    def _create_product_lines_from_contract(self):

        self.ensure_one()

        print("\n================ PACKING LIST DEBUG ================")
        print("Packing List:", self.name)
        print("Contract:", self.contract_no)
        print("Contract ID:", self.contract_no.id)

        contract_lines = self.contract_no.contract_line_ids

        print("Contract Lines:", contract_lines)
        print("Contract Lines Count:", len(contract_lines))

        for line in contract_lines:
            print("--------------------------------")
            print("Line ID:", line.id)
            print("Product:", line.product_id)
            print("Product ID:", line.product_id.id)
            print("Product Name:", line.product_id.name)
            print("Quantity:", line.quantity)
            print("Unit Price:", line.unit_price)
            print("UOM:", line.uom_id)
            print("Crop Year:", line.crop_year)

        self.product_line_ids.unlink()

        product_lines = []

        for index, contract_line in enumerate(
                contract_lines.filtered(lambda line: line.product_id),
                start=1
        ):
            product_lines.append({
                'packing_list_id': self.id,
                'sequence': index * 10,
                'contract_line_id': contract_line.id,
            })

        print("Product Lines To Create:", product_lines)

        if product_lines:
            created_lines = self.env[
                'loading.container.packing.list.product.line'
            ].create(product_lines)

            print("Created Product Lines:", created_lines)

        print("====================================================\n")

    # =========================================================
    # TOTALS
    # =========================================================

    @api.depends(
        'booking_id.container_count',
        'line_ids',
        'line_ids.no_of_bags',
        'line_ids.gross_weight',
        'line_ids.net_weight',
        'line_ids.tare_weight',
        'line_ids.vgm',
    )
    def _compute_totals(self):

        for record in self:

            lines = record.line_ids

            expected = (
                record.expected_container_count or 0
            )

            loaded = len(lines)

            record.loaded_container_count = loaded

            record.remaining_container_count = max(
                expected - loaded,
                0,
            )

            record.extra_container_count = max(
                loaded - expected,
                0,
            )

            record.total_bags = sum(
                lines.mapped('no_of_bags')
            )

            record.total_gross_weight = sum(
                lines.mapped('gross_weight')
            )

            record.total_net_weight = sum(
                lines.mapped('net_weight')
            )

            record.total_tare_weight = sum(
                lines.mapped('tare_weight')
            )

            record.total_vgm = sum(
                lines.mapped('vgm')
            )

            record.quantity_metric_tons = (
                record.total_net_weight / 1000
            )

    # =========================================================
    # CONFIRM
    # =========================================================

    def action_confirm(self):

        self.write({
            'state': 'confirmed'
        })

        return True

    @api.onchange('booking_id')
    def _onchange_booking_id(self):

        if self.booking_id:
            self.contract_no = self.booking_id.contract_no

            self.product_line_ids = [(5, 0, 0)]

            if self.contract_no:
                lines = []

                contract_lines = self.contract_no.contract_line_ids.filtered(
                    lambda line: line.product_id
                )

                for index, contract_line in enumerate(
                        contract_lines,
                        start=1,
                ):
                    lines.append(
                        (0, 0, {
                            'sequence': index * 10,
                            'contract_line_id': contract_line.id,
                        })
                    )

                self.product_line_ids = lines

        else:
            self.contract_no = False
            self.product_line_ids = [(5, 0, 0)]

from odoo import fields, models


class LoadingContainerPackingListProductLine(models.Model):
    _name = 'loading.container.packing.list.product.line'
    _description = 'Packing List Product Information'
    _order = 'sequence, id'

    packing_list_id = fields.Many2one(
        'loading.container.packing.list',
        string='Packing List',
        required=True,
        ondelete='cascade',
    )

    sequence = fields.Integer(
        string='Sr No.',
        default=10,
    )

    contract_line_id = fields.Many2one(
        'rice.sales.contract.line',
        string='Contract Line',
        readonly=True,
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='contract_line_id.product_id',
        store=True,
        readonly=True,
    )

    product_name = fields.Char(
        string='Product Name',
        related='product_id.name',
        store=True,
        readonly=True,
    )

    crop_year = fields.Char(
        string='Crop Year',
        related='contract_line_id.crop_year.name',
        store=True,
        readonly=True,
    )

    quantity = fields.Float(
        string='Quantity',
        related='contract_line_id.quantity',
        store=True,
        readonly=True,
    )

    unit_price = fields.Monetary(
        string='Unit Price',
        related='contract_line_id.unit_price',
        currency_field='currency_id',
        store=True,
        readonly=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='contract_line_id.currency_id',
        store=True,
        readonly=True,
    )

    uom_id = fields.Many2one(
        'uom.uom',
        string='UOM',
        related='contract_line_id.uom_id',
        store=True,
        readonly=True,
    )

    quality_description = fields.Char(
        string='Quality Description',
        related='packing_list_id.quality_description',
        store=True,
        readonly=True,
    )

    packing_details = fields.Text(
        string='Packing Details',
        related='packing_list_id.packing_details',
        store=True,
        readonly=True,
    )

    inspection_agency = fields.Char(
        string='Inspection Agency',
        related='packing_list_id.inspection_agency',
        store=True,
        readonly=True,
    )

    shipping_mark = fields.Char(
        string='Shipping Mark',
        related='packing_list_id.shipping_mark',
        store=True,
        readonly=True,
    )

    brand = fields.Char(
        string='Brand',
        related='packing_list_id.brand',
        store=True,
        readonly=True,
    )

    grain_type = fields.Char(
        string='Grain Type',
        related='packing_list_id.grain_type',
        store=True,
        readonly=True,
    )

    variety = fields.Char(
        string='Variety',
        related='packing_list_id.variety',
        store=True,
        readonly=True,
    )

    bag_net_weight = fields.Float(
        string='Bag Net Weight (kg)',
        related='packing_list_id.bag_net_weight',
        store=True,
        readonly=True,
    )

    bag_tare_weight = fields.Float(
        string='Bag Tare Weight (kg)',
        related='packing_list_id.bag_tare_weight',
        store=True,
        readonly=True,
    )