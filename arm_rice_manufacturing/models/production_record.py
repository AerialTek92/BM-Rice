# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class ProductionRecord(models.Model):
    _name = 'production.record'
    _description = 'Production Record'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Production No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    operator_name = fields.Char(string='Operator Name')
    shift = fields.Selection([('morning', 'Morning'), ('evening', 'Evening'), ('night', 'Night')], string='Shift')
    day = fields.Char(string='Day')
    production_date = fields.Date(string='Production Date', default=fields.Date.today(), required=True)
    product_id = fields.Many2one('product.product', string='Process Rice')
    
    
    # FIX: Added context to trigger custom display name
    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True, context={'production_record_job_view': True})
    

    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True)
    issue_material_id = fields.Many2one(
        'issue.material',
        string='Issue Material Ref',
        domain="[('job_order_id', '=', job_order_id), ('state', '=', 'confirmed')]"
    )
    process_rice_qty = fields.Float(string='Process Rice QTY')

    source_location_ids = fields.Many2many(
        'stock.location',
        string='Source Locations',
        domain="[('usage', '=', 'internal')]"
    )
    dest_location_id = fields.Many2one('stock.location', string='Destination Location', required=True,
                                       domain="[('usage', '=', 'internal')]")

    # NEW: Link to Finished Weighbridge
    finished_wb_ticket_id = fields.Many2one(
        'weighbridge.ticket',
        string='Finished W/B Ref',
        domain="['|', ('mfg_bjo_1_id', '=', job_order_id), ('mfg_bjo_2_id', '=', job_order_id), ('is_finished_weighbridge', '=', True), ('state', '=', 'confirmed')]"
    )

    # --- Section: Weights & Yield ---
    raw_material_weight = fields.Float(string='Raw Material Weight')
    finished_material_weight = fields.Float(string='Finished Material Weight')
    byproduct_weight = fields.Float(string='Bi-Product Weight (MT)', compute='_compute_byproduct_weight', store=True)
    recovery_pct = fields.Float(string='Recovery %', compute='_compute_recovery_pct', store=True, readonly=True)

    # --- Section: Bags & Quality ---
    finished_bags = fields.Integer(string='Finished Bags')
    empty_bag_weight = fields.Float(string='Empty Bag Weight (MT)')
    moisture = fields.Float(string='Moisture %')
    agl = fields.Float(string='AGL (MM)')

    byproduct_line_ids = fields.One2many('production.record.line', 'production_id', string='Bi-Products')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)
    remarks = fields.Html(string='Remarks')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionRecord':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.record.rework' if vals.get('is_reworking') else 'production.record'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    @api.depends('byproduct_line_ids.qty')
    def _compute_byproduct_weight(self):
        for rec in self:
            rec.byproduct_weight = sum(rec.byproduct_line_ids.mapped('qty'))

    @api.depends('finished_material_weight', 'raw_material_weight')
    def _compute_recovery_pct(self):
        for rec in self:
            if rec.raw_material_weight > 0:
                rec.recovery_pct = (rec.finished_material_weight / rec.raw_material_weight) * 100
            else:
                rec.recovery_pct = 0.0

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self):
        if not self.job_order_id:
            self.remarks = False
            self.moisture = 0.0
            self.agl = 0.0
            self.process_rice_qty = 0.0
            self.product_id = False
            self.byproduct_line_ids = [(5, 0, 0)]
            return

        bjo = self.job_order_id
        prd_remarks = ""
        if bjo.remarks:
            prd_remarks = f"{bjo.remarks}<br/><br/><b>Production Record Remarks:</b><br/>"
        else:
            prd_remarks = "<b>Production Record Remarks:</b><br/>"

        prs = bjo.process_rice_spec_id
        moisture_val = 0.0
        agl_val = 0.0
        if prs:
            moisture_val = prs.n_moisture_percent
            agl_val = prs.n_agl

        # ==========================================
        # NEW: Fetch By-Products from Production Log Sheet
        # ==========================================
        byproduct_vals = [(5, 0, 0)]  # Clear existing lines
        
        # Search for Log Sheets linked to this Job Order (either as 1st or 2nd Job Order)
        log_sheets = self.env['production.log.sheet'].search([
            '|',
            ('job_order_1_id', '=', bjo.id),
            ('job_order_2_id', '=', bjo.id)
        ])

        # Loop through found log sheets and fetch their by-product lines
        for log_sheet in log_sheets:
            for line in log_sheet.byproduct_line_ids:
                byproduct_vals.append((0, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.weight,         # Map 'Weight' from Log Sheet to 'Quantity'
                    'bags': line.bags,          # Map 'Bags'
                    'coverage_ratio': line.percent  # Map '%' to 'Coverage Ratio (%)'
                }))

        self.update({
            'remarks': prd_remarks,
            'moisture': moisture_val,
            'agl': agl_val,
            'product_id': bjo.product_id.id,
            'process_rice_qty': bjo.process_rice_qty,
            'byproduct_line_ids': byproduct_vals
        })

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self) -> None:
        if not self.issue_material_id:
            self.update({
                'source_location_ids': [(5, 0, 0)],
                'dest_location_id': False,
                'raw_material_weight': 0.0,
                'byproduct_line_ids': [(5, 0, 0)] # NEW: Clear bi-products if cleared
            })
            return

        issue = self.issue_material_id

        # Calculate validated quantity from the linked internal transfer
        validated_qty = 0.0
        if issue.picking_id and issue.picking_id.state == 'done':
            validated_qty = sum(issue.picking_id.move_ids.mapped('quantity'))

        dest_loc_id = issue.dest_location_ids[:1].id if issue.dest_location_ids else False

        log_sheets = self.env['production.log.sheet'].search([
            ('issue_material_id', '=', issue.id)
        ])

        # NEW: Map Bi-Products from all found Log Sheets
        byproduct_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for log_sheet in log_sheets:
            for line in log_sheet.byproduct_line_ids:
                byproduct_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.weight,         # Map 'Weight' from Log Sheet to 'Quantity'
                    'bags': line.bags,          # Map 'Bags'
                    'coverage_ratio': line.percent  # Map '%' to 'Coverage Ratio (%)'
                }))

        self.update({
            'raw_material_weight': validated_qty,
            'source_location_ids': [(6, 0, issue.source_location_ids.ids)],
            'dest_location_id': dest_loc_id,
            'byproduct_line_ids': byproduct_vals
        })

    @api.onchange('finished_wb_ticket_id')
    def _onchange_finished_wb_ticket_id(self) -> None:
        """Protocol 2.1 (SRP): Pull finished weights and by-products from the Weighbridge."""
        if not self.finished_wb_ticket_id:
            return

        wb = self.finished_wb_ticket_id

        allocated_lines = wb.line_ids.filtered(lambda l: l.bjo_id == self.job_order_id)
        self.finished_material_weight = sum(allocated_lines.mapped('allocated_weight'))

        # 2. Map By-Product Lines from WB to Production Record
        byproduct_vals = [COMMAND_CLEAR_ALL]
        for line in wb.wb_byproduct_line_ids:
            byproduct_vals.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'qty': line.weight,
                'bags': line.bags,
                'coverage_ratio': line.percent
            }))
        self.byproduct_line_ids = byproduct_vals

    def action_create_issue_material_from_production(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Material',
            'res_model': 'issue.material',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.job_order_id.id,
                'default_issue_date': fields.Date.today(),
            }
        }

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.byproduct_line_ids:
                raise UserError(_("Please add finished goods/by-products before confirming."))
            rec.state = 'confirmed'

    def action_receive_from_mill(self):
        for rec in self:
            if not rec.source_location_ids or not rec.dest_location_id:
                raise UserError(_("Please select both Source and Destination locations before receiving."))

            res = rec._create_internal_transfer()
            rec.state = 'done'

            if not rec.issue_material_id:
                return rec.action_create_issue_material_from_production()

            if res:
                return res
        return True

    def _create_internal_transfer(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an internal picking type."))

        header_source_id = self.source_location_ids[0].id if self.source_location_ids else self.dest_location_id.id

        picking = self.env['stock.picking'].create({
            'partner_id': self.job_order_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': self.name,
            'location_id': header_source_id,
            'location_dest_id': self.dest_location_id.id,
        })

        for line in self.byproduct_line_ids:
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.qty,
                'location_id': header_source_id,
                'location_dest_id': self.dest_location_id.id,
            })

        picking.action_confirm()
        picking.action_assign()

        if picking.state != 'done':
            for move in picking.move_ids:
                move.write({'quantity': move.product_uom_qty, 'picked': True})

            needs_tracking = any(m.product_id.tracking != 'none' for m in picking.move_ids)
            if not needs_tracking:
                validate_res = picking.button_validate()
                if isinstance(validate_res, dict):
                    return validate_res
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Internal Transfer',
                    'res_model': 'stock.picking',
                    'view_mode': 'form',
                    'res_id': picking.id,
                    'target': 'current',
                }

        self.picking_id = picking.id
        return True

    def action_cancel(self) -> None:
        for rec in self:
            if rec.picking_id and rec.picking_id.state != 'cancel':
                rec.picking_id.action_cancel()
            rec.state = 'cancel'

    def unlink(self) -> bool:
        for rec in self:
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_(
                    "You cannot delete a Production Record that has a validated stock transfer. "
                    "Please cancel it instead."
                ))
        pickings = self.mapped('picking_id')
        res = super().unlink()
        draft_pickings = pickings.filtered(lambda p: p.state in ('draft', 'cancel'))
        if draft_pickings:
            draft_pickings.unlink()
        return res

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def action_view_picking(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('stock.picking', self.picking_id.id, 'Internal Transfer')


class ProductionRecordLine(models.Model):
    _name = 'production.record.line'
    _description = 'Production Record Line'

    production_id = fields.Many2one('production.record', string='Production', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    location_id = fields.Many2one('stock.location', string='Location',
                                  default=lambda self: self.env.ref('stock.stock_location_stock').id)
    qty = fields.Float(string='Quantity')
    bags = fields.Integer(string='Bags')
    coverage_ratio = fields.Float(string='Coverage Ratio (%)')