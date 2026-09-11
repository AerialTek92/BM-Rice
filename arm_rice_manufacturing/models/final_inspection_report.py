# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from typing import Dict, Any, List


class FinalInspectionReport(models.Model):
    _name = 'final.inspection.report'
    _description = 'Final Inspection Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))

    # Plant Selection as per SS
    plant = fields.Selection([
        ('plant_a', 'Plant A'),
        ('plant_b', 'Plant B'),
        ('plant_c', 'Plant C')
    ], string='Plant', default='plant_a')

    operator_name = fields.Char(string='Name of Operator')
    customer_id = fields.Many2one('res.partner', string='Customer Name')
    brand_name = fields.Char(string='Brand Name')
    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.')

    date = fields.Date(string='Date', default=fields.Date.today(), required=True)
    day = fields.Selection([
        ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')
    ], string='Day', default='monday')
    shift = fields.Selection([('8 Hours', '8 Hours'), ('12 Hours', '12 Hours')], string='Shift')

    # Table for Standard and Observed Values
    report_line_ids = fields.One2many('final.inspection.report.line', 'report_id', string='Quality Parameters')

    shift_supervisor = fields.Char(string='Shift Supervisor')
    production_head = fields.Char(string='Production Head')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'FinalInspectionReport':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('final.inspection.report') or _('New')
        return super().create(vals_list)

    @api.onchange('job_order_id')
    def _onchange_job_order_id_fetch_standard_values(self):
        if not self.job_order_id:
            self.report_line_ids = [(5, 0, 0)]
            return

        prs = self.job_order_id.process_rice_spec_id
        if not prs:
            self.report_line_ids = [(5, 0, 0)]
            return

        # Auto-populate Customer and Brand if empty
        if not self.customer_id and self.job_order_id.partner_id:
            self.customer_id = self.job_order_id.partner_id.id
        if not self.brand_name and self.job_order_id.product_id:
            self.brand_name = self.job_order_id.product_id.name

        # Fetch specs directly from PRS header
        line_vals = {
            'name': 'Standard',
            'std_moisture': prs.n_moisture_percent,
            'std_broken': prs.n_broken_percent,
            'std_damage_yellow': prs.n_damaged_discolor_percent,
            'std_foreign_matter': prs.n_foreign_matter_percent,
            'std_paddy_grain': prs.n_paddy_percent,
            'std_under_milled_choba': prs.n_under_milled_grains,
            'std_kett_whitnes': prs.n_kett_whiteness,
        }

        # Replace existing lines with one pre-filled standard line.
        self.report_line_ids = [(5, 0, 0), (0, 0, line_vals)]
    def action_confirm(self) -> None:
        for rec in self:
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'


class FinalInspectionReportLine(models.Model):
    _name = 'final.inspection.report.line'
    _description = 'Final Inspection Report Line'
    _order = 'id asc'

    report_id = fields.Many2one('final.inspection.report', string='Report', required=True, ondelete='cascade')

    name = fields.Char(string='Hours / Type')

    # Standard Values (Fetched automatically, readonly in form)
    std_sample_kg = fields.Float(string='Sample (kg)')
    std_broken = fields.Float(string='Broken')
    std_damage_yellow = fields.Float(string='Damage / Yellow')
    std_moisture = fields.Float(string='Moisture')
    std_foreign_grains = fields.Float(string='Foreign Grains')
    std_foreign_matter = fields.Float(string='Foreign Matter')
    std_paddy_grain = fields.Float(string='Paddy Grain')
    std_under_milled_choba = fields.Float(string='Under Milled / Choba')
    std_kett_whitnes = fields.Float(string='Kett Whitnes')
    std_packaging_material = fields.Char(string='Packaging Material')
    std_remarks = fields.Char(string='Remarks')

    # Observed Values (User manually fills these)
    sample_kg = fields.Float(string='Sample (kg)')
    broken = fields.Float(string='Broken')
    damage_yellow = fields.Float(string='Damage / Yellow')
    moisture = fields.Float(string='Moisture')
    foreign_grains = fields.Float(string='Foreign Grains')
    foreign_matter = fields.Float(string='Foreign Matter')
    paddy_grain = fields.Float(string='Paddy Grain')
    under_milled_choba = fields.Float(string='Under Milled / Choba')
    kett_whitnes = fields.Float(string='Kett Whitnes')
    packaging_material = fields.Char(string='Packaging Material')
    remarks = fields.Char(string='Remarks')