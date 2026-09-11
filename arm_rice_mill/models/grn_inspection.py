# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Clean Code Protocol 1.3: Searchable Constants ---
DEFAULT_MOISTURE_PERCENT = 15.0
DEFAULT_BROKEN_PERCENT = 20.0

QC_FIELDS_TO_SNAPSHOT = [
    'sample_no', 'moisture_percent', 'broken_percent', 'b1_percent',
    'damage_yellow_shriveled_percent', 'chalky_immature_percent',
    'other_variety_percent', 'foreign_grain_percent', 'fungus_grain_percent',
    'red_rice_percent', 'short_grain_percent', 'foreign_matter_percent',
    'paddy_grain_percent', 'under_milled_percent', 'polish_percent',
    'average_length', 'damage_grain_percent', 'green_rice_percent',
    'aflatoxin_percent', 'kett_whitness_percent', 'cooking', 'qc_remarks',
    'inspection_status'
]

QC_RESET_VALUES = {
    'sample_no': False, 'moisture_percent': 0.0, 'broken_percent': 0.0,
    'b1_percent': 0.0, 'damage_yellow_shriveled_percent': 0.0,
    'chalky_immature_percent': 0.0, 'other_variety_percent': 0.0,
    'foreign_grain_percent': 0.0, 'fungus_grain_percent': 0.0,
    'red_rice_percent': 0.0, 'short_grain_percent': 0.0,
    'foreign_matter_percent': 0.0, 'paddy_grain_percent': 0.0,
    'under_milled_percent': 0.0,
    'polish_percent': False,
    'average_length': False,
    'damage_grain_percent': 0.0, 'green_rice_percent': 0.0,
    'aflatoxin_percent': 0.0, 'kett_whitness_percent': 0.0,
    'cooking': False, 'qc_remarks': False, 'inspection_status': 'pass'
}


class MasterTruckType(models.Model):
    _name = 'master.truck.type'
    _description = 'Master Truck Type'

    name = fields.Char(string='Truck Type Name', required=True)
    weighbridge_charges = fields.Float(string='Weighbridge Charges')
    quantity_kgs = fields.Float(string='Quantity (kgs)')


class MasterDestination(models.Model):
    _name = 'master.destination'
    _description = 'Master Destination'

    name = fields.Char(string='Destination Name', required=True)


class MasterCropYear(models.Model):
    _name = 'master.crop.year'
    _description = 'Master Crop Year'

    name = fields.Char(string='Crop Year', required=True)


class GrnInspection(models.Model):
    _name = 'grn.inspection'
    _description = 'GRN Inspection & Quality Control'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    final_qc_no = fields.Char(string='Final QC No.', index=True, readonly=True, copy=False)
    name = fields.Char(string='Inspection No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    inspection_date = fields.Date(string='Inspection Date', default=fields.Date.today(), required=True)
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Primary Purchase Order',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['purchase', 'done'])]"
    )
    ref_po_no = fields.Char(string='Ref. PO No.', readonly=True)
    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract',
                                             related='purchase_order_id.rice_sales_contract_id', store=True,
                                             readonly=True)
    partner_id = fields.Many2one('res.partner', string='Party', required=True, tracking=True)
    broker_id = fields.Many2one('res.partner', string='Broker', related='purchase_order_id.broker_id', readonly=True)
    buyer_id = fields.Many2one('hr.employee', string='Buyer', related='purchase_order_id.buyer_id', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft (Initial QC)'), ('initial_pass', 'Initial QC Passed'),
        ('initial_fail', 'Initial QC Failed'), ('final_qc', 'Final QC In Progress'),
        ('final_pass', 'Final QC Passed'), ('final_fail', 'Final QC Failed'),
        ('return_pending', 'Return Pending'), ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    is_third_party = fields.Boolean(string='Third Party / Outsider', tracking=True)

    location_dest_id = fields.Many2one('stock.location', string='Destination Location',
                                       domain="[('usage', '=', 'internal')]")

    inspection_line_ids = fields.One2many('grn.inspection.line', 'inspection_id', string='Inspection Lines')
    # remarks = fields.Html(string='Remarks')
    po_remarks = fields.Html(related='purchase_order_id.remarks', string="PO Remarks", readonly=True)
    remarks = fields.Html(string='GRN Inspection Remarks')
    gate_pass_count = fields.Integer(string='Gate Passes', compute='_compute_gate_pass_count')

    truck_type = fields.Many2one('master.truck.type', related='inspection_line_ids.truck_type', string='Truck Type',
                                 store=True, readonly=True)
    bags = fields.Integer(related='inspection_line_ids.bags', string='Bags', store=True, readonly=True)
    total_qty_remaining = fields.Float(related='inspection_line_ids.total_qty_remaining', string='Qty Received',
                                       store=True, readonly=True)
    bilty_weight = fields.Float(related='inspection_line_ids.bilty_weight', string='Bilty Weight', store=True,
                                readonly=True)

    sample_no = fields.Char(string='Sample No')
    moisture_percent = fields.Float(string='Moisture %')
    broken_percent = fields.Float(string='Broken %')
    b1_percent = fields.Float(string='B1 %')
    damage_yellow_shriveled_percent = fields.Float(string='Damage/Yellow/Shriveled %')
    chalky_immature_percent = fields.Float(string='Chalky/Immature %')
    other_variety_percent = fields.Float(string='Other Variety %')
    foreign_grain_percent = fields.Float(string='Foreign Grain %')
    fungus_grain_percent = fields.Float(string='Fungus Grain %')
    red_rice_percent = fields.Float(string='Red Rice %')
    short_grain_percent = fields.Float(string='Short Grain %')
    foreign_matter_percent = fields.Float(string='Foreign Matter %')
    paddy_grain_percent = fields.Float(string='Paddy Grain %')
    under_milled_percent = fields.Float(string='Under Milled/Rd Stripped %')
    polish_percent = fields.Char(string='Polish %')
    average_length = fields.Char(string='Average Length')
    damage_grain_percent = fields.Float(string='Damage Grain %')
    green_rice_percent = fields.Float(string='Green Rice %')
    aflatoxin_percent = fields.Float(string='AFLATOXIN')
    kett_whitness_percent = fields.Float(string='KETT WHITENESS')
    cooking = fields.Char(string='Cooking')
    qc_remarks = fields.Text(string='Remarks')
    inspection_status = fields.Selection([('pass', 'Pass'), ('fail', 'Fail')], string='Inspection Status',
                                         default='pass')

    initial_sample_no = fields.Char(string='Initial Sample No')
    initial_moisture_percent = fields.Float(string='Initial Moisture %')
    initial_broken_percent = fields.Float(string='Initial Broken %')
    initial_b1_percent = fields.Float(string='Initial B1 %')
    initial_damage_yellow_shriveled_percent = fields.Float(string='Init Damage/Yellow/Shriveled %')
    initial_chalky_immature_percent = fields.Float(string='Init Chalky/Immature %')
    initial_other_variety_percent = fields.Float(string='Init Other Variety %')
    initial_foreign_grain_percent = fields.Float(string='Init Foreign Grain %')
    initial_fungus_grain_percent = fields.Float(string='Init Fungus Grain %')
    initial_red_rice_percent = fields.Float(string='Init Red Rice %')
    initial_short_grain_percent = fields.Float(string='Init Short Grain %')
    initial_foreign_matter_percent = fields.Float(string='Init Foreign Matter %')
    initial_paddy_grain_percent = fields.Float(string='Init Paddy Grain %')
    initial_under_milled_percent = fields.Float(string='Init Under Milled %')
    initial_polish_percent = fields.Char(string='Init Polish %')
    initial_average_length = fields.Char(string='Init Average Length')
    initial_damage_grain_percent = fields.Float(string='Init Damage Grain %')
    initial_green_rice_percent = fields.Float(string='Init Green Rice %')
    initial_aflatoxin_percent = fields.Float(string='AFLATOXIN')
    initial_kett_whitness_percent = fields.Float(string='KETT WHITENESS')
    initial_cooking = fields.Char(string='Init Cooking')
    initial_qc_remarks = fields.Text(string='Init Remarks')
    initial_inspection_status = fields.Selection([('pass', 'Pass'), ('fail', 'Fail')], string='Init Status')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'GrnInspection':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('grn.inspection') or _('New')
        return super().create(vals_list)

    def _compute_gate_pass_count(self) -> None:
        counts = self._get_related_record_count_batch('gate.pass', 'grn_inspection_id')
        for rec in self:
            rec.gate_pass_count = counts.get(rec.id, 0)

    @api.onchange('partner_id')
    def _onchange_partner_id(self) -> None:
        if self.partner_id and self.purchase_order_id and self.purchase_order_id.partner_id != self.partner_id:
            self.purchase_order_id = False
            self.inspection_line_ids = [COMMAND_CLEAR_ALL]

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self) -> None:
        """Auto-populates inspection lines and basic info only."""
        self.inspection_line_ids = [COMMAND_CLEAR_ALL]

        if self.purchase_order_id:
            if not self.partner_id or self.partner_id != self.purchase_order_id.partner_id:
                self.partner_id = self.purchase_order_id.partner_id
            self.inspection_line_ids = self.purchase_order_id._prepare_inspection_line_vals()
            first_po_line = self.purchase_order_id.order_line[:1]
            self.moisture_percent = first_po_line.moisture_percent if first_po_line else DEFAULT_MOISTURE_PERCENT
            self.broken_percent = first_po_line.broken_percent if first_po_line else DEFAULT_BROKEN_PERCENT
            self.ref_po_no = self.purchase_order_id.ref_po_no or False
            self.remarks = False

    def action_view_purchase_order(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('purchase.order', self.purchase_order_id.id, 'Purchase Order')

    def action_view_sales_contract(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('rice.sales.contract', self.rice_sales_contract_id.id, 'Rice Sales Contract')

    def action_view_gate_passes(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('gate.pass', 'grn_inspection_id', 'Gate Pass')

    def _prepare_gate_pass_line_vals(self) -> List[Tuple[int, int, Dict[str, Any]]]:
        self.ensure_one()
        line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
        valid_lines = self.inspection_line_ids.filtered(lambda l: l.purchase_order_id and l.product_id)
        if not valid_lines:
            raise UserError(_("Please ensure at least one line has a Purchase Order and Product selected."))
        for line in valid_lines:
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'purchase_order_id': line.purchase_order_id.id,
                'purchase_order_line_id': line.purchase_order_line_id.id,
                'product_id': line.product_id.id,
                'return_qty': line.total_qty_remaining,
                'gross': line.total_qty_remaining,
                'net': line.total_qty_remaining,
                'bags': line.bags,
            }))
        return line_vals

    def _prepare_return_weighbridge_vals(self) -> Dict[str, Any]:
        self.ensure_one()
        original_wb = self.env['weighbridge.ticket'].search([('grn_inspection_id', '=', self.id)], limit=1,
                                                            order='id desc')
        original_gp = self.env['gate.pass'].search([('grn_inspection_id', '=', self.id), ('pass_type', '=', 'inbound')],
                                                   limit=1, order='id desc')
        wb_line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
        if original_wb and original_wb.line_ids:
            for line in original_wb.line_ids.filtered(lambda l: l.purchase_order_id):
                wb_line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'purchase_order_id': line.purchase_order_id.id,
                    'purchase_order_line_id': line.purchase_order_line_id.id,
                    'product_id': line.product_id.id if line.product_id else False,
                    'allocated_weight': line.allocated_weight,
                    'bags': line.bags,
                }))
        else:
            for line in self.inspection_line_ids.filtered(lambda l: l.product_id and l.purchase_order_id):
                wb_line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'purchase_order_id': line.purchase_order_id.id,
                    'purchase_order_line_id': line.purchase_order_line_id.id,
                    'product_id': line.product_id.id,
                    'allocated_weight': line.total_qty_remaining,
                    'bags': line.bags,
                }))
        vehicle_number = original_wb.vehicle_number if original_wb else (
            original_gp.vehicle_number if original_gp else False)
        return {
            'grn_inspection_id': self.id,
            'partner_id': self.partner_id.id,
            'vehicle_number': vehicle_number,
            'date': fields.Date.today(),
            'gross_weight': original_wb.gross_weight if original_wb else 0.0,
            'tare_weight': 0.0,
            'state': 'unloading',
            'pass_type': 'return',
            'line_ids': wb_line_vals,
        }

    def action_create_return_weighbridge(self) -> Dict[str, Any]:
        self.ensure_one()
        ticket = self.env['weighbridge.ticket'].create(self._prepare_return_weighbridge_vals())
        return self._open_form_view('weighbridge.ticket', ticket.id, 'Return Weighbridge')

    def _prepare_gate_pass_vals(self) -> Dict[str, Any]:
        """Protocol 4.1 (DRY): Extracts data preparation for Gate Pass generation."""
        self.ensure_one()
        first_line = self.inspection_line_ids[:1]

        return {
            'pass_type': 'inbound',
            'grn_inspection_id': self.id,
            'partner_id': self.partner_id.id,
            'vehicle_number': first_line.truck_no,
            'truck_type': first_line.truck_type.id,
            'bilty_no': first_line.bilty_no,
            # 'remarks': False,  <-- Is line ki ab zaroorat nahi, ye khali jayega
            'gate_pass_line_ids': self._prepare_gate_pass_line_vals(),
        }

    def action_validate_initial_qc(self) -> None:
        """Protocol 2.1 (SRP): Validate Initial QC before anything else can happen."""
        for rec in self:
            valid_lines = rec.inspection_line_ids.filtered(
                lambda l: l.purchase_order_id and l.product_id and l.total_qty_remaining > 0)
            if not valid_lines:
                raise UserError(_("You cannot pass Initial QC without any valid lines with a quantity greater than 0."))
            rec.state = 'initial_pass'

    def action_create_gate_pass(self) -> Dict[str, Any]:
        """Protocol 2.1 (SRP): Create Gate Pass strictly after Initial QC is validated."""
        self.ensure_one()

        # FIX: Enforce strict validation flow
        if self.state != 'initial_pass':
            raise UserError(_("Please validate the Initial QC before creating a Gate Pass."))

        existing_gp = self.env['gate.pass'].search([
            ('grn_inspection_id', '=', self.id),
            ('pass_type', '=', 'inbound'),
            ('state', '!=', 'cancel')  # Phase 3 Fix: Ignore cancelled gate passes
        ], limit=1)

        if existing_gp:
            return self._open_form_view('gate.pass', existing_gp.id, 'Gate Pass')

        gate_pass = self.env['gate.pass'].create({
            'date': self.inspection_date,
            **self._prepare_gate_pass_vals(),
        })

        return self._open_form_view('gate.pass', gate_pass.id, 'Gate Pass')

    def action_fail_initial(self) -> None:
        for rec in self: rec.state = 'initial_fail'

    def action_start_final_qc(self) -> None:
        for rec in self:
            if not rec.final_qc_no:
                rec.final_qc_no = self.env['ir.sequence'].next_by_code('grn.inspection.final.qc') or _('New')
            for field_name in QC_FIELDS_TO_SNAPSHOT:
                rec[f'initial_{field_name}'] = rec[field_name]
            rec.state = 'final_qc'

            # updated action_pass_final function code

    def action_pass_final(self) -> Dict[str, Any]:
        """Protocol 2.1: Single Responsibility - High-level orchestration only."""
        self.ensure_one()
        self.state = 'final_pass'

        if self.is_third_party:
            return self._process_third_party_final_pass()

        return self._process_standard_final_pass()

    def _process_third_party_final_pass(self) -> Dict[str, Any]:
        """Handles the specific flow for third-party outsourced materials."""
        picking_ids: List[int] = []
        unique_pos = self.inspection_line_ids.mapped('purchase_order_id')
        for po in unique_pos:
            picking = self._get_or_create_picking_for_po(po)
            self._update_picking_for_po_direct(picking)
            picking_ids.append(picking.id)

        self._auto_exit_inbound_gate_pass()

        if picking_ids:
            action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_incoming')
            action['domain'] = [('id', 'in', picking_ids)]
            action['name'] = _('Updated GRNs')
            return action
        return self._open_form_view('purchase.order', self.purchase_order_id.id, 'Purchase Order')

    def _process_standard_final_pass(self) -> Dict[str, Any]:
        """Handles the standard flow (redirecting to Weighbridge or PO)."""
        weighbridge = self.env['weighbridge.ticket'].search([('grn_inspection_id', '=', self.id)], limit=1,
                                                            order='id desc')
        if weighbridge:
            return self._open_form_view('weighbridge.ticket', weighbridge.id, 'Weighbridge')
        return self._open_form_view('purchase.order', self.purchase_order_id.id, 'Purchase Order')

    def _auto_exit_inbound_gate_pass(self) -> None:
        """Protocol 2.4: Low-level implementation for gate pass state management."""
        inbound_gate_pass = self.env['gate.pass'].search([
            ('grn_inspection_id', '=', self.id),
            ('pass_type', '=', 'inbound'),
            ('state', '=', 'confirmed')
        ], limit=1)
        if inbound_gate_pass:
            inbound_gate_pass.action_mark_exited()

    # def action_pass_final(self) -> Dict[str, Any]:
    #     self.ensure_one()
    #     self.state = 'final_pass'
    #     weighbridge = self.env['weighbridge.ticket'].search([('grn_inspection_id', '=', self.id)], limit=1,
    #                                                         order='id desc')
    #     if weighbridge:
    #         return self._open_form_view('weighbridge.ticket', weighbridge.id, 'Weighbridge')
    #     return self._open_form_view('purchase.order', self.purchase_order_id.id, 'Purchase Order')

    def action_fail_final(self) -> None:
        for rec in self: rec.state = 'final_fail'

    def action_mark_returned(self) -> None:
        for rec in self: rec.state = 'return_pending'

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'

# NEW METHOD FOR THIRD PARTY
    def _get_or_create_picking_for_po(self, purchase_order: 'purchase.order') -> 'stock.picking':
        self.ensure_one()
        picking = self.env['stock.picking'].search([
            ('purchase_id', '=', purchase_order.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', 'in', ['assigned', 'confirmed', 'draft']),
            ('weighbridge_id', '=', False), ], limit=1, order='id asc')

        if not picking:
            po = purchase_order
            picking_type = po.picking_type_id or self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'), ('company_id', '=', self.env.company.id)
            ], limit=1)
            if not picking_type:
                raise UserError(_("Please configure an incoming picking type."))

            # FIX: Use only Destination Location from GRN Inspection if provided
            dest_location = self.location_dest_id or picking_type.default_location_dest_id

            picking = self.env['stock.picking'].create({
                'partner_id': po.partner_id.id,
                'picking_type_id': picking_type.id,
                'origin': po.name,
                'purchase_id': po.id,
                'location_id': picking_type.default_location_src_id.id,  # Standard Source Location
                'location_dest_id': dest_location.id,
            })

            for po_line in po.order_line:
                if po_line.product_id:
                    self.env['stock.move'].create({
                        'product_id': po_line.product_id.id,
                        'product_uom': po_line.product_id.uom_id.id,
                        'product_uom_qty': 0.0,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'picking_id': picking.id,
                        'picking_type_id': picking.picking_type_id.id,
                        'purchase_line_id': po_line.id,
                        'origin': po.name,
                    })
            picking.action_confirm()
        else:
            # FIX: Update existing picking if destination location is set and different
            dest_location = self.location_dest_id or picking.picking_type_id.default_location_dest_id
            if dest_location and picking.location_dest_id != dest_location:
                picking.write({
                    'location_dest_id': dest_location.id,
                })

        return picking

    def _update_picking_for_po_direct(self, picking: 'stock.picking') -> None:
        """Third-Party flow: fills the GRN directly from Gate Pass + Inspection data (no weighbridge)."""
        self.ensure_one()
        gate_pass = self.env['gate.pass'].search([
            ('grn_inspection_id', '=', self.id), ('pass_type', '=', 'inbound')], limit=1, order='id desc')

        total_bilty_weight = sum(self.inspection_line_ids.mapped('bilty_weight'))
        net_weight = gate_pass.net_qty if gate_pass else sum(self.inspection_line_ids.mapped('total_qty_remaining'))

        picking.write({
            'grn_inspection_id': self.id,
            'gate_pass_id': gate_pass.id if gate_pass else False,
            'weighbridge_id': False,
            'grn_date': fields.Date.today(),
            'product_id': self.inspection_line_ids[:1].product_id.id if self.inspection_line_ids else False,
            'bags': sum(self.inspection_line_ids.mapped('bags')),
            'remarks': self.remarks,
            'vehicle_number': gate_pass.vehicle_number if gate_pass else False,
            'driver_name': gate_pass.driver_name if gate_pass else False,
            'transporter_id': gate_pass.transporter_id.id if gate_pass else False,
            'truck_type': gate_pass.truck_type.id if gate_pass else False,
            'bilty_no': gate_pass.bilty_no if gate_pass else False,
            'gross_weight': gate_pass.gross_qty if gate_pass else 0.0,
            'tare_weight': 0.0,
            'net_weight': net_weight,
            'bilty_weight': total_bilty_weight,
            'actual_moisture': self.moisture_percent,
            'actual_broken': self.broken_percent,
        })

        for line in self.inspection_line_ids.filtered(lambda l: l.purchase_order_id == picking.purchase_id):
            move = picking.move_ids.filtered(
                lambda m: m.purchase_line_id == line.purchase_order_line_id and m.state not in ('done', 'cancel'))[:1]
            qty = line.total_qty_remaining

            if not move:
                move = self.env['stock.move'].create({
                    'product_id': line.product_id.id,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uom_qty': 0.0,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'picking_id': picking.id,
                    'picking_type_id': picking.picking_type_id.id,
                    'purchase_line_id': line.purchase_order_line_id.id,
                    'origin': picking.origin, })
                move._action_confirm()

            move.write({'product_uom_qty': qty})

            if move.move_line_ids:
                move.move_line_ids[:1].write({'quantity': qty, 'product_uom_id': line.product_id.uom_id.id})
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_id.uom_id.id,
                    'quantity': qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id, })


class GrnInspectionLine(models.Model):
    _name = 'grn.inspection.line'
    _description = 'GRN Inspection Line'
    _inherit = 'purchase.order.line.mapper.mixin'

    inspection_id = fields.Many2one('grn.inspection', string='Inspection', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item Name')
    crop = fields.Many2one('master.crop.year', string='Crop')
    truck_no = fields.Char(string='Truck No.') 
    bilty_no = fields.Char(string='Bilty No.') 
    bilty_weight = fields.Float(string='Bilty Weight') 
    bags = fields.Integer(string='Bags')
    bardana = fields.Selection([('pp_bags', 'PP Bags'), ('jute_bags', 'Jute Bags')], string='Bardana')

    destination = fields.Many2one('master.destination', string='Station')
    truck_type = fields.Many2one('master.truck.type', string='Truck Type')

    unit_price = fields.Float(string= "Unit Price")


    # Base quantity captured from the PO at TLS = 1 (the reference point for scaling)
    base_qty_received = fields.Float(string='Base Qty Received', readonly=True, copy=False)
    total_qty_remaining = fields.Float(string='Qty Received')

    # Flow Fix: Replaced 'available_tls' with mapped 'po_tls' and manual 'grn_insp_tls'
    po_tls = fields.Float(string='PO TLS', readonly=True)
    grn_insp_tls = fields.Float(string='GRN Insp. TLS')

    # updated function

    def _apply_po_line_values(self, po_line: 'purchase.order.line') -> None:
        self.product_id = po_line.product_id
        base_qty = (po_line.product_qty / po_line.no_of_trucks) if po_line.no_of_trucks else po_line.product_qty

        self.base_qty_received = base_qty
        self.crop = po_line.crop_year.id
        self.bags = po_line.no_of_bags
        self.po_tls = po_line.available_tls
        self.unit_price = po_line.price_unit

        # keep TLS default at 1 unless already set, then derive qty from base * tls
        self.grn_insp_tls = self.grn_insp_tls or 1.0
        self.total_qty_remaining = base_qty * self.grn_insp_tls

    @api.onchange('grn_insp_tls')
    def _onchange_grn_insp_tls(self) -> None:
        for line in self:
            if not line.base_qty_received:
            # Derive the base from what was last saved in the DB (the "origin" record),
            # since this record predates the base_qty_received field.
                origin = line._origin
                prev_tls = origin.grn_insp_tls or 1.0
                prev_qty = origin.total_qty_remaining or line.total_qty_remaining
                line.base_qty_received = (prev_qty / prev_tls) if prev_tls else prev_qty

            if line.base_qty_received:
                line.total_qty_remaining = line.base_qty_received * (line.grn_insp_tls or 0.0)

    # def _apply_po_line_values(self, po_line: 'purchase.order.line') -> None:
    #     self.product_id = po_line.product_id 
    #     self.total_qty_remaining = po_line.product_qty - po_line.qty_received
    #     self.crop = po_line.crop_year.id
    #     self.bags = po_line.no_of_bags 
    #     self.po_tls = po_line.available_tls




