# -*- coding: utf-8 -*-
from odoo import models, fields, api
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_order_date = fields.Date(string='D/O Date')
    total_qty = fields.Float(string='Total', compute='_compute_total_qty', store=True, readonly=False)

    sale_memo_id = fields.Many2one('sale.order', string='Sales Memo No')
    broker_id = fields.Many2one('res.partner', string='Broker')

    delivery_remarks = fields.Text(string='Remarks')
    not_book_jv = fields.Boolean(string='NoteBook JV')

    # FIX: Compute total based on Odoo's native 'quantity' field
    @api.depends('move_ids.quantity')
    def _compute_total_qty(self) -> None:
        """Protocol 2.1 (SRP): Calculate total delivery quantity from moves."""
        for picking in self:
            picking.total_qty = sum(picking.move_ids.mapped('quantity'))

    @api.onchange('sale_memo_id')
    def _onchange_sale_memo_id(self) -> None:
        """Flow Fix: Auto-populate Partner, Broker, and Stock Moves from Sales Memo."""
        if not self.sale_memo_id:
            self.update({
                'move_ids': [COMMAND_CLEAR_ALL],
                'partner_id': False,
                'broker_id': False,
                'sale_id': False,
                'total_qty': 0.0
            })
            return

        self.partner_id = self.sale_memo_id.partner_id
        self.broker_id = self.sale_memo_id.broker_id
        self.sale_id = self.sale_memo_id.id

        move_lines: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for line in self.sale_memo_id.order_line:
            move_lines.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'quantity': line.product_uom_qty,
                'sale_order_id': self.sale_memo_id.id,
                'pcs': line.pcs,
                'ctn': line.ctn,
                'sale_line_id': line.id,
            }))

        self.move_ids = move_lines


class StockMove(models.Model):
    _inherit = 'stock.move'

    sale_order_id = fields.Many2one('sale.order', string='SO No', related='picking_id.sale_memo_id', store=True, readonly=False)
    pcs = fields.Float(string='PCS', related='sale_line_id.pcs', store=True, readonly=False)
    ctn = fields.Float(string='CTN', related='sale_line_id.ctn', store=True, readonly=False)

    # REMOVED: delivery_qty field
    balance_qty = fields.Float(string='Balance', compute='_compute_balance_qty', store=True)

    @api.depends('product_uom_qty', 'quantity')
    def _compute_balance_qty(self) -> None:
        """Protocol 2.1 (SRP): Calculate balance quantity dynamically."""
        for move in self:
            move.balance_qty = move.product_uom_qty - move.quantity