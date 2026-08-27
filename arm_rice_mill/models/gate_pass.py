# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple
from datetime import datetime

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class GatePass(models.Model):
    _name = 'gate.pass'
    _description = 'Gate Pass'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Gate Pass No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='GP Date', default=fields.Date.today(), required=True)
    inspection_date = fields.Date(related='grn_inspection_id.inspection_date', string='Inspection Date', store=True,
                                  readonly=True)
    time = fields.Char(string='Time', size=5, default=lambda self: datetime.now().strftime('%H:%M'))
    pass_type = fields.Selection([('inbound', 'Inbound'), ('outbound', 'Outbound'), ('return', 'Return')],
                                 string='Pass Type', required=True, default='inbound', tracking=True)

    grn_inspection_id = fields.Many2one('grn.inspection', string='Inspection Ref')

    # NEW: Export checkbox to toggle UI visibility
    is_export = fields.Boolean(string="Export Delivery")

    # LOCAL SALES: Sales Memo fields
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo Ref')
    sale_order_date = fields.Datetime(related='sale_order_id.date_order', string='Sales Memo Date', store=True,
                                      readonly=True)

    # EXPORT SALES: Sales Contract fields
    export_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract Ref')
    export_contract_date = fields.Date(related='export_sales_contract_id.contract_date', string='Sales Contract Date',
                                       store=True, readonly=True)

    delivery_picking_id = fields.Many2one('stock.picking', string='Delivery Order Ref')

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract',
                                             related='grn_inspection_id.rice_sales_contract_id', store=True,
                                             readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer / Supplier')
    vehicle_number = fields.Char(string='Vehicle No.', tracking=True)
    driver_name = fields.Char(string='Driver Name')
    transporter_id = fields.Many2one('res.partner', string='Transporter')
    container_no = fields.Char(string='Container No.')
    seal_no = fields.Char(string='Seal No.')
    gate_pass_line_ids = fields.One2many('gate.pass.line', 'gate_pass_id', string='GatePass Detail')
    gross_qty = fields.Float(string='Gross Qty', compute='_compute_qtys', store=True)
    net_qty = fields.Float(string='Net Qty', compute='_compute_qtys', store=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Exited'), ('cancel', 'Cancelled')], string='Status',
        default='draft', tracking=True)

    inspection_remarks = fields.Html(related='grn_inspection_id.remarks', string='Inspection Remarks', readonly=True)
    remarks = fields.Html(string='Remarks')

    weighbridge_count = fields.Integer(string='Weighbridges', compute='_compute_weighbridge_count')
    truck_type = fields.Many2one('master.truck.type', string='Truck Type')
    bilty_no = fields.Char(string='Bilty No.')

    is_third_party = fields.Boolean(related='grn_inspection_id.is_third_party', string='Third Party / Outsider',
                                    store=True, readonly=True)

    # NEW: Outbound Quality Checkmarks
    check_rice_quality = fields.Boolean(string='Rice Quality')
    check_packaging_condition = fields.Boolean(string='Packaging Condition')
    check_fumigation = fields.Boolean(string='Fumigation')
    check_weevils = fields.Boolean(string='Weevils')
    check_vehicle_condition = fields.Boolean(string='Vehicle Condition')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'GatePass':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('gate.pass') or _('New')
        return super().create(vals_list)

    @api.depends('gate_pass_line_ids.gross', 'gate_pass_line_ids.net')
    def _compute_qtys(self) -> None:
        for rec in self:
            rec.gross_qty = sum(line.gross for line in rec.gate_pass_line_ids)
            rec.net_qty = sum(line.net for line in rec.gate_pass_line_ids)

    def _compute_weighbridge_count(self) -> None:
        counts = self._get_related_record_count_batch('weighbridge.ticket', 'gate_pass_id')
        for rec in self:
            rec.weighbridge_count = counts.get(rec.id, 0)

    def action_view_purchase_order(self) -> Dict[str, Any]:
        self.ensure_one()
        first_po = self.gate_pass_line_ids[:1].purchase_order_id
        return self._open_form_view('purchase.order', first_po.id, 'Purchase Order')

    def action_view_inspection(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Inspection')

    def action_view_weighbridges(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('weighbridge.ticket', 'gate_pass_id', 'Weighbridge')

    def _prepare_weighbridge_vals(self) -> Dict[str, Any]:
        self.ensure_one()

        # FIX: Handle Outbound (Sales) Gate Pass
        if self.pass_type == 'outbound':
            line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
            for gp_line in self.gate_pass_line_ids:
                line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'sale_order_id': self.sale_order_id.id,
                    'sale_line_id': gp_line.sale_line_id.id,
                    'product_id': gp_line.product_id.id if gp_line.product_id else False,
                    'bags': gp_line.bags,
                    'allocated_weight': 0.0,
                    'additional_weight': gp_line.additional_weight,
                    'total_weight': gp_line.total_weight,
                }))
            return {
                'weighbridge_type': 'outbound',
                'gate_pass_id': self.id,
                'sale_order_id': self.sale_order_id.id,
                'delivery_picking_id': self.delivery_picking_id.id,
                'partner_id': self.partner_id.id,
                'vehicle_number': self.vehicle_number,
                'truck_type': self.truck_type.id,
                'date': fields.Date.today(),
                'gross_weight': 0.0,
                'tare_weight': 0.0,
                'line_ids': line_vals,
            }

        # Existing Procurement logic
        line_vals: List[Tuple[int, int, Dict[str, Any]]] = []
        for gp_line in self.gate_pass_line_ids.filtered(lambda l: l.purchase_order_id):
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'purchase_order_id': gp_line.purchase_order_id.id,
                'purchase_order_line_id': gp_line.purchase_order_line_id.id,
                'product_id': gp_line.product_id.id if gp_line.product_id else False,
                'bags': gp_line.bags,
                'allocated_weight': 0.0,
            }))

        return {
            'gate_pass_id': self.id,
            'grn_inspection_id': self.grn_inspection_id.id,
            'partner_id': self.partner_id.id,
            'vehicle_number': self.vehicle_number,
            'truck_type': self.truck_type.id,
            'date': fields.Date.today(),
            'gross_weight': 0.0,
            'tare_weight': 0.0,
            'line_ids': line_vals,
        }

    @api.onchange('grn_inspection_id')
    def _onchange_grn_inspection_id(self) -> None:
        if not self.grn_inspection_id:
            self.update({
                'partner_id': False,
                'vehicle_number': False,
                'truck_type': False,
                'bilty_no': False,
                'gate_pass_line_ids': [COMMAND_CLEAR_ALL],
            })
            return

        vals = self.grn_inspection_id._prepare_gate_pass_vals()
        line_commands = vals.pop('gate_pass_line_ids', [])
        line_commands.insert(0, COMMAND_CLEAR_ALL)
        self.update(vals)
        self.gate_pass_line_ids = line_commands

    @api.onchange('delivery_picking_id')
    def _onchange_delivery_picking_id_outbound(self) -> None:
        """Protocol 2.1: Auto-populate Gate Pass from selected Delivery Order."""
        if not self.delivery_picking_id or self.pass_type != 'outbound':
            return

        picking = self.delivery_picking_id
        self.sale_order_id = picking.sale_id.id

        # If Export, safely auto-map the Sales Contract from the Delivery Order's Sale Order
        if self.is_export and picking.sale_id and 'rice_sales_contract_id' in picking.sale_id._fields:
            if picking.sale_id.rice_sales_contract_id:
                self.export_sales_contract_id = picking.sale_id.rice_sales_contract_id.id

        line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            sale_line = move.sale_line_id
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'sale_order_id': picking.sale_id.id,
                'sale_line_id': sale_line.id if sale_line else False,
                'product_id': move.product_id.id,
                'do_demand_qty': move.quantity,
                'location_dest_id': move.location_dest_id.id,
                'return_qty': move.product_uom_qty,
                'pcs': move.pcs or 0.0,
                'ctn': move.ctn or 0.0,
                'gross': 0.0,
                'net': 0.0,
                'additional_weight': move.additional_weight or 0.0,
                'total_weight': move.total_weight or 0.0,
            }))
        self.gate_pass_line_ids = line_vals

    def action_create_weighbridge(self) -> Dict[str, Any]:
        self.ensure_one()

        # FIX: Enforce strict validation flow
        if self.state != 'confirmed':
            raise UserError(_("Please validate the Gate Pass before creating a Weighbridge Ticket."))

        if self.grn_inspection_id and self.grn_inspection_id.is_third_party:
            self.grn_inspection_id.action_start_final_qc()
            return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Inspection')

        existing_ticket = self.env['weighbridge.ticket'].search([('gate_pass_id', '=', self.id)], limit=1)
        if existing_ticket:
            return self._open_form_view('weighbridge.ticket', existing_ticket.id, 'Weighbridge Ticket')
        ticket = self.env['weighbridge.ticket'].create(self._prepare_weighbridge_vals())
        return self._open_form_view('weighbridge.ticket', ticket.id, 'Weighbridge Ticket')

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.vehicle_number:
                raise UserError(_("You must enter a Vehicle No. before confirming the Gate Pass."))
            rec.state = 'confirmed'

            # FIX: Link Gate Pass to Delivery Order so it can be validated
            if rec.pass_type == 'outbound' and rec.delivery_picking_id:
                rec.delivery_picking_id.gate_pass_id = rec.id

    def action_mark_exited(self) -> None:
        for rec in self: rec.state = 'done'

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'


class GatePassLine(models.Model):
    _name = 'gate.pass.line'
    _description = 'Gate Pass Line'
    _order = 'id asc'
    _inherit = 'purchase.order.line.mapper.mixin'

    gate_pass_id = fields.Many2one('gate.pass', string='Gate Pass', required=True, ondelete='cascade')
    return_reference = fields.Char(string='GRet No', compute='_compute_return_reference', store=True)
    product_id = fields.Many2one('product.product', string='Item Name')
    return_qty = fields.Float(string='Qty')
    balance = fields.Float(string='Balance')
    carton = fields.Integer(string='Carton')
    bags = fields.Integer(string='Bags')
    gross = fields.Float(string='Gross')
    net = fields.Float(string='Net')

    # NEW: Sales Memo Line fields (Kept in DB for Weighbridge mapping, hidden in UI)
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Memo Line')

    do_demand_qty = fields.Float(string='D/O Qty')
    location_dest_id = fields.Many2one('stock.location', string='Location')

    additional_weight = fields.Float(string='Add. Wt')
    total_weight = fields.Float(string='Total Wt')

    pcs = fields.Float(string='PCS')
    ctn = fields.Float(string='CTN')
    packing_type = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('china_cotton', 'China Cotton')
    ], string='Packing Type')

    job_no = fields.Char(string='Job No.')
    batch_no = fields.Char(string='Batch No.')

    def _apply_po_line_values(self, po_line: 'purchase.order.line') -> None:
        self.product_id = po_line.product_id
        self.return_qty = po_line.product_qty
        self.gross = po_line.product_qty
        self.net = po_line.product_qty
        self.bags = po_line.no_of_bags

    @api.depends('gate_pass_id', 'gate_pass_id.gate_pass_line_ids')
    def _compute_return_reference(self) -> None:
        for rec in self:
            if not rec.gate_pass_id:
                rec.return_reference = False
                continue
            all_lines = rec.gate_pass_id.gate_pass_line_ids.sorted(key=lambda r: r.id)
            line_index = {line.id: idx for idx, line in enumerate(all_lines, start=1)}
            rec.return_reference = str(line_index.get(rec.id, ''))