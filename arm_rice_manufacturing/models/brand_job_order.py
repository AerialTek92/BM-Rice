# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List

COMMAND_CREATE_NEW: int = 0


class BrandJobOrder(models.Model):
    _name = 'brand.job.order'
    _description = 'Brand Job Order'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin', 'approval.tracker.mixin']
    _order = 'id desc'

    name = fields.Char(string='Job Order No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Job Date', default=fields.Date.today(), required=True)

    process_rice_spec_id = fields.Many2one('process.rice.spec', string='Specification No.')

    prs_contract_id = fields.Many2one(
        'rice.sales.contract',
        related='process_rice_spec_id.rice_sales_contract_id',
        store=False
    )

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract')
    partner_id = fields.Many2one('res.partner', string='Customer')
    rice_type = fields.Selection(related='process_rice_spec_id.rice_type', string='Rice Type', store=True,
                                 readonly=True)

    product_id = fields.Many2one('product.product', string='Process Rice', required=True)
    raw_rice_ids = fields.Many2many('product.product', string='Raw Rice', readonly=True)
    process_rice_qty = fields.Float(string='Process Rice QTY')
    quantity_mt = fields.Float(string='Quantity [MT]')
    packing = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('bo_pp_bags', 'BO PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('china_cotton', 'China Cotton')
    ], string='Packing')
    contract_date = fields.Date(string='Contract Date')

    # FIX: Changed to Many2one to res.country for dropdown selection
    destination_country = fields.Many2one('res.country', string='Destination Country')

    shipment_period = fields.Char(string='Shipment Period')
    broken_percent = fields.Float(string='Broken (%)')
    moisture_percent = fields.Float(string='Moisture (%)')

    no_of_bags = fields.Integer(string='No of Bags')
    empty_bag_weight = fields.Float(string='Empty Bag Weight (gram)')
    empty_bag_weight_additional = fields.Float(string='Empty Bag Weight (Additional)')
    total_empty_bag_weight = fields.Float(
        string='Total Empty Bag Weight (grams)',
        compute='_compute_total_empty_bag_weight',
        store=True,
        readonly=True
    )
    pp_bags_kgs = fields.Float(string='PP Bags (Kgs)')

    net_weight = fields.Float(string="Net Weight")
    gross_weight = fields.Float(string="Gross Weight")

    fumigation_chemical = fields.Selection([
        ('aluminum_phosphide', 'Aluminum Phosphide'),
        ('methyl_bromide', 'Methyl Bromide')
    ], string='Chemical Advised', default='aluminum_phosphide')

    fumigation_method = fields.Char(string='Dosage')

    phyto_certificate_req = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Phyto Certificate Requirement', default='no')

    fumigation_agency_id = fields.Many2one(
        'fumigation.agency',
        string='Fumigation Agency',
    )
    no_of_samples = fields.Integer(string='No Of Samples Required')
    inspection_agency = fields.Many2one(
        'inspection.agency',
        string='Inspection Agency',
    )
    inspection_date = fields.Date(string='Inspection Date')
    remarks = fields.Html(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('in_progress', 'In Progress'), ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    issue_material_count = fields.Integer(string='Issue Materials', compute='_compute_issue_material_count')
    production_record_count = fields.Integer(string='Productions', compute='_compute_production_record_count')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'BrandJobOrder':
        # FIX: Generate sequence number on creation
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('brand.job.order') or _('New')

        orders = super().create(vals_list)
        for order in orders:
            matrix = order._apply_default_approval_matrix()
            if matrix:
                line_vals = []
                for m_line in matrix.line_ids:
                    line_vals.append((COMMAND_CREATE_NEW, 0, {
                        'res_model': order._name,
                        'res_id': order.id,
                        'sequence': m_line.sequence,
                        'label': m_line.label,
                        'employee_id': m_line.employee_id.id if m_line.employee_id else False,
                        'group_id': m_line.group_id.id if m_line.group_id else False,
                        'status': 'waiting',
                    }))
                if line_vals:
                    order.approval_line_ids = line_vals
        return orders

    # NEW: Custom display name for Production Record context (Protocol 4.1 DRY)
    @api.depends('name', 'partner_id.name', 'quantity_mt','product_id.name')
    def _compute_display_name(self) -> None:
        if self.env.context.get('production_record_job_view'):
            for order in self:
                partner_name = order.partner_id.name or ''
                qty = order.quantity_mt or 0.0
                brand_name = order.product_id.name or ''
                order.display_name = f"{order.name or ''} | {partner_name} | {qty} | {brand_name}"
        else:
            super()._compute_display_name()

    def _compute_issue_material_count(self) -> None:
        counts = self._get_related_record_count_batch('issue.material', 'job_order_id')
        for rec in self:
            rec.issue_material_count = counts.get(rec.id, 0)

    def _compute_production_record_count(self) -> None:
        counts = self._get_related_record_count_batch('production.record', 'job_order_id')
        for rec in self:
            rec.production_record_count = counts.get(rec.id, 0)

    @api.depends('empty_bag_weight', 'empty_bag_weight_additional')
    def _compute_total_empty_bag_weight(self):
        for rec in self:
            rec.total_empty_bag_weight = rec.empty_bag_weight + rec.empty_bag_weight_additional

    @api.onchange('process_rice_spec_id')
    def _onchange_process_rice_spec_id(self) -> None:
        if not self.process_rice_spec_id:
            self.update({
                'rice_sales_contract_id': False, 'partner_id': False, 'product_id': False,
                'raw_rice_ids': [(5, 0, 0)],  # Clear the Many2many
                'quantity_mt': 0.0, 'packing': False, 'contract_date': False,
                'destination_country': False, 'shipment_period': False, 'broken_percent': 0.0,
                'moisture_percent': 0.0, 'inspection_agency': False, 'pp_bags_kgs': 0.0, 'remarks': False,
            })
            return

        prs = self.process_rice_spec_id
        rsc = prs.rice_sales_contract_id

        shipment_period = False
        if rsc and rsc.delivery_date_from and rsc.delivery_date_to:
            shipment_period = f"{rsc.delivery_date_from.strftime('%d/%m/%Y')} to {rsc.delivery_date_to.strftime('%d/%m/%Y')}"

        bjo_remarks = ""
        if prs.remarks:
            bjo_remarks = f"<b>Process Rice Spec Remarks:</b><br/>{prs.remarks}<br/><br/><b>Brand Job Order Remarks:</b><br/>"
        else:
            bjo_remarks = "<b>Brand Job Order Remarks:</b><br/>"

        raw_product_ids = prs.spec_line_ids.mapped('product_id').ids

        raw_product_ids = prs.spec_line_ids.mapped('product_id').ids

        # FIX: Directly map Destination Country from the RSC instead of doing a text search
        destination_country_val = rsc.destination_country_id.id if rsc and rsc.destination_country_id else False

        self.update({
            'rice_sales_contract_id': rsc.id if rsc else False,
            'partner_id': prs.partner_id.id,
            'product_id': prs.product_id.id,
            'raw_rice_ids': [(6, 0, raw_product_ids)],
            'quantity_mt': sum(prs.spec_line_ids.mapped('quantity')),
            'packing': prs.packing,
            'pp_bags_kgs': prs.pp_bags_kgs,
            'process_rice_qty': prs.process_rice_qty,
            'contract_date': rsc.contract_date if rsc else False,
            'destination_country': destination_country_val,
            'shipment_period': shipment_period,
            'broken_percent': prs.n_broken_percent,  # Updated to read from header
            'moisture_percent': prs.n_moisture_percent,  # Updated to read from header
            'inspection_agency': rsc.inspection_agency if rsc else False,
            'remarks': bjo_remarks,
        })

    def action_confirm(self) -> None:
        for rec in self:
            is_admin = self.env.user.has_group('base.group_system')
            if rec.approval_line_ids and rec.approval_status != 'approved' and not is_admin:
                raise UserError(_("You cannot confirm this Job Order until all approvals are completed."))
            if not rec.product_id:
                raise UserError(_("Please specify a Product before confirming."))
            rec.state = 'confirmed'

    def _execute_post_approval(self):
        """Automatically confirm the Job Order when the final approval is done."""
        self.ensure_one()
        if self.state == 'draft':
            self.action_confirm()

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def action_done(self) -> None:
        """Protocol 2.1 (SRP): Mark the Job Order as Done."""
        for rec in self:
            rec.state = 'done'

    def action_create_planning_sheet(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Planning',
            'res_model': 'production.planning',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.id,
                'default_date': fields.Date.today(),
            }
        }

    def action_create_issue_material(self) -> Dict[str, Any]:
        self.ensure_one()
        self.state = 'in_progress'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Material',
            'res_model': 'issue.material',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.id,
                'default_issue_date': fields.Date.today(),
            }
        }

    def action_view_issue_materials(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('issue.material', 'job_order_id', 'Issue Material')

    def action_create_production_record(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Record',
            'res_model': 'production.record',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.id,
                'default_production_date': fields.Date.today(),
            }
        }

    def action_view_production_records(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.record', 'job_order_id', 'Production Record')

    # CR-08: Scoped Matrix Search for Brand Job Orders
    def _apply_default_approval_matrix(self):
        """Fetch the correct matrix based on Product Type / Plant."""
        self.ensure_one()
        
        # 1. Try to find a matrix specifically for this Rice Type (IRRI or Basmati)
        matrix = self.env['approval.matrix'].search([
            ('model_id.model', '=', self._name),
            ('rice_type', '=', self.rice_type)
        ], limit=1)
        
        # 2. Fallback: If no specific matrix is found, use the 'All Types' matrix
        if not matrix:
            matrix = self.env['approval.matrix'].search([
                ('model_id.model', '=', self._name),
                ('rice_type', '=', 'all')
            ], limit=1)
            
        return matrix


class FumigationAgency(models.Model):
    _name = 'fumigation.agency'
    _description = 'Fumigation Agency'
    _order = 'name'

    name = fields.Char(string='Agency Name', required=True)


class InspectionAgency(models.Model):
    _name = 'inspection.agency'
    _description = 'Inspection Agency'
    _order = 'name'

    name = fields.Char(string='Inspection Agency', required=True)