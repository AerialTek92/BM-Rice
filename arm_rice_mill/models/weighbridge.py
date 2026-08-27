# -*- coding: utf-8 -*-

import serial
from dataclasses import dataclass
from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api, _
from typing import Dict, Any, List, Tuple
from datetime import datetime
import re

# Phase 5 Fix: Protocol 1.3 (Searchable Constants)
WEIGHT_PATTERN_REGEX: str = r'(\d+(?:\.\d+)?)'
SERIAL_PORT: str = 'COM6'
BAUD_RATE: int = 9600
SERIAL_TIMEOUT: int = 2

DEFAULT_WEIGHT = 0.0
COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


@dataclass
class WeightTotals:
    gross: float
    tare: float
    net: float


@dataclass
class AllocationData:
    weight: float
    bags: int
    totals: WeightTotals


class WeighbridgeTicket(models.Model):
    _name = 'weighbridge.ticket'
    _description = 'Weighbridge Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Weighbridge No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))

    # FIX: Rename string to Weighbridge Date
    date = fields.Date(string='Weighbridge Date', default=fields.Date.today(), required=True)

    gate_pass_id = fields.Many2one('gate.pass', string='Gate Pass')
    grn_inspection_id = fields.Many2one('grn.inspection', string='Inspection Ref')

    # FIX: Add related date fields for flawless traceability
    inspection_date = fields.Date(related='grn_inspection_id.inspection_date', string='Inspection Date', store=True,
                                  readonly=True)
    gate_pass_date = fields.Date(related='gate_pass_id.date', string='GP Date', store=True, readonly=True)

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract',
                                             related='grn_inspection_id.rice_sales_contract_id', store=True,
                                             readonly=True)
    vehicle_number = fields.Char(string='Vehicle No.', required=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)])
    packing_size = fields.Float(string='Packing Size')

    consignee_id = fields.Many2one('res.partner', string='Customer', domain=[('is_company', '=', True)],
                                   default=lambda self: self.env.company.partner_id.id)

    truck_type = fields.Many2one('master.truck.type', string='Truck Type')
    weighbridge_charges = fields.Float(string='Weighbridge Charges', compute='_compute_weighbridge_charges', store=True,
                                       readonly=False)

    gross_weight = fields.Float(string='First Weight (Kg)', default=DEFAULT_WEIGHT)
    tare_weight = fields.Float(string='Second Weight (Kg)', default=DEFAULT_WEIGHT)
    net_weight = fields.Float(string='Net Wt (Kg)', compute='_compute_net_weight', store=True, readonly=True)
    line_ids = fields.One2many('weighbridge.ticket.line', 'ticket_id', string='Allocation Lines')
    total_allocated_weight = fields.Float(string='Total Allocated (Kg)', compute='_compute_total_allocated_weight',
                                          store=True)
    time = fields.Char(string='Time', size=5, default=lambda self: datetime.now().strftime('%H:%M'))
    driver_selection = fields.Selection([('with_driver', 'With Driver'), ('without_driver', 'Without Driver')],
                                        default='without_driver')
    pass_type = fields.Selection([('inbound', 'Inbound'), ('return', 'Return')], string='Pass Type', default='inbound',
                                 tracking=True)

    weighbridge_type = fields.Selection([
        ('procurement', 'Procurement'),
        ('outbound', 'Outbound (Sales)'),
        ('manufacturing', 'Manufacturing')
    ], string='Weighbridge Type', default='procurement', required=True, tracking=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('unloading', 'Unloading'), ('confirmed', 'Confirmed'), ('return_pending', 'Pending'),
         ('cancel', 'Cancelled')], string='Status', default='draft', tracking=True)
    inspection_state = fields.Selection(related='grn_inspection_id.state', string='Inspection Status', readonly=True)
    inspection_remarks = fields.Html(related='grn_inspection_id.remarks', string="Inspection Remarks", readonly=True)

    gate_pass_remarks = fields.Html(related='gate_pass_id.remarks', string="Gate Pass Remarks", readonly=True)

    remarks = fields.Html(string='Remarks')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'WeighbridgeTicket':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('weighbridge.ticket') or _('New')
        return super().create(vals_list)

    @api.depends('gross_weight', 'tare_weight')
    def _compute_net_weight(self) -> None:
        for rec in self:
            rec.net_weight = abs(rec.gross_weight - rec.tare_weight)

    @api.depends('line_ids.allocated_weight')
    def _compute_total_allocated_weight(self) -> None:
        for rec in self:
            rec.total_allocated_weight = sum(rec.line_ids.mapped('allocated_weight'))

    @api.depends('truck_type')
    def _compute_weighbridge_charges(self) -> None:
        """Flow Fix: Auto-populate Weighbridge Charges directly from the MasterTruckType."""
        for rec in self:
            if rec.truck_type:
                rec.weighbridge_charges = rec.truck_type.weighbridge_charges
            else:
                rec.weighbridge_charges = 0.0

    def action_view_gate_pass(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('gate.pass', self.gate_pass_id.id, 'Gate Pass')

    @api.onchange('gate_pass_id')
    def _onchange_gate_pass_id(self) -> None:
        if not self.gate_pass_id:
            self.update({'grn_inspection_id': False, 'partner_id': False, 'vehicle_number': False,
                         'line_ids': [COMMAND_CLEAR_ALL]})
            return
        vals = self.gate_pass_id._prepare_weighbridge_vals()
        line_commands = vals.pop('line_ids', [])
        vals.pop('date', None)
        vals.pop('gross_weight', None)
        vals.pop('tare_weight', None)
        self.update(vals)
        self.line_ids = line_commands

    def action_view_purchase_order(self) -> Dict[str, Any]:
        self.ensure_one()
        first_po = self.line_ids[:1].purchase_order_id
        return self._open_form_view('purchase.order', first_po.id, 'Purchase Order')

    def action_view_inspection(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Inspection')

    def action_view_sales_contract(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('rice.sales.contract', self.rice_sales_contract_id.id, 'Rice Sales Contract')

    def _calculate_accumulated_weight_for_po(self, purchase_order: 'purchase.order') -> float:
        self.ensure_one()
        domain = [('purchase_order_id', '=', purchase_order.id), ('ticket_id.state', '=', 'confirmed')]
        confirmed_weight = sum(self.env['weighbridge.ticket.line'].search(domain).mapped('allocated_weight'))
        current_ticket_weight = sum(
            self.line_ids.filtered(lambda l: l.purchase_order_id == purchase_order).mapped('allocated_weight'))
        return confirmed_weight + current_ticket_weight

    def _validate_weight_allocation(self) -> None:
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("You must allocate the weight to Purchase Orders before confirming."))
        # FIX: Allow partial allocation (e.g., 2000kg material on a 5000kg truck).
        # Only block if allocated weight exceeds the net weight.
        if round(self.total_allocated_weight, 2) > round(self.net_weight, 2):
            raise ValidationError(_(
                "Total allocated weight (%(allocated)s kg) cannot exceed the Net Weight (%(net)s kg).",
                allocated=self.total_allocated_weight, net=self.net_weight
            ))

    def _get_picking_for_po(self, purchase_order: 'purchase.order') -> 'stock.picking':
        self.ensure_one()

        # 1. Try to find an existing draft/assigned/confirmed GRN that is not linked to another WB
        picking = self.env['stock.picking'].search([
            ('purchase_id', '=', purchase_order.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', 'in', ['assigned', 'confirmed', 'draft']),
            '|',
            ('weighbridge_id', '=', False),
            ('weighbridge_id', '=', self.id)
        ], limit=1, order='id asc')

        # 2. If not found, create a brand new one
        if not picking:
            po = purchase_order
            picking_type = po.picking_type_id or self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'), ('company_id', '=', self.env.company.id)
            ], limit=1)
            if not picking_type:
                raise UserError(_("Please configure an incoming picking type."))

            # FIX: Use only Destination Location from GRN Inspection if provided
            dest_location = self.grn_inspection_id.location_dest_id or picking_type.default_location_dest_id

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
            dest_location = self.grn_inspection_id.location_dest_id or picking.picking_type_id.default_location_dest_id
            if dest_location and picking.location_dest_id != dest_location:
                picking.write({
                    'location_dest_id': dest_location.id,
                })

        return picking

    def _update_picking_for_po(self, picking: 'stock.picking') -> None:
        self.ensure_one()
        # Write custom fields (Weighbridge ID, Bilty, Vehicle, etc.) to the picking
        picking.write(self._prepare_picking_update_vals(picking))

        for line in self.line_ids.filtered(lambda l: l.purchase_order_id == picking.purchase_id):
            # Find the exact move for this PO line that is not yet done
            move = picking.move_ids.filtered(
                lambda m: m.purchase_line_id == line.purchase_order_line_id and m.state not in ('done', 'cancel'))[:1]

            if not move:
                # Fallback: If move doesn't exist for some reason, create it
                move = self.env['stock.move'].create({
                    # FIX: Removed 'name' field as it is invalid in Odoo 19 stock.move
                    'product_id': line.product_id.id,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uom_qty': 0.0,  # Start with 0 demand
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'picking_id': picking.id,
                    'picking_type_id': picking.picking_type_id.id,
                    'purchase_line_id': line.purchase_order_line_id.id,
                    'origin': picking.origin,
                })
                move._action_confirm()

            # FIX: Update Demand to match Weighbridge exactly
            move.write({'product_uom_qty': line.allocated_weight})

            # FIX: Explicitly create/update the stock.move.line so it shows in Operations tab natively
            if move.move_line_ids:
                move.move_line_ids[:1].write({
                    'quantity': line.allocated_weight,
                    'product_uom_id': line.product_id.uom_id.id
                })
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_id.uom_id.id,
                    'quantity': line.allocated_weight,  # Set Done Quantity
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })

    # Fix 3A: Sums all bilty weights from the inspection lines instead of just the first one
    def _prepare_picking_update_vals(self, picking: 'stock.picking') -> Dict[str, Any]:
        self.ensure_one()
        inspection = self.grn_inspection_id
        gate_pass = self.gate_pass_id
        totals = WeightTotals(gross=self.gross_weight, tare=self.tare_weight, net=self.net_weight)

        vehicle_info = {
            'vehicle_number': gate_pass.vehicle_number if gate_pass else False,
            'driver_name': gate_pass.driver_name if gate_pass else False,
            'transporter_id': gate_pass.transporter_id.id if gate_pass else False,
            'truck_type': gate_pass.truck_type.id if gate_pass else False,
            'bilty_no': gate_pass.bilty_no if gate_pass else False,
        }

        total_bilty_weight = sum(inspection.inspection_line_ids.mapped('bilty_weight')) if inspection else 0.0

        weight_info = {
            'gross_weight': totals.gross,
            'tare_weight': totals.tare,
            'net_weight': totals.net,
            'bilty_weight': total_bilty_weight,
        }

        quality_info = {
            'actual_moisture': inspection.moisture_percent,
            'actual_broken': inspection.broken_percent,
        }

        return {
            'grn_inspection_id': inspection.id,
            'gate_pass_id': gate_pass.id if gate_pass else False,
            'weighbridge_id': self.id,
            'grn_date': fields.Date.today(),
            'product_id': inspection.inspection_line_ids[:1].product_id.id if inspection.inspection_line_ids else False,
            'bags': sum(self.line_ids.mapped('bags')),
            'remarks': self.remarks,
            **vehicle_info,
            **weight_info,
            **quality_info,
        }

    def _prepare_return_weighbridge_vals(self) -> Dict[str, Any]:
        self.ensure_one()
        wb_line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.line_ids.filtered(lambda l: l.purchase_order_id):
            wb_line_vals.append((COMMAND_CREATE_NEW, 0, {
                'purchase_order_id': line.purchase_order_id.id,
                'purchase_order_line_id': line.purchase_order_line_id.id,
                'product_id': line.product_id.id if line.product_id else False,
                'allocated_weight': line.allocated_weight,
                'bags': line.bags,
            }))
        return {
            'grn_inspection_id': self.grn_inspection_id.id,
            'partner_id': self.partner_id.id,
            'vehicle_number': self.vehicle_number,
            'truck_type': self.truck_type.id,
            'date': fields.Date.today(),
            'gross_weight': self.gross_weight,
            'tare_weight': 0.0,
            'state': 'unloading',
            'pass_type': 'return',
            'line_ids': wb_line_vals,
        }

    def _prepare_return_gate_pass_vals(self) -> Dict[str, Any]:
        self.ensure_one()
        gp_line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.line_ids.filtered(lambda l: l.purchase_order_id):
            gp_line_vals.append((COMMAND_CREATE_NEW, 0, {
                'purchase_order_id': line.purchase_order_id.id,
                'purchase_order_line_id': line.purchase_order_line_id.id,
                'product_id': line.product_id.id if line.product_id else False,
                'return_qty': line.allocated_weight,
                'gross': line.allocated_weight,
                'net': line.allocated_weight,
            }))
        return {
            'pass_type': 'return',
            'grn_inspection_id': self.grn_inspection_id.id,
            'partner_id': self.partner_id.id,
            'date': fields.Date.today(),
            'vehicle_number': self.vehicle_number,
            'gate_pass_line_ids': gp_line_vals,
        }

    def _create_return_picking(self, gate_pass: 'gate.pass') -> 'stock.picking':
        self.ensure_one()
        picking_type_out = self.env['stock.picking.type'].search(
            [('code', '=', 'outgoing'), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type_out:
            raise UserError(_("Please configure an outgoing picking type for returns."))

        move_lines: List[Tuple[int, int, Dict[str, Any]]] = []
        for line in self.line_ids:
            move_lines.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.allocated_weight,
                'quantity': line.allocated_weight,
                'location_id': picking_type_out.default_location_src_id.id,
                'location_dest_id': self.partner_id.property_stock_supplier.id,
                'purchase_line_id': line.purchase_order_line_id.id,
            }))

        unique_pos = self.line_ids.mapped('purchase_order_id')
        po_id = unique_pos.id if len(unique_pos) == 1 else False

        return self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type_out.id,
            'origin': f"Return: {self.name}",
            'purchase_id': po_id,
            'grn_inspection_id': self.grn_inspection_id.id,
            'gate_pass_id': gate_pass.id,
            'weighbridge_id': self.id,
            'move_ids': move_lines,
        })

    def action_start_unloading(self) -> None:
        for rec in self:
            if rec.gross_weight <= 0:
                raise UserError(_("You must capture the First Weight before starting unloading."))
            rec.state = 'unloading'

    # Fix 3C: Auto-distributes net weight across PO lines proportionally
    def action_auto_distribute_weight(self) -> None:
        self.ensure_one()
        if self.net_weight <= 0:
            raise UserError(_("Please capture both First and Second weights before distributing."))

        line_remaining = {}
        total_po_remaining = 0.0
        for line in self.line_ids:
            po_line = line.purchase_order_line_id
            rem = 0.0
            if po_line:
                rem = po_line.product_qty - po_line.qty_received
            line_remaining[line.id] = rem
            total_po_remaining += rem

        if total_po_remaining <= 0:
            raise UserError(_("There is no remaining quantity on the Purchase Orders to distribute."))

        allocated = 0.0
        lines = self.line_ids.sorted(key=lambda l: l.id)
        for i, line in enumerate(lines):
            if i == len(lines) - 1:
                line.allocated_weight = self.net_weight - allocated
            else:
                line.allocated_weight = round((line_remaining[line.id] / total_po_remaining) * self.net_weight, 2)
                allocated += line.allocated_weight

    def action_create_return_weighbridge(self) -> Dict[str, Any]:
        self.ensure_one()
        ticket = self.env['weighbridge.ticket'].create(self._prepare_return_weighbridge_vals())
        return self._open_form_view('weighbridge.ticket', ticket.id, 'Return Weighbridge')

    def action_create_return_gate_pass(self) -> Dict[str, Any]:
        self.ensure_one()
        self.state = 'confirmed'
        gate_pass = self.env['gate.pass'].create(self._prepare_return_gate_pass_vals())
        self.gate_pass_id = gate_pass.id

        return_picking = self._create_return_picking(gate_pass)
        return_picking.action_confirm()
        return_picking.action_assign()

        return self._open_form_view('gate.pass', gate_pass.id, 'Return Gate Pass')

    def action_confirm(self) -> Dict[str, Any]:
        self.ensure_one()
        if self.pass_type == 'return':
            raise UserError(_("Return tickets must use the 'Create Return Gate Pass' button."))

        self._validate_weight_allocation()

        # FIX: Enforce strict validation flow for Procurement
        if self.weighbridge_type == 'procurement':
            if self.inspection_state != 'final_pass':
                raise UserError(_("The linked GRN Inspection must pass Final QC before confirming this Weighbridge."))
            if self.gross_weight <= 0 or self.tare_weight <= 0:
                raise UserError(_("Please capture both First and Second weights before confirming."))

        # FIX: Outbound flow - Simply confirm and update Gate Pass to Exited
        if self.weighbridge_type == 'outbound':
            if self.gate_pass_id and self.gate_pass_id.state == 'confirmed':
                self.gate_pass_id.action_mark_exited()
            self.state = 'confirmed'
            return {'type': 'ir.actions.act_window_close'}

        # Procurement Flow
        picking_ids_updated: List[int] = []
        unique_pos = self.line_ids.mapped('purchase_order_id')
        for po in unique_pos:
            picking = self._get_picking_for_po(po)
            self._update_picking_for_po(picking)
            picking_ids_updated.append(picking.id)

        # Auto-mark the Gate Pass as Exited because the truck has successfully left
        if self.gate_pass_id and self.gate_pass_id.state == 'confirmed':
            self.gate_pass_id.action_mark_exited()

        self.state = 'confirmed'
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_incoming')
        action['domain'] = [('id', 'in', picking_ids_updated)]
        action['name'] = _('Updated GRNs')
        return action

    def action_proceed_final_qc(self) -> Dict[str, Any]:
        self.ensure_one()
        if self.grn_inspection_id:
            self.grn_inspection_id.action_start_final_qc()
            return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Final QC')
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'
            rec.gross_weight = DEFAULT_WEIGHT
            rec.tare_weight = DEFAULT_WEIGHT

    def _read_weight_from_weighbridge(self) -> float:
        """Protocol 4.2: Fully type-hinted with extracted constants."""
        self.ensure_one()
        try:
            ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUD_RATE, timeout=SERIAL_TIMEOUT)
            raw_data = ser.readline().decode(errors='ignore').strip()
            ser.close()
            if not raw_data:
                raise UserError(_("No data received from weighbridge."))
            match = re.search(WEIGHT_PATTERN_REGEX, raw_data)
            if not match:
                raise UserError(_("Invalid weighbridge data: %s") % raw_data)
            return float(match.group(1))
        except Exception as e:
            raise UserError(_("Weighbridge Error: %s") % str(e))

    def action_capture_gross_weight(self) -> None:
        self.ensure_one()
        self.gross_weight = self._read_weight_from_weighbridge()

    def action_capture_tare_weight(self) -> None:
        self.ensure_one()
        self.tare_weight = self._read_weight_from_weighbridge()


class WeighbridgeTicketLine(models.Model):
    _name = 'weighbridge.ticket.line'
    _description = 'Weighbridge Ticket Line'
    _inherit = 'purchase.order.line.mapper.mixin'

    ticket_id = fields.Many2one('weighbridge.ticket', string='Ticket', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    bags = fields.Integer(string='Bags')
    allocated_weight = fields.Float(string='Allocated Net Weight (Kg)', digits=(16, 3))

    additional_weight = fields.Float(string='Add. Wt', readonly=True)
    total_weight = fields.Float(string='Total Wt', readonly=True)

    def _apply_po_line_values(self, po_line: 'purchase.order.line') -> None:
        self.product_id = po_line.product_id
        self.bags = po_line.no_of_bags
        self.allocated_weight = po_line.product_qty