# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Searchable Constants (Protocol 1.3) ---
PLANT_A: str = 'plant_a'
PLANT_B: str = 'plant_b'
PLANT_C: str = 'plant_c'


class PlanningSchedule(models.Model):
    _name = 'planning.schedule'
    _description = 'Planning Schedule / Calendar'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Schedule Date', default=fields.Date.today(), required=True)

    # Summary Fields (Protocol 2.1 SRP)
    total_plant_a_input = fields.Float(string='Plant A Input', compute='_compute_totals', store=True)
    total_plant_a_output = fields.Float(string='Plant A Output', compute='_compute_totals', store=True)
    total_plant_b_input = fields.Float(string='Plant B Input', compute='_compute_totals', store=True)
    total_plant_b_output = fields.Float(string='Plant B Output', compute='_compute_totals', store=True)
    total_plant_c_input = fields.Float(string='Plant C Input', compute='_compute_totals', store=True)
    total_plant_c_output = fields.Float(string='Plant C Output', compute='_compute_totals', store=True)

    line_ids = fields.One2many('planning.schedule.line', 'schedule_id', string='Schedule Lines')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'PlanningSchedule':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('planning.schedule') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.input_qty', 'line_ids.output_qty', 'line_ids.plant')
    def _compute_totals(self) -> None:
        """Protocol 2.1 (SRP): Compute plant capacities based on lines."""
        for rec in self:
            plant_a_lines = rec.line_ids.filtered(lambda l: l.plant == PLANT_A)
            plant_b_lines = rec.line_ids.filtered(lambda l: l.plant == PLANT_B)
            plant_c_lines = rec.line_ids.filtered(lambda l: l.plant == PLANT_C)

            rec.total_plant_a_input = sum(plant_a_lines.mapped('input_qty'))
            rec.total_plant_a_output = sum(plant_a_lines.mapped('output_qty'))
            rec.total_plant_b_input = sum(plant_b_lines.mapped('input_qty'))
            rec.total_plant_b_output = sum(plant_b_lines.mapped('output_qty'))
            rec.total_plant_c_input = sum(plant_c_lines.mapped('input_qty'))
            rec.total_plant_c_output = sum(plant_c_lines.mapped('output_qty'))

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Please add at least one Job Order to the schedule before confirming."))
            rec.state = 'confirmed'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def action_open_issue_materials(self) -> Dict[str, Any]:
        """Protocol 2.1 (SRP): Navigate to Issue Materials for the BJOs in this schedule."""
        self.ensure_one()
        bjo_ids = self.line_ids.mapped('job_order_id.id')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Materials',
            'res_model': 'issue.material',
            'view_mode': 'list,form',
            'domain': [('job_order_id', 'in', bjo_ids)],
            'context': {'default_job_order_id': bjo_ids[0] if bjo_ids else False}
        }


class PlanningScheduleLine(models.Model):
    _name = 'planning.schedule.line'
    _description = 'Planning Schedule Line'
    _order = 'plant, sequence'

    schedule_id = fields.Many2one('planning.schedule', string='Schedule', required=True, ondelete='cascade')
    sequence = fields.Integer(string='S.No', default=10)

    # FIX: Changed to Plant A, B, C
    plant = fields.Selection([
        (PLANT_A, 'Plant A'),
        (PLANT_B, 'Plant B'),
        (PLANT_C, 'Plant C')
    ], string='Plant', required=True, default=PLANT_A)

    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True, ondelete='restrict')

    # Mapped Fields (Protocol 4.1 DRY - Fetching from BJO)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True, store=True)
    product_id = fields.Many2one('product.product', string='Finished Rice', readonly=True, store=True)
    input_qty = fields.Float(string='Input (M.Ton)', readonly=True)
    output_qty = fields.Float(string='Output (M.Ton)', readonly=True)
    efficiency = fields.Float(string='Efficiency (%)', readonly=True)
    bags = fields.Integer(string='Bags', readonly=True)

    # NEW: User Input Fields
    stock_packed = fields.Float(string='Stock Packed')
    stock_to_be_packed = fields.Float(string='Stock to be Packed')
    final_rice_mt_hr = fields.Float(string='Final Rice (MT/hr)')

    # Production Time & Dates
    prod_hours = fields.Float(string='Hours')
    prod_days = fields.Float(string='Days')
    prod_shift = fields.Selection([
        ('8_hours', '8 Hours'),
        ('12_hours', '12 Hours')
    ], string='Shift')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')

    remarks = fields.Char(string='Remarks')

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self) -> None:
        """Protocol 2.1 (SRP): Auto-populate line details from the selected Brand Job Order."""
        if not self.job_order_id:
            self.update({
                'partner_id': False, 'product_id': False, 'input_qty': 0.0,
                'output_qty': 0.0, 'efficiency': 0.0, 'bags': 0
            })
            return

        bjo = self.job_order_id
        prs = bjo.process_rice_spec_id

        # Calculate Efficiency/Recovery from PRS if available
        efficiency_val = 0.0
        if prs and prs.total_quantity > 0:
            efficiency_val = (prs.process_rice_qty / prs.total_quantity) * 100.0

        self.update({
            'partner_id': bjo.partner_id.id,
            'product_id': bjo.product_id.id,
            'input_qty': bjo.quantity_mt,
            'output_qty': bjo.process_rice_qty,
            'efficiency': efficiency_val,
            'bags': bjo.no_of_bags,
        })