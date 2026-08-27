# -*- coding: utf-8 -*-

from odoo import models, fields, api
from typing import Dict, Any


class SmartButtonMixin(models.AbstractModel):
    """Provides reusable logic for smart button counters and navigation."""
    _name = 'smart.button.mixin'
    _description = 'Smart Button Navigation Mixin'

    def _get_related_record_count_batch(self, target_model: str, domain_field: str) -> Dict[int, int]:
        """Phase 4 Fix: Batch read_group to prevent N+1 queries in list views."""
        if not self.ids:
            return {}

        domain = [(domain_field, 'in', self.ids)]
        groups = self.env[target_model].read_group(domain, [domain_field], [domain_field])

        counts = {
            g[domain_field][0] if isinstance(g[domain_field], tuple) else g[domain_field]: g[f'{domain_field}_count']
            for g in groups}
        return {rec_id: counts.get(rec_id, 0) for rec_id in self.ids}

    def _get_related_record_count(self, target_model: str, domain_field: str) -> int:
        """Legacy single-record method, refactored to use batch."""
        self.ensure_one()
        return self._get_related_record_count_batch(target_model, domain_field).get(self.id, 0)

    def _open_related_records(self, target_model: str, domain_field: str, display_name: str) -> Dict[str, Any]:
        self.ensure_one()
        records = self.env[target_model].search([(domain_field, '=', self.id)])

        if not records:
            return {'type': 'ir.actions.act_window_close'}

        if len(records) == 1:
            return self._open_form_view(target_model, records.id, display_name)

        return {
            'type': 'ir.actions.act_window',
            'name': f"{display_name}s",
            'res_model': target_model,
            'view_mode': 'list,form',
            'domain': [(domain_field, '=', self.id)],
            'target': 'current',
        }

    def _open_form_view(self, target_model: str, record_id: int, display_name: str) -> Dict[str, Any]:
        """Protocol 4.1 (DRY): Standardized single-record form view navigation."""
        if not record_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': display_name,
            'res_model': target_model,
            'view_mode': 'form',
            'res_id': record_id,
            'target': 'current',
        }


class PurchaseOrderLineMapperMixin(models.AbstractModel):
    _name = 'purchase.order.line.mapper.mixin'
    _description = 'Purchase Order Line Mapper Mixin'

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', required=False)
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line', string='PO Product Line',
        domain="[('order_id', '=', purchase_order_id)]"
    )

    def _apply_po_line_values(self, po_line: 'purchase.order.line') -> None:
        """Protocol 3.5 (DIP): Hook for subclasses to implement specific mapping logic."""
        pass