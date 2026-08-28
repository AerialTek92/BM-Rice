# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
from typing import Any, Dict, List, Tuple

# --- ORM Command Constants (Protocol 1.3) ---
COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

# --- Unit Conversion ---
GRAMS_TO_KG_DIVISOR: float = 1000.0

# --- Local Sales Flow Constants ---
BYPASS_COMMERCIAL_CHECK: str = 'bypass_commercial_check'
EXPORT_CONTRACT_TYPE: str = 'export'
PICKING_OUTGOING: str = 'outgoing'
QUANTITY_PRECISION: int = 3


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Custom Header Fields strictly for Delivery Orders
    delivery_order_date = fields.Date(string='D/O Date')
    total_qty = fields.Float(string='Total', compute='_compute_total_qty', store=True, readonly=False)
    broker_id = fields.Many2one(related='sale_id.broker_id', string='Broker', store=True, readonly=False)
    delivery_remarks = fields.Text(string='Remarks')
    notebook_jv = fields.Boolean(string='Notebook JV')

    # Contract Type (Inherited from Sales Memo)
    contract_type = fields.Selection(related='sale_id.contract_type', string='Contract Type', store=True)

    # Commercial validation (User A approval)
    is_commercially_validated = fields.Boolean(string="Commercially Validated", copy=False)
    commercial_do_qty = fields.Float(string="Comm. D/O Qty", copy=False)

    # Link to Weighbridge Tickets
    weighbridge_ticket_ids = fields.One2many(
        'weighbridge.ticket',
        'delivery_picking_id',
        string='Weighbridge Tickets'
    )
    active_weighbridge_ticket_id = fields.Many2one(
        'weighbridge.ticket',
        string='Active Weighbridge',
        compute='_compute_active_weighbridge_ticket',
        store=True,
        help="The linked outbound weighbridge ticket that must be confirmed before this DO can be validated."
    )

    @api.depends('picking_type_code', 'weighbridge_ticket_ids.state')
    def _compute_active_weighbridge_ticket(self) -> None:
        """Protocol 2.1 (SRP): Identify the single active outbound weighbridge for this DO."""
        for picking in self:
            if picking.picking_type_code == 'outgoing':
                active_ticket = picking.weighbridge_ticket_ids.filtered(
                    lambda ticket: ticket.weighbridge_type == 'outbound' and ticket.state != 'cancel'
                )
                picking.active_weighbridge_ticket_id = active_ticket[:1].id if active_ticket else False
            else:
                picking.active_weighbridge_ticket_id = False

    @api.depends('move_ids.quantity')
    def _compute_total_qty(self) -> None:
        """Protocol 2.1 (SRP): Calculate total delivery quantity from moves."""
        for picking in self:
            picking.total_qty = sum(picking.move_ids.mapped('quantity'))

    @api.onchange('sale_id')
    def _onchange_sale_id_populate_lines(self) -> None:
        """Protocol 2.1 (SRP): Auto-populate stock moves from the linked Sales Memo."""
        if not self.sale_id:
            self.move_ids = [COMMAND_CLEAR_ALL]
            return

        move_commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for sale_line in self.sale_id.order_line.filtered(lambda line: line.product_id):
            move_commands.append((COMMAND_CREATE_NEW, 0, {
                'product_id': sale_line.product_id.id,
                'product_uom_qty': sale_line.product_uom_qty,
                'product_uom': sale_line.product_id.uom_id.id,
                'sale_line_id': sale_line.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
            }))

        if move_commands:
            self.move_ids = move_commands

    def action_dummy(self):
        """Placeholder method for the UI status button (rename pending in the UI pass)."""
        return True

    # ==========================================================
    # LOCAL SALES: COMMERCIAL VALIDATION (USER A)
    # ==========================================================

    def _is_local_sale_delivery(self) -> bool:
        """Protocol 4.1 (DRY): Single source of truth for 'local sale' classification."""
        self.ensure_one()
        return (
            self.picking_type_code == 'outgoing'
            and bool(self.sale_id)
            and self.sale_id.contract_type != EXPORT_CONTRACT_TYPE
        )

    def button_validate(self) -> Any:
        """INTERCEPT: First click only locks commercial quantities. Real stock validation
        happens later, triggered by the Weighbridge with BYPASS_COMMERCIAL_CHECK."""
        for picking in self:
            is_awaiting_commercial_approval = (
                picking._is_local_sale_delivery()
                and not picking.is_commercially_validated
                and not self.env.context.get(BYPASS_COMMERCIAL_CHECK)
            )
            if is_awaiting_commercial_approval:
                picking._capture_commercial_quantities()
                return picking._get_commercial_validation_feedback()
        return super().button_validate()

    def _capture_commercial_quantities(self) -> None:
        """Protocol 2.1 (SRP): Lock the per-product commercial qty approved by the Sales user."""
        self.ensure_one()
        deliverable_moves = self.move_ids.filtered(lambda move: move.state not in ('done', 'cancel'))

        if not any(move.quantity > 0 for move in deliverable_moves):
            raise UserError(_("Please enter the D/O Qty (Done quantity) before approving."))

        for move in deliverable_moves:
            if move.quantity <= 0:
                continue  # Product not on this truck: stays 0, the backorder covers the rest.

            remaining_qty = self._get_remaining_commercial_qty(move.sale_line_id)
            if float_compare(move.quantity, remaining_qty, precision_digits=QUANTITY_PRECISION) > 0:
                raise UserError(_(
                    "D/O Qty for %(product)s (%(requested)s kg) exceeds the remaining memo quantity "
                    "(%(remaining)s kg). Over-delivery is not allowed on Local Sales.",
                    product=move.product_id.display_name,
                    requested=move.quantity,
                    remaining=remaining_qty,
                ))
            move.commercial_quantity = move.quantity

        self.write({
            'is_commercially_validated': True,
            'commercial_do_qty': sum(self.move_ids.mapped('commercial_quantity')),
        })

    def _get_remaining_commercial_qty(self, sale_line: 'sale.order.line') -> float:
        """Invariant A: memo qty - delivered - committed on OTHER open Delivery Orders."""
        self.ensure_one()
        if not sale_line:
            return float('inf')

        committed_elsewhere = sale_line._get_committed_open_qty(exclude_picking=self)
        return sale_line.product_uom_qty - sale_line.commercial_delivered_qty - committed_elsewhere

    def _get_commercial_validation_feedback(self) -> Dict[str, Any]:
        """Protocol 3.1 (SRP): Presentation decoupled from logic - notify and reload the form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Delivery Order approved"),
                'message': _(
                    "Commercial quantities are locked. Stock will be deducted when the "
                    "Weighbridge confirms the outbound ticket."
                ),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    sale_order_id = fields.Many2one(related='picking_id.sale_id', string='SO No', store=True, readonly=False)
    balance_qty = fields.Float(string='Balance', compute='_compute_balance_qty', store=True)

    # Memo-level availability for this product (delivered + all open D/O entries deducted).
    # Delivery Orders only: receipts/internal transfers have no sale line (shows 0, column hidden).
    sale_remaining_qty = fields.Float(
        related='sale_line_id.remaining_qty',
        string='Rem. Qty',
        readonly=True,
    )

    # PCS and CTN are COMMERCIAL figures: once User A approves the D/O Qty they
    # are locked to it (45 kg -> 9 pcs) and do NOT follow the physical weighed
    # weight that the Weighbridge later writes into 'quantity' (45.8 kg).
    pcs = fields.Float(
        string='PCS',
        compute='_compute_move_pcs',
        store=True,
    )
    ctn = fields.Float(
        string='CTN',
        compute='_compute_move_ctn',
        store=True,
    )

    # The commercial quantity approved by User A (what the customer is billed for).
    # Written once at commercial validation and NEVER overwritten by the physical
    # weight sync - this is the "originally entered D/O Qty" for reporting.
    commercial_quantity = fields.Float(
        string='Comm. D/O Qty (Kg)',
        copy=False,
        digits=(16, 3),
        help="Per-product commercial quantity approved by Sales (the D/O Qty entered at "
             "approval). Billing, backorder math and reporting read this, never the "
             "physical weighed weight.",
    )

    sm_qty = fields.Float(
        related='sale_line_id.product_uom_qty',
        string='SM Qty',
        store=True,
        readonly=True,
    )

    # FIX: Computed from the D/O Qty (quantity), same commercial-first pattern as PCS
    additional_weight = fields.Float(
        string='Add. Wt (g)',
        compute='_compute_move_additional_weight',
        store=True,
        readonly=True
    )
    total_weight = fields.Float(
        string='Total Wt',
        compute='_compute_move_total_weight',
        store=True,
        readonly=True
    )

    def _get_commercial_basis_qty(self) -> float:
        """Protocol 4.1 (DRY): The quantity this move's commercial figures are based on.
        Prefers the approved commercial quantity; falls back to the current D/O Qty
        while the DO is still awaiting User A's approval."""
        self.ensure_one()
        return self.commercial_quantity if self.commercial_quantity > 0 else self.quantity

    @api.depends('quantity', 'commercial_quantity', 'product_id', 'product_id.piece_weight')
    def _compute_move_pcs(self) -> None:
        """Protocol 2.1 (SRP): PCS derived from the COMMERCIAL quantity of this move.
        Live while unapproved (follows the typed D/O Qty), locked to the approved
        value afterwards - the Weighbridge's physical weight never changes it.
        Example: 45 kg / 5 kg per piece = 9 pieces."""
        for move in self:
            product = move.product_id.product_tmpl_id if move.product_id else False
            basis_qty = move._get_commercial_basis_qty()
            if product and product.piece_weight > 0 and basis_qty > 0:
                move.pcs = basis_qty / product.piece_weight
            else:
                move.pcs = 0.0

    @api.depends('pcs', 'product_id', 'product_id.carton_capacity')
    def _compute_move_ctn(self) -> None:
        """Protocol 2.1 (SRP): CTN derived from PCS (commercial).
        Example: 9 pieces / 10 pieces per carton = 0.9 cartons."""
        for move in self:
            carton_capacity = move.product_id.carton_capacity if move.product_id else 0.0
            move.ctn = (move.pcs / carton_capacity) if carton_capacity > 0 and move.pcs > 0 else 0.0

    @api.depends('quantity', 'product_id', 'product_id.additional_weight')
    def _compute_move_additional_weight(self) -> None:
        """Protocol 2.1 (SRP): Additional Weight based on the D/O Qty (physical basis,
        matching Total Weight which is also physical)."""
        for move in self:
            product = move.product_id.product_tmpl_id if move.product_id else False
            if product and product.additional_weight > 0 and move.quantity > 0:
                # Example: 25kg * 2g = 50g
                move.additional_weight = move.quantity * product.additional_weight
            else:
                move.additional_weight = 0.0

    @api.depends('quantity', 'additional_weight')
    def _compute_move_total_weight(self) -> None:
        """Protocol 2.1 (SRP): Total Weight based on the D/O Qty (physical basis)."""
        for move in self:
            # Total Weight (kg) = D/O Qty (kg) + (Additional Weight (g) / 1000)
            move.total_weight = move.quantity + (move.additional_weight / GRAMS_TO_KG_DIVISOR)

    @api.depends('product_uom_qty', 'quantity')
    def _compute_balance_qty(self) -> None:
        """Protocol 2.1 (SRP): Calculate balance quantity dynamically."""
        for move in self:
            move.balance_qty = move.product_uom_qty - move.quantity