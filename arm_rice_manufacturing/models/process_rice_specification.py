# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Searchable Constants (Protocol 1.3) ---
KG_PER_MT: float = 1000.0
TARGET_BAG_WEIGHT_KG: float = 50.0
PERCENTAGE_MULTIPLIER: float = 100.0

IRRI_RICE_TYPE: str = 'irri'


class ProcessRiceSpec(models.Model):
    _name = 'process.rice.spec'
    _description = 'Process Rice Specification'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Ref No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Date', default=fields.Date.today(), required=True)
    production_on = fields.Date(string='Production On')

    is_brown_rice = fields.Boolean(string='Is Brown Rice')

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract Ref')
    partner_id = fields.Many2one('res.partner', string='Customer', related='rice_sales_contract_id.partner_id',
                                 store=True, readonly=True)

    destination_country_id = fields.Many2one('res.country', string='Destination Country')

    rice_type = fields.Selection([
        ('irri', 'IRRI'),
        ('basmati', 'Basmati')
    ], string='Rice Type', default='irri', required=True, tracking=True)

    # Basmati: the single Process Rice. IRRI: internal value, auto-derived
    # from the selected products - never shown to IRRI users.
    product_id = fields.Many2one('product.product', string='Process Rice')

    # IRRI: the per-product EDITOR. One line per product, each with its own
    # planned quantity. The tags field below is DERIVED from these lines and
    # feeds all downstream machinery (BJO, PLS, WB, PR).
    process_rice_line_ids = fields.One2many(
        'process.rice.spec.product.line',
        'spec_id',
        string='Process Rice',
    )

    # Machinery: derived from the lines (IRRI). Kept because every downstream
    # consumer reads it; no longer shown in the PRS view.
    process_rice_ids = fields.Many2many(
        'product.product',
        'prs_process_rice_rel',
        'spec_id',
        'product_id',
        string='Process Rice',
        help="IRRI only: all Process Rice products produced under this specification. "
             "Derived from the Process Rice lines.",
    )

    raw_rice_ids = fields.Many2many(
        'product.product',
        compute='_compute_raw_rice_ids',
        string='Raw Rice',
    )

    # Brand: same per-type pattern as Process Rice.
    brand_id = fields.Many2one('master.brand', string='Brand')
    brand_ids = fields.Many2many(
        'master.brand',
        'prs_brand_rel',
        'spec_id',
        'brand_id',
        string='Brand',
        help="IRRI only: all Brands produced under this specification.",
    )

    # Total planned Process Rice quantity: computed SUM of the lines for IRRI;
    # a manual single value for Basmati (one product, one qty).
    process_rice_qty = fields.Float(
        string='Process Rice QTY',
        compute='_compute_process_rice_qty',
        store=True,
        readonly=False,
        help="IRRI: total of the per-product quantities (not editable - edit the lines). "
             "Basmati: the single planned quantity.",
    )

    total_quantity = fields.Float(
        string='Total Quantity (Raw Rice MT)',
        compute='_compute_total_quantity',
        store=True,
        readonly=True
    )

    est_recovery_pct = fields.Float(
        string='Est Recovery %',
        compute='_compute_recovery_and_bags',
        store=True,
        readonly=True,
        digits=(16, 3)
    )

    no_of_bags = fields.Integer(
        string='No of Bags (Raw Rice)',
        compute='_compute_recovery_and_bags',
        store=True,
        readonly=True
    )

    packing = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('bo_pp_bags', 'BO PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('non_woven_bags', 'Non Woven Bags')
    ], string='Packing Material (Process Rice)')

    # --- Packing Weight with UoM Logic ---
    pp_bag_uom = fields.Selection([
        ('kg', 'Kgs'),
        ('lb', 'Lbs')
    ], string='Unit of Measure', default='kg', required=True)

    pp_bag_kg = fields.Many2one(
        'master.bag.weight',
        string='Weight (Kgs)',
    )

    pp_bag_lb = fields.Float(string='Weight (Lbs)')

    remarks = fields.Html(string='Remarks')

    spec_line_ids = fields.One2many('process.rice.spec.line', 'spec_id', string='Specification Lines')

    additional_spec_line_ids = fields.One2many('process.rice.spec.additional.line', 'spec_id',
                                               string='Additional Specifications')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    job_order_count = fields.Integer(string='Job Orders', compute='_compute_job_order_count')

    # ==========================================
    # Normal Rice Specs (Now on Header)
    # ==========================================
    n_moisture_percent = fields.Float(string='Moisture (%)')
    n_broken_percent = fields.Float(string='Broken (%)')
    n_damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    n_foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    n_paddy_percent = fields.Char(string='Paddy Grain/Kg')
    n_red_percent = fields.Float(string='Red (%)')
    n_chalky_percent = fields.Float(string='Chalky (%)')
    n_immature = fields.Float(string="Immature")
    n_cooking = fields.Char(string="Cooking", default="null")
    n_insect_damage_grains = fields.Float(string='Insect Damage Grains (%)')
    n_foreign_food_grains = fields.Float(string='Foreign Food Grains (%)')
    n_under_milled_grains = fields.Float(string='Under-milled Grains (%)')
    n_contrasting_varieties = fields.Float(string='Contrasting Varieties (%)')
    n_living_insects_mites = fields.Char(string='Living Insects & Mites')
    n_polish = fields.Char(string='Polish')
    n_agl = fields.Float(string='AGL (mm)')
    n_kett_whiteness = fields.Float(string='KETT Whiteness')

    # ==========================================
    # Brown Rice Specs (Standard Fields, NOT related)
    # ==========================================
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
    br_chemical_residues = fields.Float(string='Chemical Residues and Radioactivity')
    br_aflatoxinsA = fields.Float(string='Aflatoxins B1')
    br_aflatoxins = fields.Float(string='Aflatoxins B1+B2+G1+G2')
    br_living_insects = fields.Float(string='Insects Live/Dead')
    br_Animals_birds = fields.Float(string='Animals Birds')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProcessRiceSpec':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('process.rice.spec') or _('New')

            # Server-side twin: contract selection maps the country on
            # programmatic creation too (onchanges never run on create).
            if vals.get('rice_sales_contract_id') and not vals.get('destination_country_id'):
                contract = self.env['rice.sales.contract'].browse(vals['rice_sales_contract_id'])
                vals['destination_country_id'] = contract.destination_country_id.id

        records = super().create(vals_list)

        # Server-side twins: products follow the lines; the internal product
        # follows the products (IRRI).
        for rec in records:
            if rec.process_rice_line_ids:
                rec._sync_products_from_lines()
            if rec.rice_type == IRRI_RICE_TYPE:
                rec.product_id = rec._get_derived_process_rice()
        return records

    def write(self, vals: Dict[str, Any]) -> bool:
        result = super().write(vals)

        # Server-side twin: the product list follows the lines.
        if 'process_rice_line_ids' in vals:
            for rec in self:
                if rec.process_rice_line_ids:
                    rec._sync_products_from_lines()
        return result

    def _compute_job_order_count(self) -> None:
        for rec in self:
            rec.job_order_count = rec._get_related_record_count('brand.job.order', 'process_rice_spec_id')

    @api.depends('spec_line_ids.quantity')
    def _compute_total_quantity(self) -> None:
        for rec in self:
            rec.total_quantity = sum(rec.spec_line_ids.mapped('quantity'))

    @api.depends('spec_line_ids.product_id')
    def _compute_raw_rice_ids(self) -> None:
        """Protocol 2.1 (SRP): the raw rice products of this spec, derived
        from the Specification Lines (read-only display surface)."""
        for rec in self:
            rec.raw_rice_ids = rec.spec_line_ids.mapped('product_id')

    @api.depends('process_rice_line_ids.qty_mt', 'rice_type')
    def _compute_process_rice_qty(self) -> None:
        """IRRI: total = sum of the per-product line quantities.
        Basmati: the manual single value is preserved (assigning the current
        value keeps user input intact through recomputes)."""
        for rec in self:
            if rec.rice_type == IRRI_RICE_TYPE and rec.process_rice_line_ids:
                rec.process_rice_qty = sum(rec.process_rice_line_ids.mapped('qty_mt'))
            else:
                rec.process_rice_qty = rec.process_rice_qty

    @api.depends('total_quantity', 'process_rice_qty', 'spec_line_ids.quantity')
    def _compute_recovery_and_bags(self) -> None:
        """Protocol 2.1: Single Responsibility calculation for Recovery and Bags."""
        for rec in self:
            total_qty = sum(rec.spec_line_ids.mapped('quantity'))

            if total_qty > 0:
                rec.est_recovery_pct = (rec.process_rice_qty / total_qty) * PERCENTAGE_MULTIPLIER
                total_kgs = total_qty * KG_PER_MT
                rec.no_of_bags = int(total_kgs / TARGET_BAG_WEIGHT_KG) if TARGET_BAG_WEIGHT_KG > 0 else 0
            else:
                rec.est_recovery_pct = 0.0
                rec.no_of_bags = 0

    # ==========================================
    # Helper — Bag Weight numeric value
    # ==========================================
    def _get_bag_weight_value(self) -> float:
        """Selected UoM (Kgs/Lbs) ke mutabiq bag weight ka numeric value."""
        self.ensure_one()
        if self.pp_bag_uom == 'kg':
            return self.pp_bag_kg.weight_kg if self.pp_bag_kg else 0.0
        elif self.pp_bag_uom == 'lb':
            return self.pp_bag_lb or 0.0
        return 0.0

    # ==========================================================
    # IRRI MULTI-PRODUCT: lines are the editor, tags are machinery
    # ==========================================================

    def _get_derived_process_rice(self) -> 'product.product':
        """Internal machinery: the ONE product Odoo's Manufacturing Order will
        produce. Deterministic (alphabetically first) - purely internal, never
        shown to IRRI users; every selected product still enters stock with
        its actual weighed weight."""
        self.ensure_one()
        return self.process_rice_ids.sorted(key=lambda product: product.name or '')[:1]

    def _sync_products_from_lines(self) -> None:
        """Protocol 2.1 (SRP): the product tags (downstream machinery) follow
        the Process Rice lines. One line = one product; duplicate lines for
        the same product collapse into one tag."""
        self.ensure_one()
        products = self.process_rice_line_ids.mapped('product_id')
        self.process_rice_ids = [(6, 0, products.ids)]

    @api.onchange('product_id')
    def _onchange_product_id_map_spec(self) -> None:
        """Basmati: selecting the single Process Rice maps the product's
        stored specification onto the PRS header (name-for-name mirror).
        No-op for products without specification lines."""
        if self.rice_type != IRRI_RICE_TYPE and self.product_id:
            self._map_product_spec_to_header(self.product_id)

    @api.onchange('process_rice_line_ids')
    def _onchange_process_rice_lines_sync_products(self) -> None:
        """Lines edited: product tags follow, internal product follows, and
        the last line's product maps its specification to the header (the
        IRRI surface for product-spec mapping)."""
        if self.process_rice_line_ids:
            self._sync_products_from_lines()
            if self.rice_type == IRRI_RICE_TYPE:
                self.product_id = self._get_derived_process_rice()
                last_line = self.process_rice_line_ids[-1:]
                if last_line and last_line.product_id:
                    self._map_product_spec_to_header(last_line.product_id)

    @api.onchange('rice_type')
    def _onchange_rice_type_reset_multi_selections(self) -> None:
        """Multi-product and multi-brand are IRRI-only concepts: switching
        away clears both."""
        if self.rice_type != IRRI_RICE_TYPE:
            self.process_rice_line_ids = [COMMAND_CLEAR_ALL]
            self.process_rice_ids = [COMMAND_CLEAR_ALL]
            self.brand_ids = [COMMAND_CLEAR_ALL]

    # ==========================================================
    # PRODUCT SPEC -> PRS MAPPING
    # (Field names/types mirror product.specification.line exactly -
    # protocol 1.2: one vocabulary, one copy routine.)
    # ==========================================================

    # Class-level constant (Protocol 1.3): the name-for-name spec fields
    # copied from the product's specification lines to the PRS header.
    PRODUCT_SPEC_FIELDS: Tuple[str, ...] = (
        'n_moisture_percent', 'n_broken_percent', 'n_damaged_discolor_percent',
        'n_foreign_matter_percent', 'n_red_percent', 'n_chalky_percent',
        'n_immature', 'n_cooking', 'n_insect_damage_grains',
        'n_foreign_food_grains', 'n_under_milled_grains',
        'n_contrasting_varieties', 'n_agl', 'n_kett_whiteness',
    )
    PRODUCT_SPEC_TEXT_FIELDS: Tuple[str, ...] = (
        'n_paddy_percent', 'n_living_insects_mites', 'n_polish',
    )

    def _map_product_spec_to_header(self, product: 'product.product') -> None:
        """Protocol 2.1 (SRP): fill the PRS normal-spec header from the
        product's first specification line - name-for-name, same types.
        Products without specification lines leave the header untouched."""
        self.ensure_one()
        if not product:
            return

        spec_line = product.product_tmpl_id.specification_line_ids[:1]
        if not spec_line:
            return

        for field_name in self.PRODUCT_SPEC_FIELDS:
            self[field_name] = spec_line[field_name]
        for field_name in self.PRODUCT_SPEC_TEXT_FIELDS:
            self[field_name] = spec_line[field_name]

    @api.onchange('rice_sales_contract_id')
    def _onchange_rice_sales_contract_id(self):
        """Fetch product and specifications directly from Sales Contract Reference."""
        if not self.rice_sales_contract_id:
            self.update({
                'partner_id': False,
                'product_id': False,
                'is_brown_rice': False,
                'process_rice_qty': 0.0,
                'destination_country_id': False,
            })
            self.process_rice_line_ids = [COMMAND_CLEAR_ALL]
            self.process_rice_ids = [COMMAND_CLEAR_ALL]
            self._clear_normal_rice_specs()
            self._clear_brown_rice_specs()
            return

        contract = self.rice_sales_contract_id

        # Destination Country is a CONTRACT HEADER field: it maps even when the
        # contract has no lines yet.
        self.destination_country_id = contract.destination_country_id.id

        first_line = contract.contract_line_ids[:1]

        if not first_line:
            self.product_id = False
            self.is_brown_rice = False
            return

        self.update({
            'partner_id': contract.partner_id.id,
            'product_id': first_line.product_id.id,
            'is_brown_rice': first_line.is_brown_rice,
        })

        # IRRI: map the CONTRACT LINES into the Process Rice lines - product
        # AND its contracted quantity (user adjusts from here).
        if self.rice_type == IRRI_RICE_TYPE:
            line_commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
            for contract_line in contract.contract_line_ids.filtered(lambda l: l.product_id):
                line_commands.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': contract_line.product_id.id,
                    'qty_mt': contract_line.quantity,
                }))
            self.process_rice_line_ids = line_commands
            self._sync_products_from_lines()
            self.product_id = self._get_derived_process_rice()
            # process_rice_qty (the total) recomputes from the lines.
        else:
            self.process_rice_qty = contract.total_quantity

        if first_line.is_brown_rice:
            self._clear_normal_rice_specs()
            self.br_purity = first_line.br_purity
            self.br_broken = first_line.br_broken
            self.br_green_grains = first_line.br_green_grains
            self.br_chalky_grains = first_line.br_chalky_grains
            self.br_ddkg = first_line.br_ddkg
            self.br_immature_grains = first_line.br_immature_grains
            self.br_paddy_grains = first_line.br_paddy_grains
            self.br_red_grains = first_line.br_red_grains
            self.br_other_rices = first_line.br_other_rices
            self.br_moisture = first_line.br_moisture
            self.br_avg_length = first_line.br_avg_length
            self.br_head_yield = first_line.br_head_yield
            self.br_foreign_matter = first_line.br_foreign_matter
            self.br_yellow_amber = first_line.br_yellow_amber
            self.br_foreign_odours = first_line.br_foreign_odours
            self.br_chemical_residues = first_line.br_chemical_residues
            self.br_aflatoxinsA = first_line.br_aflatoxinsA
            self.br_aflatoxins = first_line.br_aflatoxins
            self.br_living_insects = first_line.br_living_insects
            self.br_Animals_birds = first_line.br_Animals_birds
        else:
            self._clear_brown_rice_specs()
            self.n_moisture_percent = first_line.moisture_percent_max
            self.n_broken_percent = first_line.broken_percent_max
            self.n_damaged_discolor_percent = first_line.damaged_discolor_percent_max
            self.n_foreign_matter_percent = first_line.foreign_matter_percent_max
            self.n_paddy_percent = first_line.paddy_percent_max
            self.n_red_percent = first_line.red_chalky_percent_max

    def _clear_normal_rice_specs(self):
        self.n_moisture_percent = 0.0
        self.n_broken_percent = 0.0
        self.n_damaged_discolor_percent = 0.0
        self.n_foreign_matter_percent = 0.0
        self.n_paddy_percent = False
        self.n_red_percent = 0.0
        self.n_chalky_percent = 0.0
        self.n_immature = 0.0
        self.n_cooking = 0.0
        self.n_insect_damage_grains = 0.0
        self.n_foreign_food_grains = 0.0
        self.n_under_milled_grains = 0.0
        self.n_contrasting_varieties = 0.0
        self.n_living_insects_mites = False
        self.n_polish = False
        self.n_agl = 0.0
        self.n_kett_whiteness = 0.0

    def _clear_brown_rice_specs(self):
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

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.product_id and not rec.process_rice_ids:
                raise UserError(_("Please select a Process Rice product before confirming."))
            if rec.rice_type == IRRI_RICE_TYPE and rec.process_rice_line_ids:
                if any(line.qty_mt <= 0 for line in rec.process_rice_line_ids):
                    raise UserError(_(
                        "Every Process Rice line needs a quantity greater than zero before confirming."))
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def _get_line_qty_map(self) -> Dict[int, float]:
        """Protocol 4.1 (DRY): product id -> planned qty, from the lines.
        Consumers: the BJO handoff (packing lines) and anything per-product."""
        self.ensure_one()
        return {
            line.product_id.id: line.qty_mt
            for line in self.process_rice_line_ids
        }

    def _prepare_job_order_vals(self) -> Dict[str, Any]:
        self.ensure_one()

        bjo_remarks = ""
        if self.remarks:
            bjo_remarks = f"<b>Process Rice Spec Remarks:</b><br/>{self.remarks}<br/><br/><b>Brand Job Order Remarks:</b><br/>"
        else:
            bjo_remarks = "<b>Brand Job Order Remarks:</b><br/>"

        raw_product_ids = self.spec_line_ids.mapped('product_id').ids

        destination_country_id = self.destination_country_id.id
        if not destination_country_id and self.rice_sales_contract_id:
            destination_country_id = self.rice_sales_contract_id.destination_country_id.id

        # Packing lines: one per process rice product, PRS packing config,
        # brands round-robin, PLANNED QTY per product from the PRS lines.
        prs_products = self.process_rice_ids | self.product_id
        prs_brands = self.brand_ids | self.brand_id
        qty_map = self._get_line_qty_map()
        packing_line_commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for brand_index, product in enumerate(prs_products):
            brand_val = prs_brands[brand_index % len(prs_brands)].id if prs_brands else False
            packing_line_commands.append((COMMAND_CREATE_NEW, 0, {
                'product_id': product.id,
                'brand_id': brand_val,
                'process_rice_qty': qty_map.get(product.id, 0.0),
                'packing': self.packing,
                'pp_bag_uom': self.pp_bag_uom,
                'pp_bag_kg': self.pp_bag_kg.id,
                'pp_bag_lb': self.pp_bag_lb,
            }))

        return {
            'process_rice_spec_id': self.id,
            'rice_sales_contract_id': self.rice_sales_contract_id.id,
            'partner_id': self.partner_id.id,
            'product_id': self.product_id.id,
            'process_rice_ids': [(6, 0, self.process_rice_ids.ids)],
            'brand_id': self.brand_id.id,
            'brand_ids': [(6, 0, self.brand_ids.ids)],
            'raw_rice_ids': [(6, 0, raw_product_ids)],
            'quantity_mt': self.total_quantity,
            'process_rice_qty': self.process_rice_qty,
            'packing_line_ids': packing_line_commands,
            'remarks': bjo_remarks,
            'date': fields.Date.today(),
            'rice_type': self.rice_type,
            'broken_percent': self.n_broken_percent,
            'moisture_percent': self.n_moisture_percent,
            'destination_country': destination_country_id,
        }

    def action_create_job_order(self) -> Dict[str, Any]:
        self.ensure_one()
        job_order = self.env['brand.job.order'].create(self._prepare_job_order_vals())
        return self._open_form_view('brand.job.order', job_order.id, 'Brand Job Order')

    def action_view_job_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('brand.job.order', 'process_rice_spec_id', 'Job Order')


class ProcessRiceSpecProductLine(models.Model):
    _name = 'process.rice.spec.product.line'
    _description = 'Process Rice Spec Product Line (per-product planned qty)'
    _order = 'id asc'

    spec_id = fields.Many2one('process.rice.spec', string='Specification', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Process Rice', required=True)
    qty_mt = fields.Float(string='Qty (MT)')

    @api.onchange('product_id')
    def _onchange_product_id_check_duplicate(self) -> None:
        """One line per product: warn when a product is picked twice (the
        product tags collapse duplicates silently otherwise)."""
        if self.product_id and self.spec_id:
            duplicates = self.spec_id.process_rice_line_ids.filtered(
                lambda line: line.product_id == self.product_id and line != self)
            if duplicates:
                warning = {
                    'title': _("Product already selected"),
                    'message': _(
                        "This Process Rice product is already on another line. "
                        "Only one line per product is supported."),
                }
                return {'warning': warning}


class ProcessRiceSpecLine(models.Model):
    _name = 'process.rice.spec.line'
    _description = 'Process Rice Specification Line'

    spec_id = fields.Many2one('process.rice.spec', string='Specification', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Raw Rice')
    crop_year = fields.Many2one('master.crop.year', string='Crop Year',
                                default=lambda self: self.env['master.crop.year'].search([('name', '=', '2026')],
                                                                                         limit=1))
    quantity = fields.Float(string='Quantity (MT)')

    # Quality Specs mapped from RSC
    moisture_percent = fields.Float(string='Moisture (%)')
    broken_percent = fields.Float(string='Broken (%)')
    damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    paddy_percent = fields.Float(string='Paddy (%)')
    red_percent = fields.Float(string='Red (%)')
    chalky_percent = fields.Float(string='Chalky (%)')
    immature = fields.Float(string="Immature")
    cooking = fields.Char(string="Cooking", default="null")

    # Additional Quality Fields
    insect_damage_grains = fields.Float(string='Insect Damage Grains (%)')
    foreign_food_grains = fields.Float(string='Foreign Food Grains (%)')
    under_milled_grains = fields.Float(string='Under-milled Grains (%)')
    contrasting_varieties = fields.Float(string='Contrasting Varieties (%)')
    living_insects_mites = fields.Char(string='Living Insects & Mites')

    # Process Parameters
    polish = fields.Char(string='Polish')
    agl = fields.Float(string='AGL (mm)')
    kett_whiteness = fields.Float(string='KETT Whiteness')


class ProcessRiceSpecAdditionalLine(models.Model):
    _name = 'process.rice.spec.additional.line'
    _description = 'Process Rice Additional Specification Line'

    spec_id = fields.Many2one('process.rice.spec', string='Specification', required=True, ondelete='cascade')
    parameter = fields.Char(string='Parameter Name', required=True)
    value = fields.Char(string='Value')
    uom = fields.Char(string='UoM')


class MasterBagWeight(models.Model):
    _name = 'master.bag.weight'
    _description = 'Master Bag Weight (Kgs)'
    _order = 'weight_kg asc'

    weight_kg = fields.Float(
        string='Weight (Kgs)',
        required=True,
        digits=(16, 2),
    )

    @api.depends('weight_kg')
    def _compute_display_name(self) -> None:
        for rec in self:
            rec.display_name = f"{rec.weight_kg:g} Kg"