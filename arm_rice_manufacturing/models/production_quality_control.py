# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Any, Dict, List, Tuple
import re

from .production_log_sheet import WEEKDAY_KEYS

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


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

    # POINT FIX: Added Many2many field to match XML view error
    bm1_plant_ids = fields.Many2many(
        'master.plant',
        'pqc_bm1_plant_rel',
        'qc_id',
        'plant_id',
        string='BM-1 Plants'
    )

    bm1_plant = fields.Selection([
        ('plant_a', 'Plant A'),
        ('plant_b', 'Plant B'),
        ('plant_c', 'Plant C')
    ], string='BM-1 (legacy)')

    bm2_plant = fields.Selection([
        ('plant_a', 'Plant A')
    ], string='BM-2')

    operator_name = fields.Many2one('operator.name', string='Operator Name')
    brand_name = fields.Char(string='Brand Name')
    brand_id = fields.Many2one(related='job_order_id.brand_id', string='Brand', readonly=True)

    customer_id = fields.Many2one('res.partner', string='Customer Name')
    customer_contract_no = fields.Char(string='Customer Contract No')
    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.')

    date = fields.Date(string='Date', default=fields.Date.today(), required=True)

    day = fields.Selection([
        ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')
    ], string='Day', compute='_compute_day', store=True, readonly=False)

    # Updated Shift Fields (Matching Log Sheet)
    shift = fields.Selection([
        ('8_hours', '8 Hours'),
        ('12_hours', '12 Hours'),
        ('24_hours', '24 Hours'),
    ], string='Shift Hours', default='8_hours')

    shift_type = fields.Selection([
        ('day', 'Day Shift'),
        ('night', 'Night Shift (A+B)'),
        ('general', 'General Shift'),
    ], string='Shift Type', default='day')

    is_brown_rice = fields.Boolean(string='Is Brown Rice', compute='_compute_is_brown_rice', store=True)

    standard_line_ids = fields.One2many('production.qc.standard.line', 'qc_id', string='Standard Specifications')
    qc_line_ids = fields.One2many('production.qc.line', 'qc_id', string='Observed Values')

    shift_supervisor = fields.Char(string='Shift Supervisor')
    production_head = fields.Char(string='Production Head')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    # --- BM1 / BM2 Mutual Exclusivity Logic ---
    @api.onchange('show_bm1')
    def _onchange_show_bm1(self):
        if self.show_bm1:
            self.show_bm2 = False
        else:
            self.bm1_plant_ids = [(5, 0, 0)]
            self.bm1_plant = False

    @api.onchange('show_bm2')
    def _onchange_show_bm2(self):
        if self.show_bm2:
            self.show_bm1 = False
        else:
            self.bm2_plant = False

    @api.depends('job_order_id', 'issue_material_id')
    def _compute_is_brown_rice(self):
        for rec in self:
            is_brown = False
            bjo = rec.issue_material_id.job_order_id if rec.issue_material_id else rec.job_order_id
            if bjo and bjo.process_rice_spec_id:
                is_brown = bjo.process_rice_spec_id.is_brown_rice
            rec.is_brown_rice = is_brown

    @api.depends('date')
    def _compute_day(self) -> None:
        for rec in self:
            rec.day = WEEKDAY_KEYS[rec.date.weekday()] if rec.date else 'monday'

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionQualityControl':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.quality.control.rework' if vals.get(
                    'is_reworking') else 'production.quality.control'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def _spec_text_to_float(self, value: Any) -> float:
        if value is False or value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r'(\d+(?:\.\d+)?)', str(value))
        return float(match.group(1)) if match else 0.0

    def _map_standard_specs_from_bjo(self, bjo: Any) -> None:
        if not bjo:
            self.standard_line_ids = [COMMAND_CLEAR_ALL]
            return

        prs = bjo.process_rice_spec_id
        if prs:
            line_vals = [COMMAND_CLEAR_ALL]
            if prs.is_brown_rice:
                line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': bjo.product_id.id,
                    'is_brown_rice': True,
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
                line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': bjo.product_id.id,
                    'is_brown_rice': False,
                    'moisture_percent': prs.n_moisture_percent,
                    'broken_percent': prs.n_broken_percent,
                    'damaged_discolor_percent': prs.n_damaged_discolor_percent,
                    'foreign_matter_percent': prs.n_foreign_matter_percent,
                    'paddy_percent': self._spec_text_to_float(prs.n_paddy_percent),
                    'red_percent': prs.n_red_percent,
                    'chalky_percent': prs.n_chalky_percent,
                    'under_milled_grains': prs.n_under_milled_grains,
                    'kett_whiteness': prs.n_kett_whiteness,
                }))
            self.standard_line_ids = line_vals

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self) -> None:
        if self.job_order_id:
            self.customer_id = self.job_order_id.partner_id.id
            self.brand_name = (
                    self.job_order_id.brand_id.name
                    or self.job_order_id.brand_ids.mapped('name')[:1]
                    or self.job_order_id.product_id.name
            )
            prs = self.job_order_id.process_rice_spec_id
            self.is_brown_rice = prs.is_brown_rice if prs else False
            self._map_standard_specs_from_bjo(self.job_order_id)
        else:
            self.is_brown_rice = False
            self.brand_name = False
            self.standard_line_ids = [COMMAND_CLEAR_ALL]

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self):
        if not self.issue_material_id:
            return
        im = self.issue_material_id
        self.milling_date = im.milling_date
        if im.job_order_id:
            bjo = im.job_order_id
            self.job_order_id = bjo.id
            self.customer_id = bjo.partner_id.id
            self.brand_name = (
                    bjo.brand_id.name
                    or bjo.brand_ids.mapped('name')[:1]
                    or bjo.product_id.name
            )
            prs = bjo.process_rice_spec_id
            self.is_brown_rice = prs.is_brown_rice if prs else False
            self._map_standard_specs_from_bjo(bjo)

    def action_confirm(self) -> None:
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a Draft QC report can be confirmed. Current state: %s.", rec.state))
            if not rec.job_order_id and not rec.issue_material_id:
                raise UserError(_("Please link a Job Order (or an Issue Material) before confirming."))
            if not rec.qc_line_ids:
                raise UserError(_("Please add at least one Observed Values line before confirming."))
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            if rec.state not in ('draft', 'confirmed'):
                raise UserError(
                    _("Only a Draft or Confirmed QC report can be cancelled. Current state: %s.", rec.state))
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_("Only a Cancelled QC report can be reset to draft. Current state: %s.", rec.state))
            rec.state = 'draft'


class ProductionQCStandardLine(models.Model):
    _name = 'production.qc.standard.line'
    _description = 'Production QC Standard Line (Mimics PRS)'
    qc_id = fields.Many2one('production.quality.control', string='QC', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Process Rice')
    is_brown_rice = fields.Boolean(string='Is Brown Rice')
    moisture_percent = fields.Float(string='Moisture (%)')
    broken_percent = fields.Float(string='Broken (%)')
    damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    paddy_percent = fields.Float(string='Paddy (%)')
    red_percent = fields.Float(string='Red (%)')
    chalky_percent = fields.Float(string='Chalky (%)')
    under_milled_grains = fields.Float(string='Under-milled (%)')
    kett_whiteness = fields.Float(string='KETT Whiteness')
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
    is_brown_rice = fields.Boolean(string='Is Brown Rice')
    moisture_percent = fields.Float(string='Moisture (%)')
    broken_percent = fields.Float(string='Broken (%)')
    damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    paddy_percent = fields.Float(string='Paddy (%)')
    red_percent = fields.Float(string='Red (%)')
    chalky_percent = fields.Float(string='Chalky (%)')
    under_milled_grains = fields.Float(string='Under-milled (%)')
    kett_whiteness = fields.Float(string='KETT Whiteness')
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

# # -*- coding: utf-8 -*-
#
# from odoo import models, fields, api, _
# from odoo.exceptions import UserError
# from typing import Any, Dict, List, Tuple
# import re
#
# from .production_log_sheet import WEEKDAY_KEYS
#
# COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
# COMMAND_CREATE_NEW: int = 0
#
#
# class ProductionQualityControl(models.Model):
#     _name = 'production.quality.control'
#     _description = 'Production Quality Control'
#     _inherit = ['mail.thread', 'mail.activity.mixin']
#     _order = 'id desc'
#
#     name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))
#
#     issue_material_id = fields.Many2one('issue.material', string='Issue Material Ref', ondelete='restrict')
#     milling_date = fields.Date(string='Milling Date')
#
#     show_bm1 = fields.Boolean(string="BM 1", default=True)
#     show_bm2 = fields.Boolean(string="BM 2", default=False)
#
#     bm1_plant = fields.Selection([
#         ('plant_a', 'Plant A'),
#         ('plant_b', 'Plant B'),
#         ('plant_c', 'Plant C')
#     ], string='BM-1')
#
#     bm2_plant = fields.Selection([
#         ('plant_a', 'Plant A')
#     ], string='BM-2')
#
#     operator_name = fields.Many2one('operator.name', string='Operator Name')
#     brand_name = fields.Char(string='Brand Name')
#     brand_id = fields.Many2one(related='job_order_id.brand_id', string='Brand', readonly=True)
#
#     customer_id = fields.Many2one('res.partner', string='Customer Name')
#     customer_contract_no = fields.Char(string='Customer Contract No')
#     job_order_id = fields.Many2one('brand.job.order', string='Job Order No.')
#
#     date = fields.Date(string='Date', default=fields.Date.today(), required=True)
#
#     # Small fix: Day derives from Date (still manually overridable).
#     day = fields.Selection([
#         ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
#         ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')
#     ], string='Day', compute='_compute_day', store=True, readonly=False)
#
#     shift = fields.Selection([
#         ('8_hours', '8 Hours'),
#         ('12_hours', '12 Hours')
#     ], string='Shift', default='8_hours')
#
#     is_brown_rice = fields.Boolean(string='Is Brown Rice', compute='_compute_is_brown_rice', store=True)
#
#     standard_line_ids = fields.One2many('production.qc.standard.line', 'qc_id', string='Standard Specifications')
#     qc_line_ids = fields.One2many('production.qc.line', 'qc_id', string='Observed Values')
#
#     shift_supervisor = fields.Char(string='Shift Supervisor')
#     production_head = fields.Char(string='Production Head')
#     is_reworking = fields.Boolean(string="Reworking", default=False)
#
#     state = fields.Selection([
#         ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
#     ], string='Status', default='draft', tracking=True)
#
#     @api.depends('job_order_id', 'issue_material_id')
#     def _compute_is_brown_rice(self):
#         for rec in self:
#             is_brown = False
#             bjo = rec.issue_material_id.job_order_id if rec.issue_material_id else rec.job_order_id
#             if bjo and bjo.process_rice_spec_id:
#                 is_brown = bjo.process_rice_spec_id.is_brown_rice
#             rec.is_brown_rice = is_brown
#
#     @api.depends('date')
#     def _compute_day(self) -> None:
#         """Small fix: the Day follows the Date."""
#         for rec in self:
#             rec.day = WEEKDAY_KEYS[rec.date.weekday()] if rec.date else 'monday'
#
#     @api.model_create_multi
#     def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionQualityControl':
#         for vals in vals_list:
#             if vals.get('name', _('New')) == _('New'):
#                 seq_code = 'production.quality.control.rework' if vals.get(
#                     'is_reworking') else 'production.quality.control'
#                 vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
#         return super().create(vals_list)
#
#     def _spec_text_to_float(self, value: Any) -> float:
#         """Type bridge: the PRS's Paddy field is a Char ('10 PCS PER KG') while
#         the QC standard line's field is a Float. Extract the leading number;
#         text without a number maps to 0.0."""
#         if value is False or value is None:
#             return 0.0
#         if isinstance(value, (int, float)):
#             return float(value)
#         match = re.search(r'(\d+(?:\.\d+)?)', str(value))
#         return float(match.group(1)) if match else 0.0
#
#     def _map_standard_specs_from_bjo(self, bjo: Any) -> None:
#         """Helper method to populate standard_line_ids from the BJO's PRS."""
#         if not bjo:
#             self.standard_line_ids = [COMMAND_CLEAR_ALL]
#             return
#
#         prs = bjo.process_rice_spec_id
#         if prs:
#             line_vals = [COMMAND_CLEAR_ALL]  # Clear existing
#             if prs.is_brown_rice:
#                 line_vals.append((COMMAND_CREATE_NEW, 0, {
#                     'product_id': bjo.product_id.id,
#                     'is_brown_rice': True,
#                     'br_purity': prs.br_purity,
#                     'br_broken': prs.br_broken,
#                     'br_green_grains': prs.br_green_grains,
#                     'br_chalky_grains': prs.br_chalky_grains,
#                     'br_ddkg': prs.br_ddkg,
#                     'br_immature_grains': prs.br_immature_grains,
#                     'br_paddy_grains': prs.br_paddy_grains,
#                     'br_red_grains': prs.br_red_grains,
#                     'br_other_rices': prs.br_other_rices,
#                     'br_moisture': prs.br_moisture,
#                     'br_avg_length': prs.br_avg_length,
#                     'br_head_yield': prs.br_head_yield,
#                     'br_foreign_matter': prs.br_foreign_matter,
#                     'br_yellow_amber': prs.br_yellow_amber,
#                     'br_foreign_odours': prs.br_foreign_odours,
#                     'br_chemical_residues': prs.br_chemical_residues,
#                     'br_aflatoxinsA': prs.br_aflatoxinsA,
#                     'br_aflatoxins': prs.br_aflatoxins,
#                     'br_living_insects': prs.br_living_insects,
#                     'br_Animals_birds': prs.br_Animals_birds,
#                 }))
#             else:
#                 line_vals.append((COMMAND_CREATE_NEW, 0, {
#                     'product_id': bjo.product_id.id,
#                     'is_brown_rice': False,
#                     'moisture_percent': prs.n_moisture_percent,
#                     'broken_percent': prs.n_broken_percent,
#                     'damaged_discolor_percent': prs.n_damaged_discolor_percent,
#                     'foreign_matter_percent': prs.n_foreign_matter_percent,
#                     'paddy_percent': self._spec_text_to_float(prs.n_paddy_percent),
#                     'red_percent': prs.n_red_percent,
#                     'chalky_percent': prs.n_chalky_percent,
#                     'under_milled_grains': prs.n_under_milled_grains,
#                     'kett_whiteness': prs.n_kett_whiteness,
#                 }))
#             self.standard_line_ids = line_vals
#
#     @api.onchange('show_bm1')
#     def _onchange_show_bm1(self):
#         """Protocol 2.1: Ensure mutual exclusivity."""
#         if self.show_bm1:
#             self.show_bm2 = False
#         else:
#             self.bm1_plant = False
#
#     @api.onchange('show_bm2')
#     def _onchange_show_bm2(self):
#         """Protocol 2.1: Ensure mutual exclusivity."""
#         if self.show_bm2:
#             self.show_bm1 = False
#         else:
#             self.bm2_plant = False
#
#     @api.onchange('job_order_id')
#     def _onchange_job_order_id(self) -> None:
#         if self.job_order_id:
#             self.customer_id = self.job_order_id.partner_id.id
#             # Brand from the master: single brand, else the first of the
#             # multi-brands, else fall back to the product name (legacy jobs).
#             self.brand_name = (
#                 self.job_order_id.brand_id.name
#                 or self.job_order_id.brand_ids.mapped('name')[:1]
#                 or self.job_order_id.product_id.name
#             )
#             prs = self.job_order_id.process_rice_spec_id
#             self.is_brown_rice = prs.is_brown_rice if prs else False
#             self._map_standard_specs_from_bjo(self.job_order_id)
#         else:
#             self.is_brown_rice = False
#             self.brand_name = False
#             self.standard_line_ids = [COMMAND_CLEAR_ALL]
#
#     @api.onchange('issue_material_id')
#     def _onchange_issue_material_id(self):
#         if not self.issue_material_id:
#             return
#         im = self.issue_material_id
#         self.milling_date = im.milling_date
#         if im.job_order_id:
#             bjo = im.job_order_id
#             self.job_order_id = bjo.id
#             self.customer_id = bjo.partner_id.id
#             # Brand from the master (same fallback chain as the job order path).
#             self.brand_name = (
#                 bjo.brand_id.name
#                 or bjo.brand_ids.mapped('name')[:1]
#                 or bjo.product_id.name
#             )
#             prs = bjo.process_rice_spec_id
#             self.is_brown_rice = prs.is_brown_rice if prs else False
#             self._map_standard_specs_from_bjo(bjo)
#     # ==========================================================
#     # FINDING 4 + 6: the QC twin gets the same guardrails
#     # ==========================================================
#
#     def action_confirm(self) -> None:
#         for rec in self:
#             if rec.state != 'draft':
#                 raise UserError(_("Only a Draft QC report can be confirmed. Current state: %s.", rec.state))
#             if not rec.job_order_id and not rec.issue_material_id:
#                 raise UserError(_("Please link a Job Order (or an Issue Material) before confirming."))
#             if not rec.qc_line_ids:
#                 raise UserError(_("Please add at least one Observed Values line before confirming."))
#             rec.state = 'confirmed'
#
#     def action_cancel(self) -> None:
#         for rec in self:
#             if rec.state not in ('draft', 'confirmed'):
#                 raise UserError(_("Only a Draft or Confirmed QC report can be cancelled. Current state: %s.", rec.state))
#             rec.state = 'cancel'
#
#     def action_reset_to_draft(self) -> None:
#         for rec in self:
#             if rec.state != 'cancel':
#                 raise UserError(_("Only a Cancelled QC report can be reset to draft. Current state: %s.", rec.state))
#             rec.state = 'draft'
#
#
# class ProductionQCStandardLine(models.Model):
#     _name = 'production.qc.standard.line'
#     _description = 'Production QC Standard Line (Mimics PRS)'
#
#     qc_id = fields.Many2one('production.quality.control', string='QC', required=True, ondelete='cascade')
#     product_id = fields.Many2one('product.product', string='Process Rice')
#
#     # Local boolean on the line model to drive UI visibility reliably
#     is_brown_rice = fields.Boolean(string='Is Brown Rice')
#
#     # Normal Rice Fields
#     moisture_percent = fields.Float(string='Moisture (%)')
#     broken_percent = fields.Float(string='Broken (%)')
#     damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
#     foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
#     paddy_percent = fields.Float(string='Paddy (%)')
#     red_percent = fields.Float(string='Red (%)')
#     chalky_percent = fields.Float(string='Chalky (%)')
#     under_milled_grains = fields.Float(string='Under-milled (%)')
#     kett_whiteness = fields.Float(string='KETT Whiteness')
#
#     # Brown Rice Fields (All 20)
#     br_purity = fields.Float(string='Purity')
#     br_broken = fields.Float(string='Broken')
#     br_green_grains = fields.Float(string='Green grains')
#     br_chalky_grains = fields.Float(string='Chalky grains')
#     br_ddkg = fields.Float(string='Discoloured/Damaged Kernels')
#     br_immature_grains = fields.Float(string='Immature Grains')
#     br_paddy_grains = fields.Float(string='Paddy grains')
#     br_red_grains = fields.Float(string='Red grains')
#     br_other_rices = fields.Float(string='Other Rices')
#     br_moisture = fields.Float(string='Moisture')
#     br_avg_length = fields.Float(string='Avg. Length')
#     br_head_yield = fields.Float(string='Head Yield')
#     br_foreign_matter = fields.Float(string='Foreign Matters')
#     br_yellow_amber = fields.Float(string='Yellow/Amber Kernels')
#     br_foreign_odours = fields.Float(string='Foreign odours/smell')
#     br_chemical_residues = fields.Float(string='Chemical Residues')
#     br_aflatoxinsA = fields.Float(string='Aflatoxins B1')
#     br_aflatoxins = fields.Float(string='Aflatoxins Total')
#     br_living_insects = fields.Float(string='Insects Live/Dead')
#     br_Animals_birds = fields.Float(string='Animals/Birds')
#
#
# class ProductionQCLine(models.Model):
#     _name = 'production.qc.line'
#     _description = 'Production QC Observed Line (Mimics PRS)'
#     _order = 'id asc'
#
#     qc_id = fields.Many2one('production.quality.control', string='QC', required=True, ondelete='cascade')
#     name = fields.Char(string='Hours / Type')
#     product_id = fields.Many2one('product.product', string='Raw / Process Rice')
#
#     # Local boolean on the line model to drive UI visibility reliably
#     is_brown_rice = fields.Boolean(string='Is Brown Rice')
#
#     # Normal Rice Fields
#     moisture_percent = fields.Float(string='Moisture (%)')
#     broken_percent = fields.Float(string='Broken (%)')
#     damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
#     foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
#     paddy_percent = fields.Float(string='Paddy (%)')
#     red_percent = fields.Float(string='Red (%)')
#     chalky_percent = fields.Float(string='Chalky (%)')
#     under_milled_grains = fields.Float(string='Under-milled (%)')
#     kett_whiteness = fields.Float(string='KETT Whiteness')
#
#     # Brown Rice Fields (All 20)
#     br_purity = fields.Float(string='Purity')
#     br_broken = fields.Float(string='Broken')
#     br_green_grains = fields.Float(string='Green grains')
#     br_chalky_grains = fields.Float(string='Chalky grains')
#     br_ddkg = fields.Float(string='Discoloured/Damaged Kernels')
#     br_immature_grains = fields.Float(string='Immature Grains')
#     br_paddy_grains = fields.Float(string='Paddy grains')
#     br_red_grains = fields.Float(string='Red grains')
#     br_other_rices = fields.Float(string='Other Rices')
#     br_moisture = fields.Float(string='Moisture')
#     br_avg_length = fields.Float(string='Avg. Length')
#     br_head_yield = fields.Float(string='Head Yield')
#     br_foreign_matter = fields.Float(string='Foreign Matters')
#     br_yellow_amber = fields.Float(string='Yellow/Amber Kernels')
#     br_foreign_odours = fields.Float(string='Foreign odours/smell')
#     br_chemical_residues = fields.Float(string='Chemical Residues')
#     br_aflatoxinsA = fields.Float(string='Aflatoxins B1')
#     br_aflatoxins = fields.Float(string='Aflatoxins Total')
#     br_living_insects = fields.Float(string='Insects Live/Dead')
#     br_Animals_birds = fields.Float(string='Animals/Birds')
