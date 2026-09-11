# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Any, Dict, List, Tuple

from .delivery_order import (
    BYPASS_COMMERCIAL_CHECK,
    QUANTITY_PRECISION,
)

# --- ORM Command Constants (Protocol 1.3) ---
COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Validation wizards we can safely auto-process ---
VALIDATION_WIZARD_MODELS: Tuple[str, ...] = ('stock.immediate.transfer', 'stock.backorder.confirmation')

OUTBOUND_WEIGHBRIDGE_TYPE: str = 'outbound'
GATE_PASS_CONFIRMED_STATE: str = 'confirmed'


class WeighbridgeTicketOutbound(models.Model):
    _inherit = 'weighbridge.ticket'

    # FIX: Use selection_add to inject the 'outbound' option cleanly
    weighbridge_type = fields.Selection(
        selection_add=[('outbound', 'Outbound (Sales)')],
        ondelete={'outbound': 'set default'}
    )

    # ==========================================================
    # OUTBOUND SURFACE: multiple Gate Passes (one truck carrying
    # goods for several Delivery Orders / customers).
    # Only CONFIRMED (not Exited) outbound Gate Passes are offered.
    # ==========================================================
    gate_pass_ids = fields.Many2many(
        'gate.pass',
        'wb_ticket_outbound_gp_rel',
        'ticket_id',
        'gate_pass_id',
        string='Gate Pass Refs',
        domain="[('pass_type', '=', 'outbound'), ('state', '=', 'confirmed')]",
        help="The confirmed Outbound Gate Passes carried by this truck. "
             "Search by Vehicle No. or Gate Pass No.",
    )

    # Multiple GPs -> multiple customers: derived tags display.
    outbound_partner_ids = fields.Many2many(
        'res.partner',
        compute='_compute_outbound_partners',
        string='Customers',
    )

    # MACHINERY (hidden in the view): kept for compatibility with legacy
    # records and programmatic paths. The outbound flow is GP-driven now.
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo Ref')
    delivery_picking_id = fields.Many2one(
        'stock.picking', string='Delivery Order Ref',
        domain="['&', ('picking_type_code', '=', 'outgoing'), "
               "('state', 'not in', ['done', 'cancel']), "
               "'|', ('contract_type', '=', 'export'), ('is_commercially_validated', '=', True)]"
    )

    @api.depends('gate_pass_ids.partner_id')
    def _compute_outbound_partners(self) -> None:
        """Protocol 2.1 (SRP): every selected Gate Pass's customer, as tags."""
        for rec in self:
            rec.outbound_partner_ids = rec.gate_pass_ids.mapped('partner_id')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'WeighbridgeTicketOutbound':
        records = super().create(vals_list)
        for rec in records:
            if rec.weighbridge_type == OUTBOUND_WEIGHBRIDGE_TYPE:
                # Server-side twin: lines follow the selected Gate Passes when
                # the caller (import/API) supplied none (onchanges never run
                # on programmatic creation).
                if rec.gate_pass_ids and not rec.line_ids:
                    rec._sync_lines_from_gate_passes()
                rec._resolve_outbound_do_lines()
        return records

    @api.onchange('weighbridge_type')
    def _onchange_weighbridge_type_outbound(self) -> None:
        """Protocol 2.1: Clear fields when switching types."""
        if self.weighbridge_type == OUTBOUND_WEIGHBRIDGE_TYPE:
            self.grn_inspection_id = False
            self.rice_sales_contract_id = False
            self.partner_id = False
            self.vehicle_number = False
            self.line_ids = [COMMAND_CLEAR_ALL]
        else:
            self.gate_pass_ids = [(5, 0, 0)]

    # ==========================================================
    # GATE PASS SELECTION -> LINES
    # ==========================================================

    def _build_lines_from_gate_passes(self) -> List[Tuple[int, int, Dict[str, Any]]]:
        """Protocol 2.1 (SRP) & 4.1 (DRY): one WB line per Gate Pass line,
        each carrying its own Delivery Order. Typed allocations for surviving
        (D/O + Sale Line) pairs are preserved on re-selection."""
        self.ensure_one()

        # Preservation map: (delivery_picking_id, sale_line_id) -> allocated weight.
        preservation_map: Dict[Tuple[int, int], float] = {}
        for line in self.line_ids:
            if line.delivery_picking_id and line.sale_line_id and line.allocated_weight > 0:
                preservation_map[(line.delivery_picking_id.id, line.sale_line_id.id)] = line.allocated_weight

        commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for gate_pass in self.gate_pass_ids:
            for gp_line in gate_pass.gate_pass_line_ids:
                line_key = (gate_pass.delivery_picking_id.id, gp_line.sale_line_id.id)
                commands.append((COMMAND_CREATE_NEW, 0, {
                    'sale_order_id': gate_pass.sale_order_id.id,
                    'sale_line_id': gp_line.sale_line_id.id,
                    'product_id': gp_line.product_id.id,
                    'delivery_picking_id': gate_pass.delivery_picking_id.id,
                    'allocated_weight': preservation_map.get(line_key, 0.0),
                }))
        return commands

    def _sync_lines_from_gate_passes(self) -> None:
        """Server-side twin of the GP-selection onchange (create path)."""
        self.ensure_one()
        self.line_ids = self._build_lines_from_gate_passes()

    @api.onchange('gate_pass_ids')
    def _onchange_gate_pass_ids_outbound(self) -> None:
        """Protocol 2.1: Gate Passes selected -> one line per GP line, each
        mapped to its own Delivery Order. Customers follow the GPs."""
        if self.weighbridge_type != OUTBOUND_WEIGHBRIDGE_TYPE:
            return

        if not self.gate_pass_ids:
            self.line_ids = [COMMAND_CLEAR_ALL]
            self.partner_id = False
            return

        # Machinery: base partner = first GP's customer (record consistency).
        self.partner_id = self.gate_pass_ids[0].partner_id.id
        self.line_ids = self._build_lines_from_gate_passes()
        self._resolve_outbound_do_lines()

    def _resolve_outbound_do_lines(self) -> None:
        """Protocol 2.1 (SRP): map each line to its OWN Delivery Order's move
        (the line carries the D/O from its Gate Pass):
        - do_qty:        the approved commercial D/O Qty (what User A entered)
        - do_demand_qty: the move's demand - the allocation ceiling."""
        self.ensure_one()

        for line in self.line_ids:
            do_picking = line.delivery_picking_id
            if not do_picking or not line.sale_line_id:
                continue

            do_move = self.env['stock.move'].search([
                ('picking_id', '=', do_picking.id),
                ('sale_line_id', '=', line.sale_line_id.id)
            ], limit=1)

            if do_move:
                line.write({
                    'delivery_picking_id': do_picking.id,
                    'do_line_id': do_move.id,
                    'do_qty': do_move._get_commercial_basis_qty(),
                    'do_demand_qty': do_move.product_uom_qty,
                })

    # ==========================================================
    # CONFIRMATION PIPELINE (USER B): per Delivery Order
    # ==========================================================

    def _get_allocated_delivery_pickings(self) -> 'stock.picking':
        """Protocol 4.1 (DRY): the Delivery Orders that received allocation."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda line: line.allocated_weight > 0 and line.delivery_picking_id
        ).mapped('delivery_picking_id')

    def action_confirm_outbound(self) -> None:
        """Complete the Outbound process, one responsibility per step."""
        for rec in self:
            rec._check_outbound_confirmation_readiness()
            rec._validate_weight_allocation()
            rec._sync_delivery_order_moves()
            rec._sync_gate_pass_weights()
            rec._process_delivery_validations()
            rec.state = 'confirmed'

    def _check_outbound_confirmation_readiness(self) -> None:
        """Protocol 2.1: Ordered fast-fail checklist, each with a specific, actionable message."""
        self.ensure_one()

        if self.tare_weight <= 0:
            raise UserError(_("Please capture the Second Weight before confirming."))

        if not self.gate_pass_ids:
            raise UserError(_("Select at least one confirmed Outbound Gate Pass before confirming."))

        for gate_pass in self.gate_pass_ids:
            if gate_pass.state != GATE_PASS_CONFIRMED_STATE:
                raise UserError(_(
                    "Gate Pass %s is no longer Confirmed (current state: %s). "
                    "It may have been exited or cancelled elsewhere - remove it from this ticket.",
                    gate_pass.name, gate_pass.state,
                ))

        unmapped_lines = self.line_ids.filtered(
            lambda line: line.allocated_weight > 0 and not line.do_line_id)
        if unmapped_lines:
            raise UserError(_(
                "Line for product %s has an allocated weight but is not mapped to a "
                "Delivery Order move. Its Gate Pass needs a Delivery Order reference.",
                unmapped_lines[:1].product_id.display_name,
            ))

        allocated_pickings = self._get_allocated_delivery_pickings()
        if not allocated_pickings:
            raise UserError(_("Allocate a positive Net Weight to at least one line before confirming."))

        for picking in allocated_pickings:
            if not picking._is_local_sale_delivery():
                continue
            if not picking.is_commercially_validated:
                raise UserError(_(
                    "Delivery Order %s is not commercially validated yet. "
                    "The Sales user must approve the D/O Qty before the Weighbridge can confirm.",
                    picking.name,
                ))
            tracked_lines = self.line_ids.filtered(
                lambda line: line.allocated_weight > 0
                and line.delivery_picking_id == picking
                and line.product_id.tracking != 'none'
            )
            if tracked_lines:
                raise UserError(_(
                    "Lot/serial tracked products on Delivery Order %s cannot be auto-validated yet: %s. "
                    "Assign lots on the Delivery Order manually or contact your administrator.",
                    picking.name,
                    ", ".join(tracked_lines.mapped('product_id.display_name')),
                ))

    def _validate_weight_allocation(self) -> None:
        """Outbound allocation rules: no negatives, at least one positive, none above demand.
        Zero lines are tolerated (product simply not on this truck)."""
        super()._validate_weight_allocation()
        for rec in self:
            if rec.weighbridge_type != OUTBOUND_WEIGHBRIDGE_TYPE:
                continue

            negative_lines = rec.line_ids.filtered(lambda line: line.allocated_weight < 0)
            if negative_lines:
                raise ValidationError(_(
                    "Allocated Net Weight cannot be negative for product %(product)s.",
                    product=negative_lines[:1].product_id.display_name,
                ))

            allocated_lines = rec.line_ids.filtered(lambda line: line.allocated_weight > 0)
            if not allocated_lines:
                raise ValidationError(
                    _("Allocate a positive Net Weight to at least one product before confirming.")
                )

            for line in allocated_lines:
                if line.allocated_weight > line.do_demand_qty:
                    raise ValidationError(_(
                        "Allocated Net Weight (%(allocated)s kg) for %(product)s cannot exceed "
                        "the Demand Qty (%(demand)s kg).",
                        allocated=line.allocated_weight,
                        product=line.product_id.display_name,
                        demand=line.do_demand_qty,
                    ))

    def _sync_delivery_order_moves(self) -> None:
        """Protocol 2.1 (SRP): update every line's Delivery Order move with its
        allocated weight - across ALL Delivery Orders on this ticket."""
        self.ensure_one()

        for line in self.line_ids:
            if line.allocated_weight > 0 and line.do_line_id:
                line.do_line_id.write({
                    'quantity': line.allocated_weight,
                    'picked': True
                })

    def _sync_gate_pass_weights(self) -> None:
        """Protocol 2.1 (SRP): per-product weights on every selected Gate Pass's
        lines, then mark each Confirmed Gate Pass as Exited."""
        self.ensure_one()

        for gate_pass in self.gate_pass_ids:
            gp_picking = gate_pass.delivery_picking_id
            for gp_line in gate_pass.gate_pass_line_ids:
                wb_line = self.line_ids.filtered(
                    lambda line: line.allocated_weight > 0
                    and (not gp_picking or line.delivery_picking_id == gp_picking)
                    and (line.sale_line_id == gp_line.sale_line_id
                         or (not line.sale_line_id and line.product_id == gp_line.product_id))
                )[:1]
                if wb_line:
                    gp_line.gross = wb_line.allocated_weight
                    gp_line.net = wb_line.allocated_weight

            if gate_pass.state == GATE_PASS_CONFIRMED_STATE:
                gate_pass.action_mark_exited()

    def _process_delivery_validations(self) -> None:
        """Protocol 2.1 (SRP): validate EVERY allocated Delivery Order.
        Local sales DOs: bypassed validation + commercial accumulation +
        backorder recompute, each per its own allocated weights.
        Export DOs: untouched here (native manual validation), as before."""
        self.ensure_one()

        for picking in self._get_allocated_delivery_pickings():
            if not picking._is_local_sale_delivery():
                continue
            self._process_delivery_validation(picking)
            self._accumulate_commercial_quantities(picking)
            self._refresh_open_delivery_demand(picking)

    def _process_delivery_validation(self, picking: 'stock.picking') -> None:
        """Protocol 2.1 (SRP): trigger the real (bypassed) validation for ONE
        Delivery Order and digest any wizards."""
        bypassed_picking = picking.with_context(**{BYPASS_COMMERCIAL_CHECK: True})
        validation_result = bypassed_picking.button_validate()
        self._process_validation_wizards(validation_result)

    def _process_validation_wizards(self, validation_result: Any) -> None:
        """Protocol 4.1 (DRY): Wizard digestion in one place."""
        self.ensure_one()
        while (isinstance(validation_result, dict)
               and validation_result.get('res_model') in VALIDATION_WIZARD_MODELS):
            wizard = self.env[validation_result['res_model']].with_context(
                validation_result.get('context', {})
            ).create({})
            validation_result = wizard.process()

        if isinstance(validation_result, dict):
            raise UserError(_(
                "An unexpected validation dialog appeared. Please finish validating "
                "Delivery Order %s manually.",
                self.delivery_picking_id.name,
            ))

    def _accumulate_commercial_quantities(self, picking: 'stock.picking') -> None:
        """Per-product accumulation for ONE Delivery Order - fixes
        double-counting on multi-product / split-move DOs."""
        self.ensure_one()
        delivered_moves = picking.move_ids.filtered(
            lambda move: move.state == 'done' and move.sale_line_id and move.commercial_quantity > 0
        )
        for move in delivered_moves:
            move.sale_line_id.commercial_delivered_qty += move.commercial_quantity

    def _refresh_open_delivery_demand(self, picking: 'stock.picking') -> None:
        """Invariant A as a recompute for ONE Delivery Order's Sale lines:
        open demand = memo qty - commercial delivered. Idempotent."""
        self.ensure_one()
        sale_lines = picking.move_ids.mapped('sale_line_id')

        for line in sale_lines:
            remaining_qty = max(0.0, line.product_uom_qty - line.commercial_delivered_qty)
            open_moves = line.move_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            ).sorted(key=lambda move: move.id)

            if not open_moves:
                continue

            if remaining_qty <= 0:
                # Fully delivered commercially: the leftover backorder has no purpose.
                open_moves.mapped('picking_id').filtered(
                    lambda open_picking: open_picking.state not in ('done', 'cancel')
                ).action_cancel()
                continue

            distributed_qty = 0.0
            move_count = len(open_moves)
            for index, move in enumerate(open_moves):
                is_last_move = index == move_count - 1
                share_qty = round(remaining_qty / move_count, QUANTITY_PRECISION)
                move.product_uom_qty = remaining_qty - distributed_qty if is_last_move else share_qty
                distributed_qty += share_qty
                move.picked = False

            open_moves.mapped('picking_id').filtered(
                lambda open_picking: open_picking.state not in ('done', 'cancel')
            ).action_assign()

    # ==========================================================
    # CANCELLATION (INTERIM - reversal flow pending design sign-off)
    # ==========================================================

    def action_cancel(self) -> None:
        """Pre-confirmation cancel only for Outbound tickets.
        A confirmed ticket has already deducted stock and updated invoicing quantities:
        reverting it requires the dedicated reversal process, not a state change."""
        confirmed_outbound = self.filtered(
            lambda rec: rec.weighbridge_type == OUTBOUND_WEIGHBRIDGE_TYPE and rec.state == 'confirmed'
        )
        if confirmed_outbound:
            raise UserError(_(
                "Ticket %s is confirmed: stock has already been deducted and invoicing "
                "quantities were updated. It cannot be cancelled directly. Use the reversal "
                "process once it is enabled, or contact your administrator.",
                confirmed_outbound[:1].name,
            ))
        # Before confirmation nothing was synced to the D/Os - a plain cancel is safe.
        super().action_cancel()

    # ==========================================================
    # NAVIGATION
    # ==========================================================

    def action_start_loading(self) -> None:
        for rec in self:
            if rec.gross_weight <= 0:
                raise UserError(_("You must capture the First Weight before starting loading."))
            rec.state = 'unloading'

    def action_view_delivery_pickings(self) -> Dict[str, Any]:
        """Open the Delivery Orders referenced by this ticket's lines
        (single: the form; several: the list)."""
        self.ensure_one()
        pickings = self.line_ids.mapped('delivery_picking_id')
        if not pickings:
            return {'type': 'ir.actions.act_window_close'}
        if len(pickings) == 1:
            return self._open_form_view('stock.picking', pickings.id, 'Delivery Order')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Delivery Orders',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
            'target': 'current',
        }

    @api.constrains('sale_order_id')
    def _check_company_consistency(self) -> None:
        """Protocol 3.1 (SRP): legacy guard - the (machinery) Sales Memo must
        belong to a company allowed for the current user."""
        for rec in self:
            if rec.sale_order_id and rec.sale_order_id.company_id not in self.env.companies:
                raise ValidationError(_(
                    "The Sales Memo (%(so)s) belongs to a company you are not authorized to use. "
                    "Please switch your active company or select a different Sales Memo.",
                    so=rec.sale_order_id.name
                ))

    @api.constrains('line_ids', 'weighbridge_type', 'state')
    def _check_delivery_picking_unique_weighbridge(self) -> None:
        """Protocol 3.1 (SRP): a Delivery Order may appear on only ONE active
        Outbound Weighbridge Ticket - now enforced per LINE, since one ticket
        legitimately carries several Delivery Orders."""
        for ticket in self:
            if ticket.weighbridge_type != OUTBOUND_WEIGHBRIDGE_TYPE or ticket.state == 'cancel':
                continue

            for picking in ticket.line_ids.mapped('delivery_picking_id'):
                if not picking:
                    continue
                other_tickets = self.search([
                    ('id', '!=', ticket.id),
                    ('weighbridge_type', '=', OUTBOUND_WEIGHBRIDGE_TYPE),
                    ('state', '!=', 'cancel'),
                    ('line_ids.delivery_picking_id', '=', picking.id),
                ])
                if other_tickets:
                    raise ValidationError(_(
                        "Delivery Order %s already has an active Weighbridge Ticket (%s). "
                        "A Delivery Order can only have one active Outbound Weighbridge Ticket at a time. "
                        "Please validate or cancel the existing ticket first.",
                        picking.name,
                        other_tickets[0].name
                    ))


class WeighbridgeTicketLineOutbound(models.Model):
    _inherit = 'weighbridge.ticket.line'

    # Delivery Order specific fields for Outbound (one D/O PER LINE now)
    delivery_picking_id = fields.Many2one('stock.picking', string='Delivery Order')
    do_line_id = fields.Many2one('stock.move', string='D/O Line')
    # The approved commercial D/O Qty mapped from the Delivery Order move (reporting reference).
    do_qty = fields.Float(string='D/O Qty', readonly=True, digits=(16, 3))
    # The move's demand - governs the allocation ceiling (moisture gain above D/O Qty allowed).
    do_demand_qty = fields.Float(string='Qty', readonly=True, digits=(16, 3))

    # Sales Memo fields kept in DB for background logic (hidden in UI)
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Memo Line')