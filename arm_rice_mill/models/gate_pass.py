# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple
from datetime import datetime

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Gate Pass states (Protocol 1.3) ---
GATE_PASS_CONFIRMED_STATE: str = 'confirmed'


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
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer / Supplier',
        domain="partner_id_domain",  # dynamic by pass_type / is_export
    )
    vehicle_number = fields.Char(string='Vehicle No.', tracking=True)
    driver_name = fields.Char(string='Driver Name')
    driver_cnic = fields.Char(string='Driver CNIC')
    driver_cell_phone = fields.Char(string='Driver Cell Phone')
    transporter_id = fields.Many2one('res.partner', string='Transporter')
    container_no = fields.Char(string='Container No.')
    seal_no = fields.Char(string='Seal No.')
    gate_pass_line_ids = fields.One2many('gate.pass.line', 'gate_pass_id', string='GatePass Detail')

    # REQUIREMENT (GP weights <- Weighbridge, on the LINES): the lines carry
    # the actual weighed quantities, mapped from the confirmed Weighbridge
    # (apply_ticket_line_weights). The header is their auto-sum - the
    # original design, restored - so there is exactly one mapping target
    # and one source of truth.
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
        """Header totals = the sum of the line weights (original design,
        restored). The lines carry the Weighbridge's actual weights."""
        for rec in self:
            rec.gross_qty = sum(line.gross for line in rec.gate_pass_line_ids)
            rec.net_qty = sum(line.net for line in rec.gate_pass_line_ids)

    @api.depends('pass_type', 'is_export')
    def _compute_partner_id_domain(self) -> None:
        """Dynamic domain on the Customer / Supplier field by pass type:
        - Outbound + Export: Export Customer only
        - Outbound + Local:  Customer only
        - Inbound:           Vendor and Broker
        - Return:            all partners (picking up vendors for returns)
        Computed field approach: the domain lives in the FIELD definition,
        re-evaluated whenever pass_type / is_export changes - no XML
        coupling, one source of truth."""
        for rec in self:
            if rec.pass_type == 'outbound':
                if rec.is_export:
                    rec.partner_id_domain = json.dumps(
                        [('partner_assign_type', '=', 'export_customer')])
                else:
                    rec.partner_id_domain = json.dumps(
                        [('partner_assign_type', '=', 'customer')])
            elif rec.pass_type == 'inbound':
                rec.partner_id_domain = json.dumps(
                    [('partner_assign_type', '=', 'vendor')])
            else:
                rec.partner_id_domain = json.dumps([])

    partner_id_domain = fields.Char(compute='_compute_partner_id_domain')

    # ==========================================================
    # WEIGHBRIDGE SMART BUTTON (requirement: the button sees a ticket
    # from the moment it is created against this Gate Pass - through
    # EITHER existing link)
    # ==========================================================

    def _get_linked_weighbridge_tickets(self) -> 'weighbridge.ticket':
        """Protocol 4.1 (DRY): every Weighbridge Ticket linked to these Gate
        Passes, through either existing link:
        - the direct link (ticket.gate_pass_id): procurement, manufacturing
          and Gate-Pass-created tickets;
        - the outbound m2m (ticket.gate_pass_ids): Weighbridge-first tickets."""
        return self.env['weighbridge.ticket'].search([
            '|',
            ('gate_pass_id', 'in', self.ids),
            ('gate_pass_ids', 'in', self.ids),
        ])

    def _compute_weighbridge_count(self) -> None:
        """Smart button count over BOTH links. The link exists from the
        moment the ticket is created against the Gate Pass - it does not
        wait for the ticket's confirmation."""
        linked_tickets = self._get_linked_weighbridge_tickets()
        for gate_pass in self:
            gate_pass.weighbridge_count = len(linked_tickets.filtered(
                lambda ticket: ticket.gate_pass_id == gate_pass
                or gate_pass in ticket.gate_pass_ids
            ))

    def action_view_weighbridges(self) -> Dict[str, Any]:
        """Open the linked Weighbridge Tickets: single -> its form,
        several -> the filtered list."""
        self.ensure_one()
        tickets = self._get_linked_weighbridge_tickets()
        if not tickets:
            return {'type': 'ir.actions.act_window_close'}
        if len(tickets) == 1:
            return self._open_form_view('weighbridge.ticket', tickets.id, 'Weighbridge')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Weighbridges',
            'res_model': 'weighbridge.ticket',
            'view_mode': 'list,form',
            'domain': [('id', 'in', tickets.ids)],
            'target': 'current',
        }

    def action_view_purchase_order(self) -> Dict[str, Any]:
        self.ensure_one()
        first_po = self.gate_pass_line_ids[:1].purchase_order_id
        return self._open_form_view('purchase.order', first_po.id, 'Purchase Order')

    def action_view_inspection(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Inspection')

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

    # ==========================================================
    # WEIGHBRIDGE WEIGHT MAPPING (requirement: the confirmed
    # Weighbridge's weights land on the LINES; the header totals
    # follow automatically via _compute_qtys)
    # ==========================================================

    def apply_ticket_line_weights(self, ticket: 'weighbridge.ticket') -> None:
        """Map the confirmed Weighbridge's weights onto this Gate Pass's lines.

        Line net  = the line's allocated weight.
        Line gross = the same share of the truck's LOADED weight (the tare
        distributed proportionally), so a single-line Gate Pass shows exactly
        the ticket's loaded / net weights, and multi-line Gate Passes rebuild
        the truck totals when summed.

        Lines with no allocation on this truck are zeroed: an exited Gate
        Pass must not keep showing expected quantities as if they were
        actuals. A fresh Gate Pass keeps its 0s until confirmation."""
        loaded_weight = max(ticket.gross_weight, ticket.tare_weight)
        tare_ratio = loaded_weight / ticket.net_weight if ticket.net_weight > 0 else 1.0

        for gate_pass in self:
            matched_lines = self.env['gate.pass.line']
            for wb_line in ticket.line_ids.filtered(lambda line: line.allocated_weight > 0):
                gp_line = gate_pass._match_gate_pass_line(wb_line, matched_lines)
                if not gp_line:
                    continue
                line_vals: Dict[str, float] = {
                    'gross': round(wb_line.allocated_weight * tare_ratio, 3),
                    'net': wb_line.allocated_weight,
                }
                if wb_line.bags:
                    line_vals['bags'] = wb_line.bags
                gp_line.write(line_vals)
                matched_lines |= gp_line

            unmatched_lines = gate_pass.gate_pass_line_ids - matched_lines
            if unmatched_lines:
                unmatched_lines.write({'gross': 0.0, 'net': 0.0, 'bags': 0})

    def apply_divided_ticket_weights(self, ticket: 'weighbridge.ticket') -> None:
        """Shared-truck rule (requirement): every Gate Pass on the ticket
        receives an EQUAL share of the truck's weights - loaded gross and
        net, each divided by the number of Gate Passes on the recordset.
        A single selected Gate Pass therefore receives the full weights.

        Each Gate Pass's share is distributed across its lines
        proportionally to the weights actually loaded for them (matched
        Weighbridge allocations); lines with no allocation are zeroed. When
        nothing matches, the share is split equally across the lines so the
        Gate Pass still shows its part of the truck."""
        gate_pass_count = len(self)
        if gate_pass_count <= 0:
            return
        loaded_weight = max(ticket.gross_weight, ticket.tare_weight)
        share_gross = loaded_weight / gate_pass_count
        share_net = ticket.net_weight / gate_pass_count

        for gate_pass in self:
            lines = gate_pass.gate_pass_line_ids
            if not lines:
                continue

            matched_lines = self.env['gate.pass.line']
            line_allocations: Dict[int, float] = {}
            for wb_line in ticket.line_ids.filtered(lambda line: line.allocated_weight > 0):
                gp_line = gate_pass._match_gate_pass_line(wb_line, matched_lines)
                if not gp_line:
                    continue
                line_allocations[gp_line.id] = wb_line.allocated_weight
                if wb_line.bags:
                    gp_line.write({'bags': wb_line.bags})
                matched_lines |= gp_line

            total_allocated = sum(line_allocations.values())
            if total_allocated > 0:
                for line in lines:
                    allocation = line_allocations.get(line.id, 0.0)
                    if allocation > 0:
                        line.write({
                            'gross': round(share_gross * allocation / total_allocated, 3),
                            'net': round(share_net * allocation / total_allocated, 3),
                        })
                    else:
                        line.write({'gross': 0.0, 'net': 0.0, 'bags': 0})
            else:
                # No allocation matched this Gate Pass: its selected share
                # is still its own - split equally across its lines.
                line_count = len(lines)
                for line in lines:
                    line.write({
                        'gross': round(share_gross / line_count, 3),
                        'net': round(share_net / line_count, 3),
                    })

    def _match_gate_pass_line(self, wb_line: 'weighbridge.ticket.line',
                              matched_lines: 'gate.pass.line') -> 'gate.pass.line':
        """Match one Weighbridge line to its (not-yet-written) Gate Pass line:
        Purchase Order line first (procurement), then Sales Memo line
        (outbound), then product. Weighbridge lines belonging to another
        Gate Pass's Delivery Order never match. Sales-module fields are
        guarded so the matcher also works without arm_sales_management."""
        self.ensure_one()
        candidates = self.gate_pass_line_ids - matched_lines
        if not candidates:
            return self.env['gate.pass.line']

        if wb_line.purchase_order_line_id:
            by_po_line = candidates.filtered(
                lambda gp: gp.purchase_order_line_id == wb_line.purchase_order_line_id)
            if by_po_line:
                return by_po_line[:1]

        wb_sale_line = wb_line.sale_line_id if 'sale_line_id' in wb_line._fields else False
        if wb_sale_line:
            by_sale_line = candidates.filtered(lambda gp: gp.sale_line_id == wb_sale_line)
            if by_sale_line:
                return by_sale_line[:1]

        wb_delivery = (wb_line.delivery_picking_id
                       if 'delivery_picking_id' in wb_line._fields else False)
        if wb_delivery and self.delivery_picking_id and wb_delivery != self.delivery_picking_id:
            return self.env['gate.pass.line']

        by_product = candidates.filtered(lambda gp: gp.product_id == wb_line.product_id)
        return by_product[:1]

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

    additional_weight = fields.Float(string='Add. Wt (g)')
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
        # Requirement: actual weights are mapped from the Weighbridge at
        # confirmation - a fresh Gate Pass carries none.
        self.gross = 0.0
        self.net = 0.0
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