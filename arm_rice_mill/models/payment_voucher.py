# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from typing import Dict, Any, List


class AccountMove(models.Model):
    _inherit = 'account.move'

    # NEW: Separate Broker field (distinct from Vendor/Supplier)
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

    # NEW: Link to Payment Certificate (Domain filters by selected Broker)
    payment_certificate_id = fields.Many2one(
        'payment.certificate',
        string='Payment Certificate Ref',
        domain="[('broker_id', '=', broker_id), ('state', 'in', ['confirmed', 'paid'])]"
    )

    # NEW: Field to display the mapped amount from the PC
    rice_pc_amount = fields.Monetary(
        string='Rice PC Amount',
        currency_field='currency_id',
        readonly=True,
        store=True
    )

    line_helper = fields.Boolean(string="Line Helper", store=True, compute='_compute_line_helper')

    @api.depends('payment_certificate_id')
    def _compute_line_helper(self):
        for rec in self:
            rec.line_helper = True
            pc = rec.payment_certificate_id

            if not pc:
                rec['rice_pc_amount'] = 0.0
                rec['invoice_line_ids'] = [(5, 0, 0)]
                continue  # <-- key fix: stop here for THIS record, don't fall through
            if rec.move_type == 'in_invoice':
                # raise UserError("Pawan")
                # Update header fields
                rec['partner_id'] = pc.partner_id.id
                rec['rice_pc_amount'] = pc.net_payable
                rec['ref'] = f"PC: {pc.name} / PO: {pc.purchase_id.name or ''}"
                rec['invoice_date'] = pc.date
                rec['payment_reference'] = pc.name

                po_line = self.env['purchase.order.line'].search([
                    ('order_id', '=', pc.purchase_id.id),
                    ('product_id', '=', pc.product_id.id),
                ], limit=1)

                line_vals = {
                    'name': f"Bill Amount against PC: {pc.name}",
                    'product_id': pc.product_id.id if pc.product_id else False,
                    'price_unit': pc.net_payable,
                    'quantity': po_line.product_qty if po_line else 1.0,
                }

                # Command.clear() + Command.create() is the Odoo 17+ idiomatic
                # equivalent of (5,0,0) + (0,0,vals) — same semantics, clearer intent
                rec['invoice_line_ids'] = [(5, 0, 0), (0, 0, line_vals)]

    # @api.onchange('broker_id')
    # def _onchange_broker_id_for_payment_voucher(self) -> None:
    #     """Protocol 2.1 (SRP): Reset PC if Broker changes."""
    #     if self.payment_certificate_id and self.payment_certificate_id.broker_id.id != self.broker_id.id:
    #         self.payment_certificate_id = False
    #         self.rice_pc_amount = 0.0

    # @api.onchange('payment_certificate_id')
    # def _onchange_payment_certificate_id(self) -> None:
    #     for rec in self:
    #         pc = rec.payment_certificate_id
    #
    #         if not pc or rec.move_type != 'in_invoice':
    #             rec.invoice_line_ids = [Command.clear()]
    #             rec.rice_pc_amount = 0.0
    #             continue  # <-- key fix: stop here for THIS record, don't fall through
    #
    #         # Update header fields
    #         rec.partner_id = pc.partner_id.id
    #         rec.rice_pc_amount = pc.net_payable
    #         rec.ref = f"PC: {pc.name} / PO: {pc.purchase_id.name or ''}"
    #         rec.invoice_date = pc.date
    #         rec.payment_reference = pc.name
    #
    #         po_line = self.env['purchase.order.line'].search([
    #             ('order_id', '=', pc.purchase_id.id),
    #             ('product_id', '=', pc.product_id.id),
    #         ], limit=1)
    #
    #         line_vals = {
    #             'name': f"Bill Amount against PC: {pc.name}",
    #             'product_id': pc.product_id.id if pc.product_id else False,
    #             'price_unit': pc.net_payable,
    #             'quantity': po_line.product_qty if po_line else 1.0,
    #         }
    #
    #         # Command.clear() + Command.create() is the Odoo 17+ idiomatic
    #         # equivalent of (5,0,0) + (0,0,vals) — same semantics, clearer intent
    #         rec.invoice_line_ids = [Command.clear(), Command.create(line_vals)]
    # # @api.onchange('payment_certificate_id')
    # def _onchange_payment_certificate_id(self) -> None:
    #     for rec in self:
    #         if not rec.payment_certificate_id or rec.move_type != 'in_invoice':
    #             rec.invoice_line_ids = False
    #
    #             # return
    #
    #         pc = rec.payment_certificate_id
    #
    #         # Update header fields first
    #         # self.update({
    #         rec.partner_id = pc.partner_id.id  # Auto-map the Vendor (Supplier)
    #         rec.rice_pc_amount = pc.net_payable
    #         rec.ref = f"PC: {pc.name} / PO: {pc.purchase_id.name or ''}"  # Map to Remarks
    #         rec.invoice_date = pc.date  # Map PC date to Voucher Date
    #         rec.payment_reference = pc.name
    #         # })
    #
    #         # FIX: Fetch the product_qty from the matching purchase.order.line
    #         po_line = self.env['purchase.order.line'].search([
    #             ('order_id', '=', pc.purchase_id.id),
    #             ('product_id', '=', pc.product_id.id)
    #         ], limit=1)
    #
    #         # Prepare line values
    #         line_vals = {
    #             'name': f"Bill Amount against PC: {pc.name}",
    #             'product_id': pc.product_id.id if pc.product_id else False,
    #             'price_unit': pc.net_payable,
    #             'quantity': po_line.product_qty if po_line else 1.0,  # Safely map the quantity
    #         }
    #
    #         # FIX: Use simple clear and create commands.
    #         # This allows Odoo 19's native line manager to handle sequencing without duplication conflicts.
    #         rec.invoice_line_ids = [(5, 0, 0), (0, 0, line_vals)]

        # """Protocol 2.1 (SRP): Map PC details to Payment Voucher (Vendor Bill)."""
        # if not self.payment_certificate_id or self.move_type != 'in_invoice':
        #     return
        #
        # pc = self.payment_certificate_id
        #
        # # Update header fields first
        # self.update({
        #     'partner_id': pc.partner_id.id,  # Auto-map the Vendor (Supplier)
        #     'rice_pc_amount': pc.net_payable,
        #     'ref': f"PC: {pc.name} / PO: {pc.purchase_id.name or ''}",  # Map to Remarks
        #     'invoice_date': pc.date,  # Map PC date to Voucher Date
        #     'payment_reference': pc.name,
        # })
        #
        # # FIX: Fetch the product_qty from the matching purchase.order.line
        # po_line = self.env['purchase.order.line'].search([
        #     ('order_id', '=', pc.purchase_id.id),
        #     ('product_id', '=', pc.product_id.id)
        # ], limit=1)
        #
        # # Prepare line values
        # line_vals = {
        #     'name': f"Bill Amount against PC: {pc.name}",
        #     'product_id': pc.product_id.id if pc.product_id else False,
        #     'price_unit': pc.net_payable,
        #     'quantity': po_line.product_qty if po_line else 1.0,  # Safely map the quantity
        # }
        #
        # # FIX: Use simple clear and create commands.
        # # This allows Odoo 19's native line manager to handle sequencing without duplication conflicts.
        # self.invoice_line_ids = [(5, 0, 0), (0, 0, line_vals)]

    # def _clean_phantom_lines(self, lines: List) -> List:
    #     """Protocol 4.1 (DRY): Shared logic to aggressively filter out empty/phantom lines."""
    #     cleaned_lines = []
    #     for cmd in lines:
    #         # If it's a create command (0, 0, vals)
    #         if cmd[0] == 0:
    #             line_data = cmd[2]
    #             # Aggressively skip ANY line that has no price AND no quantity
    #             if not line_data.get('price_unit') and not line_data.get('quantity'):
    #                 continue
    #         cleaned_lines.append(cmd)
    #     return cleaned_lines

    # @api.model_create_multi
    # def create(self, vals_list: List[Dict[str, Any]]) -> 'AccountMove':
    #     """Protocol 2.1 (SRP): Override create to filter out phantom $0.00 lines."""
    #     for vals in vals_list:
    #         if vals.get('move_type') == 'in_invoice' and vals.get('invoice_line_ids'):
    #             vals['invoice_line_ids'] = self._clean_phantom_lines(vals['invoice_line_ids'])
    #     return super().create(vals_list)

    # def write(self, vals):
    #     res = super().write(vals)
    #     if 'payment_certificate_id' in vals:
    #         for rec in self:
    #             if not rec.payment_certificate_id or rec.move_type != 'in_invoice':
    #                 return
    #
    #             pc = rec.payment_certificate_id
    #
    #             # Update header fields first
    #             # self.update({
    #             rec.partner_id = pc.partner_id.id  # Auto-map the Vendor (Supplier)
    #             rec.rice_pc_amount = pc.net_payable
    #             rec.ref = f"PC: {pc.name} / PO: {pc.purchase_id.name or ''}"  # Map to Remarks
    #             rec.invoice_date = pc.date  # Map PC date to Voucher Date
    #             rec.payment_reference = pc.name
    #             # })
    #
    #             # FIX: Fetch the product_qty from the matching purchase.order.line
    #             po_line = self.env['purchase.order.line'].search([
    #                 ('order_id', '=', pc.purchase_id.id),
    #                 ('product_id', '=', pc.product_id.id)
    #             ], limit=1)
    #
    #             # Prepare line values
    #             line_vals = {
    #                 'name': f"Bill Amount against PC: {pc.name}",
    #                 'product_id': pc.product_id.id if pc.product_id else False,
    #                 'price_unit': pc.net_payable,
    #                 'quantity': po_line.product_qty if po_line else 1.0,  # Safely map the quantity
    #             }
    #
    #             # FIX: Use simple clear and create commands.
    #             # This allows Odoo 19's native line manager to handle sequencing without duplication conflicts.
    #             self.invoice_line_ids = [(5, 0, 0), (0, 0, line_vals)]
    #


