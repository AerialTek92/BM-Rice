# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from typing import Any, Dict, List

KG_PER_MT: float = 1000.0


class BrandStockWizard(models.TransientModel):
    _name = 'brand.stock.wizard'
    _description = 'Brand Stock Report Wizard'

    date_as_at = fields.Date(string='As At Date', required=True,
                             default=fields.Date.today)

    def action_view(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref(
            'am_broker_setup.action_report_brand_stock_html'
        ).report_action(self, data=self._prepare_report_data())

    def action_print(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref(
            'am_broker_setup.action_report_brand_stock_pdf'
        ).report_action(self, data=self._prepare_report_data())

    def _prepare_report_data(self) -> Dict[str, Any]:
        """NOTE: report data crosses the report_action() boundary, which
        JSON-serializes it - dates do not survive. Everything returned
        here is a string / number / list / dict.

        Product scope: Odoo 17+ removed the 'product' value from the type
        field - storable products are found via is_storable."""
        self.ensure_one()
        as_at = fields.Datetime.to_datetime(f'{self.date_as_at} 23:59:59')
        year_start = self.date_as_at.replace(month=1, day=1)

        return {
            'date_as_at': self.date_as_at.strftime('%d/%m/%Y'),
            'raw_section': self._build_section(
                [('is_storable', '=', True), ('is_raw_rice', '=', True)],
                as_at, year_start, is_raw=True),
            'process_section': self._build_section(
                [('is_storable', '=', True), ('is_process_rice', '=', True)],
                as_at, year_start, is_raw=False),
        }

    def _build_section(self, domain, as_at, year_start, is_raw: bool) -> Dict[str, Any]:
        products = self.env['product.product'].search(domain, order='name asc')
        lines: List[Dict[str, Any]] = []
        totals = {'opening': 0.0, 'movement_in': 0.0, 'movement_out': 0.0, 'closing': 0.0}

        for product in products:
            opening = self._internal_qty_between(product, None, year_start)
            ytd_in, ytd_out = self._movement_between(product, year_start, as_at)
            closing = self._internal_qty_between(product, None, as_at)

            if not (opening or ytd_in or ytd_out or closing):
                continue

            lines.append({
                'name': product.display_name,
                'opening': opening / KG_PER_MT,
                'movement_in': ytd_in / KG_PER_MT,
                'movement_out': ytd_out / KG_PER_MT,
                'closing': closing / KG_PER_MT,
            })
            totals['opening'] += opening / KG_PER_MT
            totals['movement_in'] += ytd_in / KG_PER_MT
            totals['movement_out'] += ytd_out / KG_PER_MT
            totals['closing'] += closing / KG_PER_MT

        return {
            'title': 'Raw Rice' if is_raw else 'Process Rice',
            'in_header': 'Purchases (Mt)' if is_raw else 'Production (Mt)',
            'out_header': 'Issues (Mt)' if is_raw else 'Packing / Sales (Mt)',
            'lines': lines,
            'totals': totals,
        }

    def _internal_qty_between(self, product, date_from, date_to) -> float:
        """On-hand in internal locations at end of date_to (kg)."""
        domain = [
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '<=', date_to),
        ]
        if date_from:
            domain.append(('date', '>=', fields.Datetime.to_datetime(f'{date_from} 00:00:00')))
        lines = self.env['stock.move.line'].search(domain)
        qty = 0.0
        for line in lines:
            if line.location_dest_id.usage == 'internal':
                qty += line.quantity
            if line.location_id.usage == 'internal':
                qty -= line.quantity
        return qty

    def _movement_between(self, product, date_from, date_to) -> tuple:
        """(in, out) across the internal-stock boundary within the range (kg)."""
        lines = self.env['stock.move.line'].search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '>=', fields.Datetime.to_datetime(f'{date_from} 00:00:00')),
            ('date', '<=', date_to),
        ])
        qty_in = 0.0
        qty_out = 0.0
        for line in lines:
            if line.location_dest_id.usage == 'internal' and line.location_id.usage != 'internal':
                qty_in += line.quantity
            elif line.location_id.usage == 'internal' and line.location_dest_id.usage != 'internal':
                qty_out += line.quantity
        return qty_in, qty_out


class ReportBrandStock(models.AbstractModel):
    """Report bridge for the Brand Stock template - carries the wizard's
    data dict into the QWeb rendering context."""
    _name = 'report.am_broker_setup.report_brand_stock'
    _description = 'Brand Stock Report'

    def _get_report_values(self, docids, data=None):
        return {
            'data': data or {},
            'doc_ids': docids,
            'doc_model': 'brand.stock.wizard',
        }