# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class ProductionLogSheet(models.Model):
    _name = 'production.log.sheet'
    _description = 'Production Log Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Log No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))

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

    date = fields.Date(string='Date', default=fields.Date.today(), required=True)
    day = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ], string='Day', default='monday')
    shift = fields.Selection([
        ('8_hours', '8 Hours'),
        ('12_hours', '12 Hours'),
    ], string='Shift', default='8_hours')
    operator_name = fields.Many2one('operator.name', string='Operator Name')

    customer_1_id = fields.Many2one('res.partner', string='1st Customer Name')
    job_order_1_id = fields.Many2one('brand.job.order', string='1st Job Order No.')
    customer_2_id = fields.Many2one('res.partner', string='2nd Customer Name')
    job_order_2_id = fields.Many2one('brand.job.order', string='2nd Job Order No.')

    first_finish_lot_location_id = fields.Many2one('stock.location', string='First Finish Lot Stacking Location',
                                                   domain="[('usage', '=', 'internal')]")

    second_finish_lot_location_id = fields.Many2one('stock.location', string='Second Finish Lot Stacking Location',
                                                    domain="[('usage', '=', 'internal')]")

    running_line_ids = fields.One2many('production.log.running.line', 'log_sheet_id', string='Running Time')
    stop_line_ids = fields.One2many('production.log.stop.line', 'log_sheet_id', string='Stop Time')
    packing_line_ids = fields.One2many('production.log.packing.line', 'log_sheet_id', string='Final Product Packing')
    byproduct_line_ids = fields.One2many('production.log.byproduct.line', 'log_sheet_id', string='By-Product Summary')

    total_running_time = fields.Char(string='Total Running Time')
    total_down_time = fields.Char(string='Total Down Time')

    prepared_by = fields.Char(string='Prepared By')
    supervisor = fields.Char(string='Production Supervisor')
    production_head = fields.Char(string='Production Head')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    remarks = fields.Html(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionLogSheet':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.log.sheet.rework' if vals.get('is_reworking') else 'production.log.sheet'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.running_line_ids and not rec.packing_line_ids:
                raise UserError(_("Please add at least one Running Time or Packing line before confirming."))
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

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

    @api.onchange('customer_1_id')
    def _onchange_customer_1_id(self):
        if self.job_order_1_id and self.job_order_1_id.partner_id != self.customer_1_id:
            self.job_order_1_id = False

    @api.onchange('customer_2_id')
    def _onchange_customer_2_id(self):
        if self.job_order_2_id and self.job_order_2_id.partner_id != self.customer_2_id:
            self.job_order_2_id = False

    # Protocol 2.1 & 4.1 (DRY): Sync raw rice and process rice from selected Job Orders
    @api.onchange('job_order_1_id', 'job_order_2_id')
    def _onchange_job_order_ids_sync_running_lines(self) -> None:
        """Auto-populate Running Time lines with Raw Rice AND 
        Final Product Packing lines with Process Rice from the selected Brand Job Orders."""
        
        # ==========================================
        # 1. Handle Running Time Lines (Raw Rice)
        # ==========================================
        raw_rice_products = self.env['product.product']
        if self.job_order_1_id:
            raw_rice_products |= self.job_order_1_id.raw_rice_ids
        if self.job_order_2_id:
            raw_rice_products |= self.job_order_2_id.raw_rice_ids

        existing_running_map: Dict[int, Dict[str, Any]] = {}
        for line in self.running_line_ids:
            if line.product_id and line.product_id in raw_rice_products:
                existing_running_map[line.product_id.id] = {
                    'product_id': line.product_id.id,
                    'start_time': line.start_time,
                    'stop_time': line.stop_time,
                    'actual_time': line.actual_time,
                    'remarks': line.remarks,
                }

        running_line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for product in raw_rice_products:
            if product.id in existing_running_map:
                running_line_vals.append((COMMAND_CREATE_NEW, 0, existing_running_map[product.id]))
            else:
                running_line_vals.append((COMMAND_CREATE_NEW, 0, {'product_id': product.id}))

        self.running_line_ids = running_line_vals

        # ==========================================
        # 2. Handle Final Product Packing Lines (Process Rice)
        # ==========================================
        process_rice_products = self.env['product.product']
        if self.job_order_1_id and self.job_order_1_id.product_id:
            process_rice_products |= self.job_order_1_id.product_id
        if self.job_order_2_id and self.job_order_2_id.product_id:
            process_rice_products |= self.job_order_2_id.product_id

        existing_packing_map: Dict[int, Dict[str, Any]] = {}
        for line in self.packing_line_ids:
            if line.product_id and line.product_id in process_rice_products:
                existing_packing_map[line.product_id.id] = {
                    'product_id': line.product_id.id,
                    'variety': line.variety,
                    'no_of_bags': line.no_of_bags,
                    'packing_size': line.packing_size,
                    'total_weight': line.total_weight,
                    'percent': line.percent,
                }

        packing_line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for product in process_rice_products:
            if product.id in existing_packing_map:
                packing_line_vals.append((COMMAND_CREATE_NEW, 0, existing_packing_map[product.id]))
            else:
                packing_line_vals.append((COMMAND_CREATE_NEW, 0, {'product_id': product.id}))

        self.packing_line_ids = packing_line_vals
        
        # # ==========================================
        # # 3. Handle By-Product Summary Lines (Auto-fetch By-Products)
        # # ==========================================
        # # FIX: Search for all products marked as 'By Product' on the Product Master
        # byproduct_products = self.env['product.product'].search([('is_by_product', '=', True)])

        # existing_byproduct_map: Dict[int, Dict[str, Any]] = {}
        # for line in self.byproduct_line_ids:
        #     if line.product_id and line.product_id in byproduct_products:
        #         existing_byproduct_map[line.product_id.id] = {
        #             'product_id': line.product_id.id,
        #             'bags': line.bags,
        #             'size': line.size,
        #             'weight': line.weight,
        #             'percent': line.percent,
        #         }

        # byproduct_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        # for product in byproduct_products:
        #     if product.id in existing_byproduct_map:
        #         byproduct_vals.append((COMMAND_CREATE_NEW, 0, existing_byproduct_map[product.id]))
        #     else:
        #         byproduct_vals.append((COMMAND_CREATE_NEW, 0, {'product_id': product.id}))

        # self.byproduct_line_ids = byproduct_vals

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id_milling_date(self):
        if self.issue_material_id:
            self.milling_date = self.issue_material_id.milling_date


class ProductionLogRunningLine(models.Model):
    _name = 'production.log.running.line'
    _description = 'Production Log - Running Time Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item')
    start_time = fields.Char(string='Start Time')
    stop_time = fields.Char(string='Stop Time')
    actual_time = fields.Char(string='Actual Time')
    remarks = fields.Char(string='Remarks')


class ProductionLogStopLine(models.Model):
    _name = 'production.log.stop.line'
    _description = 'Production Log - Stop Time Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    stop_time = fields.Char(string='Stop Time')
    start_time = fields.Char(string='Start Time')
    down_time = fields.Char(string='Down Time')
    remarks = fields.Char(string='Remarks')


class ProductionLogPackingLine(models.Model):
    _name = 'production.log.packing.line'
    _description = 'Production Log - Final Product Packing Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Brand')
    variety = fields.Char(string='Variety')
    no_of_bags = fields.Integer(string='No. Bags')
    packing_size = fields.Float(string='Packing Size')
    total_weight = fields.Float(string='T. Wt')
    percent = fields.Float(string='%')


class ProductionLogByproductLine(models.Model):
    _name = 'production.log.byproduct.line'
    _description = 'Production Log - By-Product Summary Line'
    _order = 'id asc'

    # FIX: Removed required=True to allow reuse in Weighbridge (Protocol 4.1 DRY)
    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', ondelete='cascade')

    # NEW: Relational link to Weighbridge Ticket
    wb_ticket_id = fields.Many2one('weighbridge.ticket', string='Weighbridge Ticket', ondelete='cascade')

    product_id = fields.Many2one('product.product', string='Item')
    bags = fields.Integer(string='Bags')
    size = fields.Float(string='Size')
    weight = fields.Float(string='Weight')
    percent = fields.Float(string='%')


class OperatorName(models.Model):
    _name = 'operator.name'
    _description = 'Operator Name'
    _order = 'name'

    name = fields.Char(string='Operator Name', required=True)