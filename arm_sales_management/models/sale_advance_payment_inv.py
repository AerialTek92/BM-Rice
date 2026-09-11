# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError
from typing import Any


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def create_invoices(self) -> Any:
        """Server-side enforcement of the invoicing gate.

        Hiding the button is UI-only; this guard blocks every other path that
        reaches the invoicing wizard (Action menu, multi-select invoicing, ...)."""
        active_ids = self.env.context.get('active_ids') or []
        if not active_ids and self.env.context.get('active_id'):
            active_ids = [self.env.context.get('active_id')]

        sale_orders = self.env['sale.order'].browse(active_ids)
        incomplete_orders = sale_orders.filtered(lambda order: not order.is_delivery_complete)

        if incomplete_orders:
            raise UserError(_(
                "Sales Memo(s) %s cannot be invoiced yet: not every line has been fully "
                "delivered. Invoicing unlocks when all demand quantity has been delivered.",
                ", ".join(incomplete_orders.mapped('name')),
            ))
        return super().create_invoices()