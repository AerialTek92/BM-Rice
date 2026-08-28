# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.exceptions import ValidationError


class GatePassLocalSales(models.Model):
    _inherit = 'gate.pass'

    @api.constrains('delivery_picking_id', 'pass_type')
    def _check_delivery_order_commercially_approved(self) -> None:
        """Server-side twin of the D/O dropdown filter.

        Hiding unapproved Delivery Orders from the dropdown is UI-only; this
        constraint guards every other path (list-view edits, imports, RPC).
        Export deliveries are out of scope: their flow has no commercial
        validation step."""
        for gate_pass in self:
            picking = gate_pass.delivery_picking_id
            if gate_pass.pass_type != 'outbound' or not picking:
                continue
            if picking.state in ('done', 'cancel'):
                continue
            if picking._is_local_sale_delivery() and not picking.is_commercially_validated:
                raise ValidationError(_(
                    "Delivery Order %(picking)s has not been commercially validated yet. "
                    "The Sales user must approve its D/O Qty before a Gate Pass can reference it.",
                    picking=picking.name,
                ))