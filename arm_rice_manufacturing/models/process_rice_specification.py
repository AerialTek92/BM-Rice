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

    rice_type = fields.Selection([
        ('irri', 'IRRI'),
        ('basmati', 'Basmati')
    ], string='Rice Type', default='irri', required=True, tracking=True)

    product_id = fields.Many2one('product.product', string='Process Rice')
    process_rice_qty = fields.Float(string='Process Rice QTY')

    total_quantity = fields.Float(
        string='Total Quantity (MT)',
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
        string='No of Bags',
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
    ], string='Packing')

    # --- NEW: Packing Weight with UoM Logic ---
    pp_bag_uom = fields.Selection([
        ('kg', 'Kgs'),
        ('lb', 'Lbs')
    ], string='Unit of Measure', default='kg', required=True)

    pp_bag_kg = fields.Selection([
        ('5', '5 Kg'),
        ('20', '20 Kg'),
        ('22.5', '22.5 Kg'),
        ('25', '25 Kg'),
        ('50', '50 Kg')
    ], string='Weight (Kgs)')

    pp_bag_lb = fields.Float(string='Weight (Lbs)')

    # pp_bags = fields.Selection([
    #     ('5 kg', '5 Kg'),
    #     ('20 kg', '20 Kg'),
    #     ('22.5 kg', '22.5 Kg'),
    #     ('25 kg', '25 Kg'),
    #     ('50 kg', '50 Kg'),
    # ])
    remarks = fields.Html(string='Remarks')

    spec_line_ids = fields.One2many('process.rice.spec.line', 'spec_id', string='Specification Lines')

    # NEW: Additional Manual Specifications
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
    n_paddy_percent = fields.Float(string='Paddy (%)')
    n_red_percent = fields.Float(string='Red (%)')
    n_chalky_percent = fields.Float(string='Chalky (%)')
    n_immature = fields.Float(string="Immature")
    n_cooking = fields.Float(string="Cooking")
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
    br_chemical_residues = fields.Float(string="Chemical Residues and Radioactivity")
    br_aflatoxinsA = fields.Float(string="Aflatoxins B1")
    br_aflatoxins = fields.Float(string='Aflatoxins B1+B2+G1+G2')
    br_living_insects = fields.Float(string='Insects Live/Dead')
    br_Animals_birds = fields.Float(string='Animals Birds')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProcessRiceSpec':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('process.rice.spec') or _('New')
        return super().create(vals_list)

    def _compute_job_order_count(self) -> None:
        for rec in self:
            rec.job_order_count = rec._get_related_record_count('brand.job.order', 'process_rice_spec_id')

    @api.depends('spec_line_ids.quantity')
    def _compute_total_quantity(self) -> None:
        for rec in self:
            rec.total_quantity = sum(rec.spec_line_ids.mapped('quantity'))

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

    @api.onchange('rice_sales_contract_id')
    def _onchange_rice_sales_contract_id(self):
        """Fetch product and specifications directly from Sales Contract Reference."""
        if not self.rice_sales_contract_id:
            self.update({
                'partner_id': False,
                'product_id': False,
                'is_brown_rice': False,
                'process_rice_qty': 0.0,
            })
            self._clear_normal_rice_specs()
            self._clear_brown_rice_specs()
            return

        contract = self.rice_sales_contract_id
        first_line = contract.contract_line_ids[:1]

        if not first_line:
            self.product_id = False
            self.is_brown_rice = False
            return

        self.update({
            'partner_id': contract.partner_id.id,
            'product_id': first_line.product_id.id,
            'is_brown_rice': first_line.is_brown_rice,
            'process_rice_qty': contract.total_quantity,
        })

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
        self.n_paddy_percent = 0.0
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
            if not rec.product_id:
                raise UserError(_("Please select a Process Rice product before confirming."))
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def _prepare_job_order_vals(self) -> Dict[str, Any]:
        self.ensure_one()

        bjo_remarks = ""
        if self.remarks:
            bjo_remarks = f"<b>Process Rice Spec Remarks:</b><br/>{self.remarks}<br/><br/><b>Brand Job Order Remarks:</b><br/>"
        else:
            bjo_remarks = "<b>Brand Job Order Remarks:</b><br/>"

        raw_product_ids = self.spec_line_ids.mapped('product_id').ids

        # FIX: PRS uses Selection for pp_bags_kgs, but BJO uses Float. Convert safely.
        pp_bags_kgs_val = 0.0
        if self.pp_bag_uom == 'kg' and self.pp_bag_kg:
            try:
                pp_bags_kgs_val = float(self.pp_bag_kg)
            except ValueError:
                pp_bags_kgs_val = 0.0
        elif self.pp_bag_uom == 'lb' and self.pp_bag_lb:
            pp_bags_kgs_val = self.pp_bag_lb

        return {
            'process_rice_spec_id': self.id,
            'rice_sales_contract_id': self.rice_sales_contract_id.id,
            'partner_id': self.partner_id.id,
            'product_id': self.product_id.id,
            'raw_rice_ids': [(6, 0, raw_product_ids)],
            'quantity_mt': self.total_quantity,
            'packing': self.packing,
            'pp_bags_kgs': pp_bags_kgs_val,  # Pass the parsed float value
            'process_rice_qty': self.process_rice_qty,
            'remarks': bjo_remarks,
            'date': fields.Date.today(),
            'rice_type': self.rice_type,
            'broken_percent': self.n_broken_percent,  # Fixed: Read from header
            'moisture_percent': self.n_moisture_percent,  # Fixed: Read from header
        }

    def action_create_job_order(self) -> Dict[str, Any]:
        self.ensure_one()
        job_order = self.env['brand.job.order'].create(self._prepare_job_order_vals())
        return self._open_form_view('brand.job.order', job_order.id, 'Brand Job Order')

    def action_view_job_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('brand.job.order', 'process_rice_spec_id', 'Job Order')


class ProcessRiceSpecLine(models.Model):
    _name = 'process.rice.spec.line'
    _description = 'Process Rice Specification Line'

    spec_id = fields.Many2one('process.rice.spec', string='Specification', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Raw / Process Rice')
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
    cooking = fields.Float(string="Cooking")

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


# ==========================================
# NEW MODEL FOR ADDITIONAL MANUAL SPECIFICATIONS
# ==========================================
class ProcessRiceSpecAdditionalLine(models.Model):
    _name = 'process.rice.spec.additional.line'
    _description = 'Process Rice Additional Specification Line'

    spec_id = fields.Many2one('process.rice.spec', string='Specification', required=True, ondelete='cascade')
    parameter = fields.Char(string='Parameter Name', required=True)
    value = fields.Char(string='Value')
    uom = fields.Char(string='UoM')