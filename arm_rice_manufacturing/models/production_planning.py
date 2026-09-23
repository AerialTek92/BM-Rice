# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List


class ProductionPlanning(models.Model):
    _name = 'production.planning'
    _description = 'Production Planning Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))

    # FIX: Removed compute from here. Date is a normal Date field.
    # Its format will be handled by XML options.
    date = fields.Date(string='Date', default=fields.Date.today(), required=True)

    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True, ondelete='restrict')

    # Mapped Fields
    commodity = fields.Char(string='Commodity')
    rice_variety = fields.Char(string='Rice Variety')
    customer_id = fields.Many2one('res.partner', string='Customer Name')

    # ==========================================
    # NEW: Milling Date Range (Client Requirement)
    # From 25 Apr 2026 to 30 Mar 2027 wala concept
    # ==========================================
    milling_date_from = fields.Date(string='Milling Date From', required=True)
    milling_date_to = fields.Date(string='Milling Date To')

    # Display field — form/list/report par default format mein dikhega
    milling_date = fields.Char(
        string='Milling Date',
        compute='_compute_milling_date',
        store=True,
    )

    brand = fields.Char(string='Brand')

    # Quality Parameters
    planning_line_ids = fields.One2many('production.planning.line', 'planning_id', string='Parameters')

    # Packing Details
    no_of_bags = fields.Integer(string='No of Bags')
    packing_material = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('bo_pp_bags', 'BO PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('china_cotton', 'China Cotton')
    ], string='Packing (Material)')

    # Integer GRAMS, matching the label. Historical kg values are scaled
    # by the 19.0.1.0.1 pre-migration; the BJO mapping now passes its
    # (already-gram) total straight through - no conversion anywhere.
    empty_bag_weight = fields.Integer(string='Empty Bag Weight (Grams)')

    total_quantity = fields.Float(string='Total Quantity (MT)')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed')
    ], string='Status', default='draft', tracking=True)

    remarks = fields.Html(string='Remarks')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionPlanning':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('production.planning') or _('New')
        return super().create(vals_list)

    # ==========================================
    # FIX: Milling Date Range Display + Validation (Default Format Restored)
    # ==========================================
    @api.depends('milling_date_from', 'milling_date_to')
    def _compute_milling_date(self) -> None:
        # FIX: Reverted back to default format '%d %b %Y' (e.g., 03 Sep 2026)
        date_format = '%d %b %Y'
        for rec in self:
            frm = rec.milling_date_from
            to = rec.milling_date_to
            if frm and to:
                if frm == to:
                    rec.milling_date = frm.strftime(date_format)
                else:
                    rec.milling_date = f"{frm.strftime(date_format)} to {to.strftime(date_format)}"
            elif frm:
                rec.milling_date = frm.strftime(date_format)
            elif to:
                rec.milling_date = to.strftime(date_format)
            else:
                rec.milling_date = False

    @api.constrains('milling_date_from', 'milling_date_to')
    def _check_milling_date_range(self) -> None:
        date_format = '%d %b %Y'
        for rec in self:
            if rec.milling_date_from and rec.milling_date_to \
                    and rec.milling_date_to < rec.milling_date_from:
                raise UserError(_(
                    "Milling Date 'To' (%s) cannot be earlier than 'From' (%s)."
                ) % (
                                    rec.milling_date_to.strftime(date_format),
                                    rec.milling_date_from.strftime(date_format),
                                ))

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self):
        """Flow Fix: Auto-populate header and parameter lines from BJO."""
        if not self.job_order_id:
            return

        bjo = self.job_order_id
        prs = bjo.process_rice_spec_id

        self.commodity = bjo.product_id.name
        self.rice_variety = bjo.product_id.name
        self.customer_id = bjo.partner_id.id
        self.brand = bjo.product_id.name

        self.no_of_bags = bjo.no_of_bags
        self.packing_material = bjo.packing

        # BJO's total is already in grams: pass it straight through.
        if bjo.total_empty_bag_weight:
            self.empty_bag_weight = bjo.total_empty_bag_weight

        self.total_quantity = bjo.quantity_mt

        # Populate Quality Parameters Table
        self.planning_line_ids = [(5, 0, 0)]
        if prs:
            if prs.is_brown_rice:
                params = [
                    ('Purity', '%', prs.br_purity),
                    ('Broken', '%', prs.br_broken),
                    ('Green grains', '%', prs.br_green_grains),
                    ('Chalky grains', '%', prs.br_chalky_grains),
                    ('Discoloured/Damaged Kernels', '%', prs.br_ddkg),
                    ('Immature Grains', '%', prs.br_immature_grains),
                    ('Paddy grains', '%', prs.br_paddy_grains),
                    ('Red grains', '%', prs.br_red_grains),
                    ('Other Rices', '%', prs.br_other_rices),
                    ('Moisture', '%', prs.br_moisture),
                    ('Avg. Length', 'mm', prs.br_avg_length),
                    ('Head Yield', '%', prs.br_head_yield),
                    ('Foreign Matters', '%', prs.br_foreign_matter),
                    ('Yellow/Amber Kernels', '%', prs.br_yellow_amber),
                    ('Foreign odours/smell', '%', prs.br_foreign_odours),
                    ('Chemical Residues', '-', prs.br_chemical_residues),
                    ('Aflatoxins B1', '-', prs.br_aflatoxinsA),
                    ('Aflatoxins Total', '-', prs.br_aflatoxins),
                    ('Insects Live/Dead', '-', prs.br_living_insects),
                    ('Animals/Birds', '-', prs.br_Animals_birds),
                ]
            else:
                params = [
                    ('Moisture', '%age', prs.n_moisture_percent),
                    ('Broken', '%age', prs.n_broken_percent),
                    ('Damaged / Yellow grains', '%age', prs.n_damaged_discolor_percent),
                    ('Red / Chalky grains', '%age', prs.n_red_percent),
                    ('Foreign Food Grains', '%age', prs.n_foreign_food_grains),
                    ('Foreign Matter', '%age', prs.n_foreign_matter_percent),
                    ('Paddy grains', 'grains/kg', prs.n_paddy_percent),
                    ('Under milled / red stripped', '%age', prs.n_under_milled_grains),
                    ('Polish Grade', '-', prs.n_polish),
                    ('Polish (Whiteness)', 'Kett', prs.n_kett_whiteness),
                ]

            lines = []
            for i, (param, uom, val) in enumerate(params, start=1):
                lines.append((0, 0, {
                    'sequence': i,
                    'parameter': param,
                    'uom': uom,
                    'value': val,
                }))
            self.planning_line_ids = lines

    def action_confirm(self) -> None:
        for rec in self:
            rec.state = 'confirmed'

    def action_create_issue_material(self) -> Dict[str, Any]:
        self.ensure_one()
        self.state = 'confirmed'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Material',
            'res_model': 'issue.material',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.job_order_id.id,
                'default_issue_date': fields.Date.today(),
                'default_milling_date': self.milling_date_from,
            }
        }

    def action_create_production_record(self) -> Dict[str, Any]:
        self.ensure_one()
        self.state = 'confirmed'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Record',
            'res_model': 'production.record',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.job_order_id.id,
                'default_production_date': fields.Date.today(),
            }
        }


class ProductionPlanningLine(models.Model):
    _name = 'production.planning.line'
    _description = 'Production Planning Parameter Line'

    planning_id = fields.Many2one('production.planning', string='Planning', required=True, ondelete='cascade')
    sequence = fields.Integer(string='S.No.')
    parameter = fields.Char(string='Parameters')
    uom = fields.Char(string='UoM')
    value = fields.Char(string='Values in Job Order')