# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from typing import Dict, Any, List, Tuple

PERCENTAGE_DIVISOR = 100.0
COMMAND_CREATE_NEW: int = 0


class RiceSalesContract(models.Model):
    _name = 'rice.sales.contract'
    _description = 'Rice Sales Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # --- Header Fields ---
    name = fields.Char(string='Contract No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    external_contract_no = fields.Char(string='External Contract No')
    contract_date = fields.Date(string='Order Date', default=fields.Date.today(), required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True,
                                 domain=[('customer_rank', '>', 0)])
    company_id = fields.Many2one('res.company', string='Seller / Exporter', default=lambda self: self.env.company,
                                 required=True)

    quality_description = fields.Char(string='Quality Description')
    contract_term = fields.Selection([('contract', 'Contract'), ('spot', 'Spot Sales')], string='Term',
                                     default='contract')

    # Contract Categorization
    contract_type = fields.Selection([
        ('export', 'Export Sales')
    ], string='Contract Type', tracking=True)

    # --- Notebook / Tab Fields ---
    contract_line_ids = fields.One2many('rice.sales.contract.line', 'contract_id', string='Contract Lines')
    shipment_schedule_ids = fields.One2many('rice.shipment.schedule', 'contract_id', string='Shipment Schedule')

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id,
                                  required=True)
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms')

    # --- Computed Totals (Header) ---
    total_quantity = fields.Float(string='Qty (MTons)', compute='_compute_totals', store=True)
    header_unit_price = fields.Float(string='Rate (MTons)', compute='_compute_totals', store=True)
    total_amount = fields.Monetary(string='Amount', compute='_compute_totals', store=True, currency_field='currency_id')

    # --- Logistics ---
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterms')
    port_of_loading = fields.Char(string='Port of Loading')
    port_of_discharge = fields.Char(string='Port of Discharge')
    destination_country_id = fields.Many2one('res.country', string='Destination Country')
    delivery_date_from = fields.Date(string='Shipping Period From')
    delivery_date_to = fields.Date(string='Shipping Period To')
    shipment_period_display = fields.Char(string='Shipment Period Text')
    packing_details = fields.Text(string='Packing Details')
    inspection_agency = fields.Char(string='Inspection Agency')
    insurance = fields.Char(string='Insurance')
    remarks = fields.Html(string='Remarks / Special Conditions')

    # --- Status ---
    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # --- Smart Button Counts ---
    purchase_order_count = fields.Integer(string='Purchase Orders', compute='_compute_purchase_order_count')
    sale_order_count = fields.Integer(string='Sales Memos', compute='_compute_sale_order_count')
    delivery_order_count = fields.Integer(string='Delivery Orders', compute='_compute_delivery_order_count')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'RiceSalesContract':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rice.sales.contract') or _('New')
        return super().create(vals_list)

    # --- Calculation: Line -> Header ---
    @api.depends('contract_line_ids.quantity', 'contract_line_ids.unit_price')
    def _compute_totals(self) -> None:
        for rec in self:
            qty_sum = sum(rec.contract_line_ids.mapped('quantity'))
            rate_sum = sum(rec.contract_line_ids.mapped('unit_price'))
            rec.total_quantity = qty_sum
            rec.header_unit_price = rate_sum
            rec.total_amount = qty_sum * rate_sum

    def _compute_purchase_order_count(self) -> None:
        for rec in self:
            rec.purchase_order_count = self.env['purchase.order'].search_count([
                ('rice_sales_contract_id', '=', rec.id)
            ])

    def _compute_sale_order_count(self) -> None:
        for rec in self:
            rec.sale_order_count = self.env['sale.order'].search_count([
                ('rice_sales_contract_id', '=', rec.id)
            ])

    def _compute_delivery_order_count(self) -> None:
        for rec in self:
            rec.delivery_order_count = self.env['stock.picking'].search_count([
                ('sale_id.rice_sales_contract_id', '=', rec.id),
                ('picking_type_code', '=', 'outgoing')
            ])

    def action_confirm(self) -> None:
        """Protocol 2.1: Confirm contract and auto-generate draft PO/SO based on type."""
        for rec in self:
            if not rec.contract_line_ids:
                raise ValidationError(_("You must add at least one product line before confirming."))

            rec.state = 'confirmed'

            # Auto-create documents only if they don't already exist
            if rec.contract_type == 'export' and rec.delivery_order_count == 0:
                rec._create_and_confirm_export_sale_order()

    def _create_draft_purchase_order(self) -> None:
        """Protocol 2.1 (SRP): Create a draft Purchase Order mapping lines from the RSC."""
        self.ensure_one()
        order_lines: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.contract_line_ids.filtered(lambda l: l.product_id):
            order_lines.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name or line.product_id.name,
                'product_qty': line.quantity,
                'price_unit': line.unit_price,
                'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
                'crop_year': line.crop_year.id,
                'moisture_percent': line.moisture_percent_max,
                'broken_percent': line.broken_percent_max,
                'rice_contract_line_id': line.id,
            }))

        self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'rice_sales_contract_id': self.id,
            'origin': self.name,
            'date_order': self.contract_date,
            'delivery_date_from': self.delivery_date_from,
            'delivery_date_to': self.delivery_date_to,
            'remarks': self.remarks,
            'order_line': order_lines,
        })

    def _create_draft_sale_order(self) -> None:
        """Protocol 2.1 (SRP): Create a draft Sales Memo mapping lines from the RSC."""
        self.ensure_one()
        order_lines: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.contract_line_ids.filtered(lambda l: l.product_id):
            order_lines.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name or line.product_id.name,
                'product_uom_qty': line.quantity,
                'price_unit': line.unit_price,
                'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
            }))

        self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'rice_sales_contract_id': self.id,
            'origin': self.name,
            'date_order': self.contract_date,
            'validity_date': False,
            'order_line': order_lines,
        })

    def _create_and_confirm_export_sale_order(self) -> None:
        """Protocol 2.1 (SRP): Create a hidden, auto-confirmed Sales Memo for Export contracts."""
        self.ensure_one()
        order_lines: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.contract_line_ids.filtered(lambda l: l.product_id):
            order_lines.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name or line.product_id.name,
                'product_uom_qty': line.quantity,
                'price_unit': line.unit_price,
                'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,

            }))

        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'rice_sales_contract_id': self.id,
            'origin': self.name,
            'date_order': self.contract_date,
            'validity_date': False,
            'order_line': order_lines,
            'is_export_hidden': False,  # FIX: Use custom field to hide from standard list view
        })

        # Auto-confirm the Sales Memo to trigger native Delivery Order creation
        sale = self.env['sale.order'].browse(sale_order.id)

        # raise UserError("Sale Order: " + str(sale_order))
        sale.action_confirm()

    def action_complete(self) -> None:
        for rec in self: rec.state = 'done'

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'

    def action_view_purchase_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('rice_sales_contract_id', '=', self.id)],
            'context': {'default_rice_sales_contract_id': self.id, 'default_contract_type': 'procurement'}
        }

    def action_view_sale_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sales Memos',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('rice_sales_contract_id', '=', self.id)],
            'context': {'default_rice_sales_contract_id': self.id, 'default_contract_type': self.contract_type}
        }

    def action_view_delivery_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Delivery Orders',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('sale_id.rice_sales_contract_id', '=', self.id), ('picking_type_code', '=', 'outgoing')],
            'context': {'default_picking_type_code': 'outgoing'}
        }


class RiceSalesContractLine(models.Model):
    _name = 'rice.sales.contract.line'
    _description = 'Rice Sales Contract Line'

    contract_id = fields.Many2one('rice.sales.contract', string='Contract', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True, domain=[('sale_ok', '=', True)])

    is_brown_rice = fields.Boolean(related='product_id.is_brown_rice', string='Is Brown Rice')

    crop_year = fields.Many2one('master.crop.year', string='Crop Year',
                                default=lambda self: self.env['master.crop.year'].search(
                                    [('name', '=', str(fields.Date.today().year))], limit=1))

    quantity = fields.Float(string='Qty (MTons)', required=True, default=1.0)
    unit_price = fields.Monetary(string='Rate (MTons)', required=True, currency_field='currency_id')

    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='contract_id.currency_id', readonly=True)
    tolerance_percent = fields.Float(string='Tolerance (%)')

    # Standard fields (for normal products)
    moisture_percent_max = fields.Float(string='Moisture (% max)')
    broken_percent_max = fields.Float(string='Broken (% max)')
    damaged_discolor_percent_max = fields.Float(string='Damaged/Discolor (% max)')
    foreign_matter_percent_max = fields.Float(string='Foreign Matter (% max)')
    paddy_percent_max = fields.Float(string='Paddy (% max)')
    red_chalky_percent_max = fields.Float(string='Red/Chalky (% max)')

    # Brown Rice Specific Fields
    br_purity = fields.Float(string='Purity')
    br_broken = fields.Float(string='Broken')
    br_green_grains = fields.Float(string='Green grains')
    br_chalky_grains = fields.Float(string='Chalky grains')
    br_ddkg = fields.Float(string='Discoloured, damaged and Kernels Grain')
    br_immature_grains = fields.Float(string='Immature Grains')
    br_paddy_grains = fields.Float(string='Paddy grains')
    br_red_grains = fields.Float(string='Red grains')
    br_other_rices = fields.Float(string='Other Rices')
    br_moisture = fields.Float(string='Moisture')
    br_avg_length = fields.Float(string='Avg.Length')
    br_head_yield = fields.Float(string="Head Yield")
    br_foreign_matter = fields.Float(string='Foreign Matters')
    br_yellow_amber = fields.Float(string='Yellow/Amber Kernels')
    br_foreign_odours = fields.Float(string="Foreign odours/smell")
    br_chemical_residues = fields.Float(string="Chemical Residues and Radioactivity")
    br_aflatoxinsA = fields.Float(string="Aflatoxins B1")
    br_aflatoxins = fields.Float(string='Aflatoxins B1+B2+G1+G2')
    br_living_insects = fields.Float(string='Insects Live/Dead')
    br_Animals_birds = fields.Float(string='Animals Birds')

    @api.onchange('product_id')
    def _onchange_product_id_set_defaults(self) -> None:
        if not self.product_id:
            self.uom_id = False
            self._clear_all_specs()
            return

        self.uom_id = self.product_id.uom_id.id
        self._clear_all_specs()

        if self.product_id.is_brown_rice and self.product_id.brown_rice_spec_id:
            spec = self.product_id.brown_rice_spec_id
            self.br_purity = spec.purity
            self.br_broken = spec.broken
            self.br_green_grains = spec.green_grains
            self.br_chalky_grains = spec.chalky_grains
            self.br_ddkg = spec.ddkg
            self.br_immature_grains = spec.immature_grains
            self.br_paddy_grains = spec.paddy_grains
            self.br_red_grains = spec.red_grains
            self.br_other_rices = spec.other_rices
            self.br_moisture = spec.moisture
            self.br_avg_length = spec.avg_length
            self.br_head_yield = spec.head_yield
            self.br_foreign_matter = spec.foreign_matter
            self.br_yellow_amber = spec.yellow_amber
            self.br_foreign_odours = spec.foreign_odours
            self.br_chemical_residues = spec.chemical_residues
            self.br_aflatoxinsA = spec.aflatoxinsA
            self.br_aflatoxins = spec.aflatoxins
            self.br_living_insects = spec.living_insects
            self.br_Animals_birds = spec.Animals_birds

    def _clear_all_specs(self) -> None:
        self.moisture_percent_max = 0.0
        self.broken_percent_max = 0.0
        self.damaged_discolor_percent_max = 0.0
        self.foreign_matter_percent_max = 0.0
        self.paddy_percent_max = 0.0
        self.red_chalky_percent_max = 0.0

        self.br_purity = 0.0
        self.br_broken = 0.0
        self.br_green_grains = 0.0
        self.br_chalky_grains = 0.0
        self.br_ddkg = 0.0
        self.br_immature_grains = 0.0
        self.br_paddy_grains = 0.0
        self.br_red_grains = 0.0
        self.br_other_rices = 0.0
        self.br_moisture = 0.0
        self.br_avg_length = 0.0
        self.br_head_yield = 0.0
        self.br_foreign_matter = 0.0
        self.br_yellow_amber = 0.0
        self.br_foreign_odours = 0.0
        self.br_chemical_residues = 0.0
        self.br_aflatoxinsA = 0.0
        self.br_aflatoxins = 0.0
        self.br_living_insects = 0.0
        self.br_Animals_birds = 0.0

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self) -> None:
        for line in self: line.subtotal = line.quantity * line.unit_price


class RiceShipmentSchedule(models.Model):
    _name = 'rice.shipment.schedule'
    _description = 'Shipment Schedule'

    contract_id = fields.Many2one('rice.sales.contract', ondelete='cascade')
    quantity = fields.Float(string='Qty')
    rate = fields.Float(string='$ Rate')
    date_from = fields.Date(string='From Date')
    date_to = fields.Date(string='To Date')
    loading_port = fields.Char(string='Loading Port')