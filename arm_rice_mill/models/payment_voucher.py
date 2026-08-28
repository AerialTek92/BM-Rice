# -*- coding: utf-8 -*-

from odoo import api, fields, models
from typing import Any, Dict, List

# --- ORM Command Constants (Protocol 1.3) ---
COMMAND_CLEAR_ALL: int = 5
COMMAND_CREATE_NEW: int = 0

# --- Document Constants ---
VENDOR_BILL_MOVE_TYPE: str = 'in_invoice'
PRODUCT_LINE_TYPE: str = 'product'
DRAFT_STATE: str = 'draft'
DEFAULT_LINE_SEQUENCE: int = 10
NORMALIZATION_CONTEXT_FLAG: str = 'pc_bill_normalizing'


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Separate Broker field (distinct from Vendor/Supplier)
    broker_id = fields.Many2one(
        'res.partner',
        string='Broker',
        domain="[('partner_assign_type', '=', 'broker')]"
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Primary Purchase Order',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['purchase', 'done'])]"
    )

    # Link to Payment Certificate (domain filters by the selected Broker)
    payment_certificate_id = fields.Many2one(
        'payment.certificate',
        string='Payment Certificate Ref',
        domain="[('broker_id', '=', broker_id), ('state', 'in', ['confirmed', 'paid'])]"
    )

    # Mapped amount from the PC - ALWAYS written directly from the PC,
    # never derived from lines, so line duplication can never zero it.
    rice_pc_amount = fields.Monetary(
        string='Rice PC Amount',
        currency_field='currency_id',
        readonly=True,
        store=True
    )

    # ==========================================================
    # PC -> PAYMENT VOUCHER MAPPING (DRY core)
    # ==========================================================

    @api.model
    def _prepare_pc_bill_header_vals(self, payment_certificate: 'payment.certificate') -> Dict[str, Any]:
        """Protocol 2.1 (SRP): Header values mapped from a Payment Certificate."""
        return {
            'partner_id': payment_certificate.partner_id.id,
            'rice_pc_amount': payment_certificate.net_payable,
            'ref': f"PC: {payment_certificate.name} / PO: {payment_certificate.purchase_id.name or ''}",
            'invoice_date': payment_certificate.date,
            'payment_reference': payment_certificate.name,
        }

    @api.model
    def _prepare_pc_bill_line_vals(self, payment_certificate: 'payment.certificate') -> Dict[str, Any]:
        """Protocol 2.1 (SRP): The single JV line mapped from a Payment Certificate.

        Quantity shows the PO line's product quantity; the unit price is derived
        as net_payable / quantity so the line TOTAL always equals the PC's net
        payable - the commercial figure that must actually be paid."""
        po_line = self.env['purchase.order.line'].search([
            ('order_id', '=', payment_certificate.purchase_id.id),
            ('product_id', '=', payment_certificate.product_id.id),
        ], limit=1)

        line_quantity = po_line.product_qty if po_line else 0.0
        if line_quantity <= 0:
            line_quantity = payment_certificate.net_weight or 1.0
        unit_price = payment_certificate.net_payable / line_quantity

        return {
            'name': f"Bill Amount against PC: {payment_certificate.name}",
            'product_id': payment_certificate.product_id.id if payment_certificate.product_id else False,
            'display_type': PRODUCT_LINE_TYPE,
            'sequence': DEFAULT_LINE_SEQUENCE,
            'quantity': line_quantity,
            'price_unit': unit_price,
        }

    @api.model
    def _prepare_pc_bill_vals(self, payment_certificate: 'payment.certificate') -> Dict[str, Any]:
        """Protocol 4.1 (DRY): Full mapping used by the UI onchange."""
        return {
            **self._prepare_pc_bill_header_vals(payment_certificate),
            'invoice_line_ids': [
                (COMMAND_CLEAR_ALL, 0, 0),
                (COMMAND_CREATE_NEW, 0, self._prepare_pc_bill_line_vals(payment_certificate)),
            ],
        }

    # ==========================================================
    # UI ENTRY POINT (onchange)
    # ==========================================================

    @api.onchange('broker_id')
    def _onchange_broker_id_reset_payment_certificate(self) -> None:
        """Protocol 2.1 (SRP): Reset the PC when the Broker no longer matches."""
        if self.payment_certificate_id and self.payment_certificate_id.broker_id != self.broker_id:
            self.payment_certificate_id = False
            self.rice_pc_amount = 0.0

    @api.onchange('payment_certificate_id')
    def _onchange_payment_certificate_id(self) -> None:
        """Protocol 2.1 (SRP): Immediate UI feedback when a PC is selected."""
        if not self.payment_certificate_id or self.move_type != VENDOR_BILL_MOVE_TYPE:
            return
        self.update(self._prepare_pc_bill_vals(self.payment_certificate_id))

    # ==========================================================
    # POST-SAVE NORMALIZATION
    # (Ports the old line_helper compute's guarantee: after ANY save of a
    # PC-linked draft bill, exactly one correct line exists. Runs server-side,
    # so placeholder rows the form's line manager sneaks into the payload
    # never reach the database. Scoped to draft vendor bills with a PC only.)
    # ==========================================================

    def _enforce_pc_bill_lines(self) -> None:
        """Idempotent: wipe and rebuild the JV line + amount from the PC.
        Skips posted/cancelled bills and bills without a PC."""
        for move in self:
            if move.move_type != VENDOR_BILL_MOVE_TYPE:
                continue
            if not move.payment_certificate_id:
                continue
            if move.state != DRAFT_STATE:
                continue

            move.with_context(**{NORMALIZATION_CONTEXT_FLAG: True}).write({
                'rice_pc_amount': move.payment_certificate_id.net_payable,
                'invoice_line_ids': [
                    (COMMAND_CLEAR_ALL, 0, 0),
                    (COMMAND_CREATE_NEW, 0, self._prepare_pc_bill_line_vals(move.payment_certificate_id)),
                ],
            })

    def _is_phantom_bill_line(self, line_vals: Dict[str, Any]) -> bool:
        """Defense in depth: an empty placeholder create command from the
        bill form's quick-entry row. Sections/notes/tax lines never match."""
        if line_vals.get('display_type') not in (False, None, PRODUCT_LINE_TYPE):
            return False
        line_name = (line_vals.get('name') or '').strip()
        return (
            not line_vals.get('product_id')
            and not line_name
            and not (line_vals.get('price_unit') or 0.0)
        )

    def _strip_phantom_bill_lines(self, commands: List[Any]) -> List[Any]:
        """Protocol 2.6: pure filter over ORM commands."""
        return [
            command for command in commands
            if not (command[0] == COMMAND_CREATE_NEW and self._is_phantom_bill_line(command[2]))
        ]

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'AccountMove':
        """Create, then normalize: any PC-linked draft bill ends with exactly
        one rebuilt line regardless of what the client payload contained."""
        records = super().create(vals_list)
        pc_bills = records.filtered(lambda move: move.payment_certificate_id)
        if pc_bills:
            pc_bills._enforce_pc_bill_lines()
        return records

    def write(self, vals: Dict[str, Any]) -> bool:
        """Strip placeholder lines defensively, and re-normalize whenever the
        PC itself changes (mirrors the old compute's recompute trigger, so
        manual edits to a bill whose PC did not change are left alone)."""
        if 'invoice_line_ids' in vals and not self.env.context.get(NORMALIZATION_CONTEXT_FLAG):
            if any(rec.move_type == VENDOR_BILL_MOVE_TYPE for rec in self):
                vals['invoice_line_ids'] = self._strip_phantom_bill_lines(vals['invoice_line_ids'])

        result = super().write(vals)

        if 'payment_certificate_id' in vals and not self.env.context.get(NORMALIZATION_CONTEXT_FLAG):
            self._enforce_pc_bill_lines()
        return result