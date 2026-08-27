# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from typing import Dict, Any, List


class ProductionQualityControl(models.Model):
    _name = 'production.quality.control'
    _description = 'Production Quality Control'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))

    issue_material_id = fields.Many2one('issue.material', string='Issue Material Ref', ondelete='restrict')
    milling_date = fields.Date(string='Milling Date')

    show_bm1 = fields.Boolean(string="BM 1", default=True)
    show_bm2 = fields.Boolean(string="BM 2", default=False)

    bm1_plant = fields.Selection([
        ('plant_a', 'Plant A'),
        ('plant_b', 'Plant B'),
        ('plant_c', 'Plant C')
    ], string='BM-1')

    bm2_plant = fields.Selection([
        ('plant_a', 'Plant A')
    ], string='BM-2')

    operator_name = fields.Many2one('operator.name', string='Operator Name')
    brand_name = fields.Char(string='Brand Name')

    customer_id = fields.Many2one('res.partner', string='Customer Name')
    customer_contract_no = fields.Char(string='Customer Contract No')
    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.')

    date = fields.Date(string='Date', default=fields.Date.today(), required=True)
    day = fields.Selection([
        ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')
    ], string='Day', default='monday')

    shift = fields.Selection([
        ('8_hours', '8 Hours'),
        ('12_hours', '12 Hours')
    ], string='Shift', default='8_hours')

    is_brown_rice = fields.Boolean(string='Is Brown Rice', compute='_compute_is_brown_rice', store=True)

    standard_line_ids = fields.One2many('production.qc.standard.line', 'qc_id', string='Standard Specifications')
    qc_line_ids = fields.One2many('production.qc.line', 'qc_id', string='Observed Values')

    shift_supervisor = fields.Char(string='Shift Supervisor')
    production_head = fields.Char(string='Production Head')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.depends('job_order_id', 'issue_material_id')
    def _compute_is_brown_rice(self):
        for rec in self:
            is_brown = False
            bjo = rec.issue_material_id.job_order_id if rec.issue_material_id else rec.job_order_id
            if bjo and bjo.process_rice_spec_id:
                is_brown = bjo.process_rice_spec_id.is_brown_rice
            rec.is_brown_rice = is_brown

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionQualityControl':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.quality.control.rework' if vals.get(
                    'is_reworking') else 'production.quality.control'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def _map_standard_specs_from_bjo(self, bjo: Any) -> None:
        """Helper method to populate standard_line_ids from the BJO's PRS."""
        if not bjo:
            self.standard_line_ids = [(5, 0, 0)]
            return

        prs = bjo.process_rice_spec_id
        if prs:
            line_vals = [(5, 0, 0)]  # Clear existing
            if prs.is_brown_rice:
                line_vals.append((0, 0, {
                    'product_id': bjo.product_id.id,
                    'is_brown_rice': True,  # FIX: Pass is_brown_rice to the line
                    'br_purity': prs.br_purity,
                    'br_broken': prs.br_broken,
                    'br_green_grains': prs.br_green_grains,
                    'br_chalky_grains': prs.br_chalky_grains,
                    'br_ddkg': prs.br_ddkg,
                    'br_immature_grains': prs.br_immature_grains,
                    'br_paddy_grains': prs.br_paddy_grains,
                    'br_red_grains': prs.br_red_grains,
                    'br_other_rices': prs.br_other_rices,
                    'br_moisture': prs.br_moisture,
                    'br_avg_length': prs.br_avg_length,
                    'br_head_yield': prs.br_head_yield,
                    'br_foreign_matter': prs.br_foreign_matter,
                    'br_yellow_amber': prs.br_yellow_amber,
                    'br_foreign_odours': prs.br_foreign_odours,
                    'br_chemical_residues': prs.br_chemical_residues,
                    'br_aflatoxinsA': prs.br_aflatoxinsA,
                    'br_aflatoxins': prs.br_aflatoxins,
                    'br_living_insects': prs.br_living_insects,
                    'br_Animals_birds': prs.br_Animals_birds,
                }))
            else:
                line_vals.append((0, 0, {
                    'product_id': bjo.product_id.id,
                    'is_brown_rice': False,  # FIX: Pass is_brown_rice to the line
                    'moisture_percent': prs.n_moisture_percent,
                    'broken_percent': prs.n_broken_percent,
                    'damaged_discolor_percent': prs.n_damaged_discolor_percent,
                    'foreign_matter_percent': prs.n_foreign_matter_percent,
                    'paddy_percent': prs.n_paddy_percent,
                    'red_percent': prs.n_red_percent,
                    'chalky_percent': prs.n_chalky_percent,
                    'under_milled_grains': prs.n_under_milled_grains,
                    'kett_whiteness': prs.n_kett_whiteness,
                }))
            self.standard_line_ids = line_vals

    @api.onchange('show_bm1')
    def _onchange_show_bm1(self):
        """Protocol 2.1: Ensure mutual exclusivity."""
        if self.show_bm1:
            self.show_bm2 = False
        else:
            self.bm1_plant = False

    @api.onchange('show_bm2')
    def _onchange_show_bm2(self):
        """Protocol 2.1: Ensure mutual exclusivity."""
        if self.show_bm2:
            self.show_bm1 = False
        else:
            self.bm2_plant = False

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self) -> None:
        if self.job_order_id:
            self.customer_id = self.job_order_id.partner_id.id
            self.brand_name = self.job_order_id.product_id.name
            prs = self.job_order_id.process_rice_spec_id
            self.is_brown_rice = prs.is_brown_rice if prs else False
            self._map_standard_specs_from_bjo(self.job_order_id)
        else:
            self.is_brown_rice = False
            self.standard_line_ids = [(5, 0, 0)]

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self):
        if not self.issue_material_id:
            return
        im = self.issue_material_id
        self.milling_date = im.milling_date
        if im.job_order_id:
            self.job_order_id = im.job_order_id.id
            self.customer_id = im.job_order_id.partner_id.id
            self.brand_name = im.job_order_id.product_id.name
            prs = im.job_order_id.process_rice_spec_id
            self.is_brown_rice = prs.is_brown_rice if prs else False
            self._map_standard_specs_from_bjo(im.job_order_id)

    def action_confirm(self) -> None:
        for rec in self:
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'


class ProductionQCStandardLine(models.Model):
    _name = 'production.qc.standard.line'
    _description = 'Production QC Standard Line (Mimics PRS)'

    qc_id = fields.Many2one('production.quality.control', string='QC', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Raw / Process Rice')
    
    # NEW: Local boolean on the line model to drive UI visibility reliably
    is_brown_rice = fields.Boolean(string='Is Brown Rice')
    
    # Normal Rice Fields
    moisture_percent = fields.Float(string='Moisture (%)')
    broken_percent = fields.Float(string='Broken (%)')
    damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    paddy_percent = fields.Float(string='Paddy (%)')
    red_percent = fields.Float(string='Red (%)')
    chalky_percent = fields.Float(string='Chalky (%)')
    under_milled_grains = fields.Float(string='Under-milled (%)')
    kett_whiteness = fields.Float(string='KETT Whiteness')

    # Brown Rice Fields (All 20)
    br_purity = fields.Float(string='Purity')
    br_broken = fields.Float(string='Broken')
    br_green_grains = fields.Float(string='Green grains')
    br_chalky_grains = fields.Float(string='Chalky grains')
    br_ddkg = fields.Float(string='Discoloured/Damaged Kernels')
    br_immature_grains = fields.Float(string='Immature Grains')
    br_paddy_grains = fields.Float(string='Paddy grains')
    br_red_grains = fields.Float(string='Red grains')
    br_other_rices = fields.Float(string='Other Rices')
    br_moisture = fields.Float(string='Moisture')
    br_avg_length = fields.Float(string='Avg. Length')
    br_head_yield = fields.Float(string='Head Yield')
    br_foreign_matter = fields.Float(string='Foreign Matters')
    br_yellow_amber = fields.Float(string='Yellow/Amber Kernels')
    br_foreign_odours = fields.Float(string='Foreign odours/smell')
    br_chemical_residues = fields.Float(string='Chemical Residues')
    br_aflatoxinsA = fields.Float(string='Aflatoxins B1')
    br_aflatoxins = fields.Float(string='Aflatoxins Total')
    br_living_insects = fields.Float(string='Insects Live/Dead')
    br_Animals_birds = fields.Float(string='Animals/Birds')


class ProductionQCLine(models.Model):
    _name = 'production.qc.line'
    _description = 'Production QC Observed Line (Mimics PRS)'
    _order = 'id asc'

    qc_id = fields.Many2one('production.quality.control', string='QC', required=True, ondelete='cascade')
    name = fields.Char(string='Hours / Type')
    product_id = fields.Many2one('product.product', string='Raw / Process Rice')
    
    # NEW: Local boolean on the line model to drive UI visibility reliably
    is_brown_rice = fields.Boolean(string='Is Brown Rice')
    
    # Normal Rice Fields
    moisture_percent = fields.Float(string='Moisture (%)')
    broken_percent = fields.Float(string='Broken (%)')
    damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    paddy_percent = fields.Float(string='Paddy (%)')
    red_percent = fields.Float(string='Red (%)')
    chalky_percent = fields.Float(string='Chalky (%)')
    under_milled_grains = fields.Float(string='Under-milled (%)')
    kett_whiteness = fields.Float(string='KETT Whiteness')

    # Brown Rice Fields (All 20)
    br_purity = fields.Float(string='Purity')
    br_broken = fields.Float(string='Broken')
    br_green_grains = fields.Float(string='Green grains')
    br_chalky_grains = fields.Float(string='Chalky grains')
    br_ddkg = fields.Float(string='Discoloured/Damaged Kernels')
    br_immature_grains = fields.Float(string='Immature Grains')
    br_paddy_grains = fields.Float(string='Paddy grains')
    br_red_grains = fields.Float(string='Red grains')
    br_other_rices = fields.Float(string='Other Rices')
    br_moisture = fields.Float(string='Moisture')
    br_avg_length = fields.Float(string='Avg. Length')
    br_head_yield = fields.Float(string='Head Yield')
    br_foreign_matter = fields.Float(string='Foreign Matters')
    br_yellow_amber = fields.Float(string='Yellow/Amber Kernels')
    br_foreign_odours = fields.Float(string='Foreign odours/smell')
    br_chemical_residues = fields.Float(string='Chemical Residues')
    br_aflatoxinsA = fields.Float(string='Aflatoxins B1')
    br_aflatoxins = fields.Float(string='Aflatoxins Total')
    br_living_insects = fields.Float(string='Insects Live/Dead')
    br_Animals_birds = fields.Float(string='Animals/Birds') 