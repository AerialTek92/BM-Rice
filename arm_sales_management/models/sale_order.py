# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
from typing import Any, Dict, List, Optional

from .delivery_order import QUANTITY_PRECISION, PICKING_OUTGOING

# --- Searchable Constants (Protocol 1.3) ---
PERCENTAGE_DIVISOR: float = 100.0
GRAMS_TO_KG_DIVISOR: float = 1000.0

# --- Product Types that never physically ship (Protocol 1.3) ---
SERVICE_PRODUCT_TYPE: str = 'service'
COMBO_PRODUCT_TYPE: str = 'combo'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Header level custom fields
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'broker')]")
    delivery_date = fields.Date(string='Delivery Date')
    delivery_remarks = fields.Text(string='Delivery Remarks')

    # Manual Sales Memo Reference
    manual_sales_memo_ref = fields.Char(string='Sales Memo Ref')

    # Contract Linkage & Type (Related & Readonly)
    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Rice Sales Contract')
    contract_type = fields.Selection(
        related='rice_sales_contract_id.contract_type',
        string='Contract Type',
        readonly=True,
        store=True
    )
    is_export_hidden = fields.Boolean(string="Hidden Export Memo", default=False)

    # Invoicing gate: True only when every shippable line is fully delivered
    is_delivery_complete = fields.Boolean(
        string='Fully Delivered (Commercial)',
        compute='_compute_is_delivery_complete',
        store=True,
        help="True when every stockable line of the memo has been fully delivered. "
             "The 'Create Invoice' button stays hidden until then.",
    )

    @api.depends('order_line.qty_delivered', 'order_line.product_uom_qty',
                 'order_line.display_type', 'order_line.product_id')
    def _compute_is_delivery_complete(self) -> None:
        """Invariant A surfaced on the memo header: invoicing unlocks only at full delivery."""
        for order in self:
            shippable_lines = order.order_line.filtered(lambda line: line._is_shippable_line())
            order.is_delivery_complete = all(
                float_compare(line.qty_delivered, line.product_uom_qty, precision_digits=QUANTITY_PRECISION) >= 0
                for line in shippable_lines
            )

    def action_confirm(self) -> Any:
        """Protocol 2.1 (SRP): Safety net for Delivery Order creation on confirmation."""
        res = super().action_confirm()
        for order in self:
            if order.order_line and not order.picking_ids:
                order.order_line._action_launch_stock_rule()
        return res

    def action_create_delivery_order(self) -> Dict[str, Any]:
        """Create an ADDITIONAL Delivery Order for the remaining quantity of this memo.

        Native Odoo creates exactly one DO per confirmation; this is the sanctioned
        path for multiple trucks/DOs without touching the existing open DO."""
        self.ensure_one()
        if self.state not in ('sale', 'done'):
            raise UserError(_("Confirm the Sales Memo before creating Delivery Orders."))

        lines_with_remaining = self.order_line.filtered(
            lambda line: line._is_shippable_line() and line.remaining_qty > 0
        )
        if not lines_with_remaining:
            raise UserError(_(
                "There is no remaining quantity to deliver on Sales Memo %s. Remaining = "
                "memo quantity minus delivered minus quantities already entered on open Delivery Orders.",
                self.name,
            ))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', PICKING_OUTGOING),
            ('warehouse_id', '=', self.warehouse_id.id),
        ], limit=1) or self.env['stock.picking.type'].search([
            ('code', '=', PICKING_OUTGOING),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an outgoing operation type for this warehouse."))

        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'origin': self.name,
        })

        # NOTE: stock.move keeps the field name 'product_uom' in Odoo 19
        # (only sale/purchase lines were renamed to product_uom_id).
        move_vals = [{
            'product_id': line.product_id.id,
            'product_uom': line.product_id.uom_id.id,
            'product_uom_qty': line.remaining_qty,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'picking_id': picking.id,
            'picking_type_id': picking_type.id,
            'sale_line_id': line.id,
            'origin': self.name,
        } for line in lines_with_remaining]
        self.env['stock.move'].create(move_vals)

        picking.action_confirm()
        picking.action_assign()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Line level custom fields
    # PCS is a plain editable input: either PCS or Qty can be the driver.
    pcs = fields.Float(string='Pcs')
    # CTN is always derived - never an input (Protocol 2.1: single responsibility).
    ctn = fields.Float(string='Ctn', compute='_compute_cartons', store=True, readonly=True)

    # Available-to-promise on the memo line: memo qty - delivered - committed on open DOs.
    remaining_qty = fields.Float(
        string='Rem. Qty',
        compute='_compute_remaining_qty',
        help="Memo quantity minus commercially delivered minus quantities already entered "
             "on open Delivery Orders (validated or not).",
    )

    discount_amount = fields.Monetary(string='Disct Amt', compute='_compute_net_amount', store=True)
    discount_special = fields.Monetary(string='Disct Sp.')
    net_amount = fields.Monetary(string='Net Amt', compute='_compute_net_amount', store=True)

    # The exact commercial quantity to invoice (ignores moisture weight gain)
    commercial_delivered_qty = fields.Float(string='Commercial Delivered Qty', default=0.0)

    additional_weight = fields.Float(string='Add. Weight (g)', compute='_compute_additional_weight', store=True)
    total_weight = fields.Float(string='Total Weight (kg)', compute='_compute_total_weight', store=True)

    # ==========================================================
    # PACK QUANTITY SYNCHRONIZATION (Qty (kgs) <-> PCS)
    # ==========================================================

    def _is_shippable_line(self) -> bool:
        """Protocol 4.1 (DRY): Single definition of 'this line must physically ship'."""
        self.ensure_one()
        return (
            not self.display_type
            and bool(self.product_id)
            and self.product_id.type not in (SERVICE_PRODUCT_TYPE, COMBO_PRODUCT_TYPE)
        )

    def _get_piece_weight_kg(self) -> float:
        """Protocol 1.3/2.1: Piece weight from the product configuration (kg per piece)."""
        self.ensure_one()
        product = self.product_id
        return product.product_tmpl_id.piece_weight if product else 0.0

    def _convert_quantity_to_kg(self, quantity: float) -> float:
        """Guard: piece math is defined in kg; convert line-unit quantities safely."""
        self.ensure_one()
        if self.product_id and self.product_uom_id and self.product_uom_id != self.product_id.uom_id:
            return self.product_uom_id._compute_quantity(quantity, self.product_id.uom_id)
        return quantity

    def _convert_kg_to_quantity(self, quantity_kg: float) -> float:
        """Guard: mirror conversion back into the line's unit."""
        self.ensure_one()
        if self.product_id and self.product_uom_id and self.product_uom_id != self.product_id.uom_id:
            return self.product_id.uom_id._compute_quantity(quantity_kg, self.product_uom_id)
        return quantity_kg

    def _set_pieces_from_quantity(self) -> None:
        """Qty is the driver: PCS = Qty (kg) / piece weight."""
        piece_weight = self._get_piece_weight_kg()
        if piece_weight > 0:
            quantity_kg = self._convert_quantity_to_kg(self.product_uom_qty)
            self.pcs = quantity_kg / piece_weight

    def _set_quantity_from_pieces(self) -> None:
        """PCS is the driver: Qty = PCS * piece weight."""
        piece_weight = self._get_piece_weight_kg()
        if piece_weight > 0:
            self.product_uom_qty = self._convert_kg_to_quantity(self.pcs * piece_weight)

    @api.onchange('product_uom_qty', 'product_uom_id')
    def _onchange_quantity_set_pieces(self) -> None:
        """User typed Qty (kgs): derive PCS (CTN follows via its own compute)."""
        self._set_pieces_from_quantity()

    @api.onchange('pcs')
    def _onchange_pieces_set_quantity(self) -> None:
        """User typed PCS: derive Qty (CTN follows via its own compute)."""
        self._set_quantity_from_pieces()

    @api.onchange('product_id')
    def _onchange_product_recompute_pieces(self) -> None:
        """Product changed: Qty is the commercial driver and survives the swap."""
        self._set_pieces_from_quantity()

    @api.depends('pcs', 'product_id', 'product_id.carton_capacity')
    def _compute_cartons(self) -> None:
        """CTN is always derived from PCS: CTN = PCS / pieces per carton."""
        for line in self:
            carton_capacity = line.product_id.carton_capacity if line.product_id else 0.0
            line.ctn = (line.pcs / carton_capacity) if carton_capacity > 0 and line.pcs > 0 else 0.0

    @api.model
    def _normalize_pack_vals(self, vals: Dict[str, Any]) -> Dict[str, Any]:
        """Server-side twin of the onchanges for imports and programmatic writes.
        Precedence when both quantity and pieces are provided: QUANTITY WINS."""
        product = self.env['product.product'].browse(vals.get('product_id'))
        if not product:
            return vals

        piece_weight = product.product_tmpl_id.piece_weight
        if piece_weight <= 0:
            return vals

        line_uom = self.env['uom.uom'].browse(
            vals.get('product_uom_id') or product.uom_id.id
        )
        if 'product_uom_qty' in vals:
            quantity_kg = line_uom._compute_quantity(vals['product_uom_qty'], product.uom_id)
            vals['pcs'] = quantity_kg / piece_weight
        elif 'pcs' in vals:
            quantity_kg = vals['pcs'] * piece_weight
            vals['product_uom_qty'] = product.uom_id._compute_quantity(quantity_kg, line_uom)
        return vals

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'SaleOrderLine':
        """Normalize Qty/PCS before creation (covers contract-flow and imported lines)."""
        for vals in vals_list:
            self._normalize_pack_vals(vals)
        return super().create(vals_list)

    def write(self, vals: Dict[str, Any]) -> bool:
        """Normalize Qty/PCS before writing, per line, filling in line context."""
        if 'product_uom_qty' in vals or 'pcs' in vals:
            for line in self:
                line_vals = dict(vals)
                line_vals.setdefault('product_id', line.product_id.id)
                line_vals.setdefault('product_uom_id', line.product_uom_id.id)
                self._normalize_pack_vals(line_vals)
                super(SaleOrderLine, line).write(line_vals)
            return True
        return super().write(vals)

    # ==========================================================
    # REMAINING QUANTITY (Invariant A, surfaced live)
    # ==========================================================

    def _get_committed_open_qty(self, exclude_picking: Optional['stock.picking'] = None) -> float:
        """Protocol 4.1 (DRY): Quantity committed on open outgoing DOs for this line.
        Counts the D/O Qty entered by users (validated or not) so draft entries
        already reduce availability. Returns and receipts are excluded by picking type."""
        self.ensure_one()
        open_moves = self.move_ids.filtered(
            lambda move: move.state not in ('done', 'cancel')
            and move.picking_id.picking_type_code == PICKING_OUTGOING
            and (not exclude_picking or move.picking_id != exclude_picking)
        )
        return sum(max(move.quantity, move.commercial_quantity) for move in open_moves)

    @api.depends('product_uom_qty', 'commercial_delivered_qty',
                 'move_ids.quantity', 'move_ids.commercial_quantity', 'move_ids.state',
                 'move_ids.picking_id.state', 'move_ids.picking_id.picking_type_code')
    def _compute_remaining_qty(self) -> None:
        """Remaining = memo qty - commercially delivered - committed on open DOs.
        Deliberately non-stored: it must reflect draft D/O Qty entries immediately."""
        for line in self:
            committed_open_qty = line._get_committed_open_qty()
            line.remaining_qty = (
                line.product_uom_qty - line.commercial_delivered_qty - committed_open_qty
            )

    # ==========================================================
    # COMMERCIAL / DISPLAY COMPUTES
    # ==========================================================

    @api.depends('product_uom_qty', 'price_unit', 'discount', 'discount_special')
    def _compute_net_amount(self) -> None:
        for line in self:
            base_amount = line.product_uom_qty * line.price_unit

            if line.discount:
                line.discount_amount = base_amount * (line.discount / PERCENTAGE_DIVISOR)
            else:
                line.discount_amount = 0.0

            line.net_amount = base_amount - (line.discount_amount or 0.0) - (line.discount_special or 0.0)

    @api.depends('product_id', 'product_uom_qty', 'move_ids.state', 'move_ids.quantity', 'move_ids.product_uom',
                 'commercial_delivered_qty')
    def _compute_qty_delivered(self):
        res = super()._compute_qty_delivered()
        for line in self:
            if line.commercial_delivered_qty > 0.0:
                line.qty_delivered = line.commercial_delivered_qty
        return res

    @api.depends('product_uom_qty', 'product_id', 'product_id.additional_weight')
    def _compute_additional_weight(self) -> None:
        for line in self:
            if line.product_id and line.product_id.additional_weight:
                line.additional_weight = line.product_uom_qty * line.product_id.additional_weight
            else:
                line.additional_weight = 0.0

    @api.depends('product_uom_qty', 'additional_weight')
    def _compute_total_weight(self) -> None:
        for line in self:
            line.total_weight = line.product_uom_qty + (line.additional_weight / GRAMS_TO_KG_DIVISOR)

    def unlink(self) -> bool:
        for line in self:
            if line.qty_delivered > 0.0:
                raise UserError(_(
                    "You cannot delete a Sales Memo line for product '%(product)s' because it has already been delivered. "
                    "Please create a return or a credit note instead.",
                    product=line.product_id.name
                ))
        return super().unlink()