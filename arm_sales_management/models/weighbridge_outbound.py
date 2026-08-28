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


class WeighbridgeTicketOutbound(models.Model):
    _inherit = 'weighbridge.ticket'

    # FIX: Use selection_add to inject the 'outbound' option cleanly
    weighbridge_type = fields.Selection(
        selection_add=[('outbound', 'Outbound (Sales)')],
        ondelete={'outbound': 'set default'}
    )

    # Outbound Specific Fields
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo Ref')
    delivery_picking_id = fields.Many2one(
        'stock.picking', string='Delivery Order Ref',
        domain="['&', ('sale_id', '=', sale_order_id), ('picking_type_code', '=', 'outgoing'), "
               "('state', 'not in', ['done', 'cancel']), "
               "'|', ('contract_type', '=', 'export'), ('is_commercially_validated', '=', True)]"
    )
    outbound_partner_id = fields.Many2one(
        related='sale_order_id.partner_id', string='Customer', store=True, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'WeighbridgeTicketOutbound':
        records = super().create(vals_list)
        for rec in records:
            if rec.weighbridge_type == 'outbound':
                rec._resolve_outbound_do_lines()
        return records

    @api.onchange('weighbridge_type')
    def _onchange_weighbridge_type_outbound(self) -> None:
        """Protocol 2.1: Clear fields when switching types."""
        if self.weighbridge_type == 'outbound':
            self.grn_inspection_id = False
            self.rice_sales_contract_id = False
            self.partner_id = False
            self.vehicle_number = False
            self.line_ids = [COMMAND_CLEAR_ALL]

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self) -> None:
        """Protocol 2.1: Auto-populate lines and Gate Pass from Sales Memo."""
        if not self.sale_order_id:
            self.line_ids = [COMMAND_CLEAR_ALL]
            self.gate_pass_id = False
            return

        self.partner_id = self.sale_order_id.partner_id.id

        gate_pass = self.env['gate.pass'].search([
            ('sale_order_id', '=', self.sale_order_id.id),
            ('pass_type', '=', 'outbound'),
            ('state', 'in', ['draft', 'confirmed'])
        ], limit=1, order='id desc')

        if gate_pass:
            self.gate_pass_id = gate_pass.id
            self.vehicle_number = gate_pass.vehicle_number
            self.truck_type = gate_pass.truck_type.id

        shippable_lines = self.sale_order_id.order_line.filtered(
            lambda line: line._is_shippable_line()
        )
        line_vals = [
            (COMMAND_CREATE_NEW, 0, {
                'sale_order_id': self.sale_order_id.id,
                'sale_line_id': so_line.id,
                'product_id': so_line.product_id.id,
                'allocated_weight': 0.0,
            })
            for so_line in shippable_lines
        ]
        self.line_ids = line_vals

    @api.onchange('gate_pass_id')
    def _onchange_gate_pass_id_outbound(self) -> None:
        """Protocol 2.1: Auto-populate from Gate Pass."""
        if (self.weighbridge_type == 'outbound'
                and self.gate_pass_id
                and self.gate_pass_id.pass_type == 'outbound'):
            self.sale_order_id = self.gate_pass_id.sale_order_id.id
            self.delivery_picking_id = self.gate_pass_id.delivery_picking_id.id
            self.partner_id = self.gate_pass_id.partner_id.id
            self.vehicle_number = self.gate_pass_id.vehicle_number
            self.truck_type = self.gate_pass_id.truck_type.id
            self._resolve_outbound_do_lines()

    @api.onchange('delivery_picking_id')
    def _onchange_delivery_picking_id_outbound(self) -> None:
        """Manually linking a Delivery Order (without a Gate Pass): map its moves
        onto the lines - D/O Line, D/O Qty and Demand - exactly like the
        Gate Pass flow does, so allocation has its reference values."""
        if self.weighbridge_type == 'outbound' and self.delivery_picking_id:
            self._resolve_outbound_do_lines()

    def _resolve_outbound_do_lines(self) -> None:
        """Protocol 2.1 (SRP): Map Weighbridge lines to Delivery Order moves based on Sale Line IDs.
        Maps BOTH reference quantities per line:
        - do_qty:        the approved commercial D/O Qty (what User A entered, e.g. 45)
        - do_demand_qty: the move's demand (e.g. 100) - governs the allocation ceiling
          so physical moisture gain above the D/O Qty stays allowed."""
        self.ensure_one()

        if not self.delivery_picking_id and self.gate_pass_id and self.gate_pass_id.delivery_picking_id:
            self.delivery_picking_id = self.gate_pass_id.delivery_picking_id.id

        if not self.delivery_picking_id:
            return  # Cannot map lines without a D/O

        for line in self.line_ids:
            if line.sale_line_id:
                do_move = self.env['stock.move'].search([
                    ('picking_id', '=', self.delivery_picking_id.id),
                    ('sale_line_id', '=', line.sale_line_id.id)
                ], limit=1)

                if do_move:
                    line.write({
                        'delivery_picking_id': self.delivery_picking_id.id,
                        'do_line_id': do_move.id,
                        'do_qty': do_move._get_commercial_basis_qty(),
                        'do_demand_qty': do_move.product_uom_qty,
                    })

    # ==========================================================
    # CONFIRMATION PIPELINE (USER B)
    # ==========================================================

    def _is_local_delivery_ticket(self) -> bool:
        """Protocol 4.1 (DRY): Outbound tickets tied to a Local Sales Delivery Order
        follow the commercial validation pipeline. Export deliveries keep their
        native behavior (no User A approval, no stock validation from here)."""
        self.ensure_one()
        return bool(self.delivery_picking_id) and self.delivery_picking_id._is_local_sale_delivery()

    def action_confirm_outbound(self) -> None:
        """Complete the Outbound process, one responsibility per step."""
        for rec in self:
            rec._check_outbound_confirmation_readiness()
            rec._validate_weight_allocation()
            rec._sync_delivery_order_moves()
            rec._sync_gate_pass_weights()
            if rec._is_local_delivery_ticket():
                rec._process_delivery_validation()
                rec._accumulate_commercial_quantities()
                rec._refresh_open_delivery_demand()
            rec.state = 'confirmed'

    def _check_outbound_confirmation_readiness(self) -> None:
        """Protocol 2.1: Ordered fast-fail checklist, each with a specific, actionable message."""
        self.ensure_one()

        if self.tare_weight <= 0:
            raise UserError(_("Please capture the Second Weight before confirming."))

        if not self.delivery_picking_id:
            raise UserError(_("Link a Delivery Order first: weights are posted against it."))

        if self._is_local_delivery_ticket() and not self.delivery_picking_id.is_commercially_validated:
            raise UserError(_(
                "Delivery Order %s is not commercially validated yet. "
                "The Sales user must approve the D/O Qty before the Weighbridge can confirm.",
                self.delivery_picking_id.name,
            ))

        if not self.gate_pass_id:
            raise UserError(_("Link the Outbound Gate Pass for this truck."))

        if self.gate_pass_id.state not in ('confirmed', 'done'):
            raise UserError(_(
                "Gate Pass %s must be Confirmed (button 'Confirm Entry') before confirming the "
                "ticket. Current state: %s.",
                self.gate_pass_id.name, self.gate_pass_id.state,
            ))

        if self._is_local_delivery_ticket():
            tracked_lines = self.line_ids.filtered(
                lambda line: line.allocated_weight > 0 and line.product_id.tracking != 'none'
            )
            if tracked_lines:
                raise UserError(_(
                    "Lot/serial tracked products cannot be auto-validated yet: %s. "
                    "Assign lots on the Delivery Order manually or contact your administrator.",
                    ", ".join(tracked_lines.mapped('product_id.display_name')),
                ))

    def _validate_weight_allocation(self) -> None:
        """Outbound allocation rules: no negatives, at least one positive, none above demand.
        Zero lines are tolerated (product simply not on this truck)."""
        super()._validate_weight_allocation()
        for rec in self:
            if rec.weighbridge_type != 'outbound':
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
        """Protocol 2.1 (SRP): Update the linked Delivery Order moves with allocated weights.
        Does NOT validate the DO; native backorder creation happens during validation."""
        self.ensure_one()

        for line in self.line_ids:
            if line.allocated_weight > 0 and line.do_line_id:
                line.do_line_id.write({
                    'quantity': line.allocated_weight,
                    'picked': True
                })

    def _sync_gate_pass_weights(self) -> None:
        """Protocol 2.1 (SRP): Per-product weights on gate pass lines.
        Header totals recompute natively from lines (_compute_qtys on gate.pass)."""
        self.ensure_one()
        gate_pass = self.gate_pass_id
        if not gate_pass:
            return

        for gp_line in gate_pass.gate_pass_line_ids:
            wb_line = self.line_ids.filtered(
                lambda line: line.allocated_weight > 0
                and (line.sale_line_id == gp_line.sale_line_id
                     or (not line.sale_line_id and line.product_id == gp_line.product_id))
            )[:1]
            if wb_line:
                gp_line.gross = wb_line.allocated_weight
                gp_line.net = wb_line.allocated_weight

        if self.delivery_picking_id and not gate_pass.delivery_picking_id:
            gate_pass.delivery_picking_id = self.delivery_picking_id.id

        if gate_pass.state == 'confirmed':
            gate_pass.action_mark_exited()

    def _process_delivery_validation(self) -> None:
        """Protocol 2.1 (SRP): Trigger the real (bypassed) validation and digest any wizards."""
        self.ensure_one()
        picking = self.delivery_picking_id.with_context(**{BYPASS_COMMERCIAL_CHECK: True})
        validation_result = picking.button_validate()
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

    def _accumulate_commercial_quantities(self) -> None:
        """Per-product accumulation - fixes double-counting on multi-product / split-move DOs."""
        self.ensure_one()
        delivered_moves = self.delivery_picking_id.move_ids.filtered(
            lambda move: move.state == 'done' and move.sale_line_id and move.commercial_quantity > 0
        )
        for move in delivered_moves:
            move.sale_line_id.commercial_delivered_qty += move.commercial_quantity

    def _refresh_open_delivery_demand(self) -> None:
        """Invariant A as a recompute: open demand = memo qty - commercial delivered.
        Idempotent, so it is safe for both confirm and (later) reversal."""
        self.ensure_one()
        sale_lines = self.delivery_picking_id.move_ids.mapped('sale_line_id')

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
                    lambda picking: picking.state not in ('done', 'cancel')
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
                lambda picking: picking.state not in ('done', 'cancel')
            ).action_assign()

    # ==========================================================
    # CANCELLATION (INTERIM - reversal flow pending design sign-off)
    # ==========================================================

    def action_cancel(self) -> None:
        """Pre-confirmation cancel only for Outbound tickets.
        A confirmed ticket has already deducted stock and updated invoicing quantities:
        reverting it requires the dedicated reversal process, not a state change."""
        confirmed_outbound = self.filtered(
            lambda rec: rec.weighbridge_type == 'outbound' and rec.state == 'confirmed'
        )
        if confirmed_outbound:
            raise UserError(_(
                "Ticket %s is confirmed: stock has already been deducted and invoicing "
                "quantities were updated. It cannot be cancelled directly. Use the reversal "
                "process once it is enabled, or contact your administrator.",
                confirmed_outbound[:1].name,
            ))
        # Before confirmation nothing was synced to the D/O - a plain cancel is safe.
        super().action_cancel()

    # ==========================================================
    # NAVIGATION
    # ==========================================================

    def action_start_loading(self) -> None:
        for rec in self:
            if rec.gross_weight <= 0:
                raise UserError(_("You must capture the First Weight before starting loading."))
            rec.state = 'unloading'

    def action_view_sale_order(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('sale.order', self.sale_order_id.id, 'Sales Memo')

    def action_view_delivery_picking(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('stock.picking', self.delivery_picking_id.id, 'Delivery Order')

    @api.constrains('sale_order_id')
    def _check_company_consistency(self) -> None:
        """Protocol 3.1 (SRP): Ensure Sales Memo belongs to a company allowed for the current user."""
        for rec in self:
            if rec.sale_order_id and rec.sale_order_id.company_id not in self.env.companies:
                raise ValidationError(_(
                    "The Sales Memo (%(so)s) belongs to a company you are not authorized to use. "
                    "Please switch your active company or select a different Sales Memo.",
                    so=rec.sale_order_id.name
                ))

    @api.constrains('delivery_picking_id', 'weighbridge_type', 'state')
    def _check_delivery_picking_unique_weighbridge(self) -> None:
        """Protocol 3.1 (SRP): Ensure a 1:1 relationship between active Outbound Weighbridge and Delivery Order."""
        for ticket in self:
            if ticket.weighbridge_type == 'outbound' and ticket.delivery_picking_id and ticket.state != 'cancel':
                other_tickets = self.search([
                    ('id', '!=', ticket.id),
                    ('delivery_picking_id', '=', ticket.delivery_picking_id.id),
                    ('weighbridge_type', '=', 'outbound'),
                    ('state', '!=', 'cancel')
                ])
                if other_tickets:
                    raise ValidationError(_(
                        "Delivery Order %s already has an active Weighbridge Ticket (%s). "
                        "A Delivery Order can only have one active Outbound Weighbridge Ticket at a time. "
                        "Please validate or cancel the existing ticket first.",
                        ticket.delivery_picking_id.name,
                        other_tickets[0].name
                    ))


class WeighbridgeTicketLineOutbound(models.Model):
    _inherit = 'weighbridge.ticket.line'

    # Delivery Order specific fields for Outbound
    delivery_picking_id = fields.Many2one('stock.picking', string='Delivery Order')
    do_line_id = fields.Many2one('stock.move', string='D/O Line')
    # The approved commercial D/O Qty mapped from the Delivery Order move (reporting reference).
    do_qty = fields.Float(string='D/O Qty', readonly=True, digits=(16, 3))
    # The move's demand - governs the allocation ceiling (moisture gain above D/O Qty allowed).
    do_demand_qty = fields.Float(string='Qty', readonly=True, digits=(16, 3))

    # Sales Memo fields kept in DB for background logic (hidden in UI)
    sale_order_id = fields.Many2one('sale.order', string='Sales Memo')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Memo Line')