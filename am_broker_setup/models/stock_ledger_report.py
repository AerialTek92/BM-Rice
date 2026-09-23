# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from typing import Any, Dict, List

KG_PER_MT: float = 1000.0


class StockLedgerWizard(models.TransientModel):
    _name = 'stock.ledger.wizard'
    _description = 'Stock Ledger Report Wizard'

    date_from = fields.Date(string='From Date', required=True,
                            default=lambda self: fields.Date.today().replace(day=1, month=1))
    date_to = fields.Date(string='To Date', required=True,
                          default=fields.Date.today)
    product_id = fields.Many2one(
        'product.product', string='Product',
        help="Leave empty for ALL products - one ledger section per product.")

    def action_view(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref(
            'am_broker_setup.action_report_stock_ledger_html'
        ).report_action(self, data=self._prepare_report_data())

    def action_print(self) -> Dict[str, Any]:
        self.ensure_one()
        return self.env.ref(
            'am_broker_setup.action_report_stock_ledger_pdf'
        ).report_action(self, data=self._prepare_report_data())

    def _prepare_report_data(self) -> Dict[str, Any]:
        """NOTE: report data crosses the report_action() boundary, which
        JSON-serializes it - everything returned here must be a string /
        number / list / dict. Dates are pre-formatted dd/mm/yyyy.

        Product scope: Odoo 17+ removed the 'product' value from the type
        field - storable products are found via is_storable."""
        self.ensure_one()
        domain_products = [('is_storable', '=', True)]
        if self.product_id:
            domain_products.append(('id', '=', self.product_id.id))
        products = self.env['product.product'].search(domain_products, order='name asc')

        sections: List[Dict[str, Any]] = []
        for product in products:
            rows = self._build_ledger_rows(product, self.date_from, self.date_to)
            # Skip products with no activity - unless the user explicitly
            # selected this one (a single-product request always renders).
            if not rows and not self.product_id:
                continue
            sections.append({
                'product_name': product.display_name,
                'rows': rows,
            })

        return {
            'date_from': self.date_from.strftime('%d/%m/%Y'),
            'date_to': self.date_to.strftime('%d/%m/%Y'),
            'sections': sections,
            'single_product': bool(self.product_id),
        }

    def _build_ledger_rows(self, product, date_from, date_to) -> List[Dict[str, Any]]:
        """One product's ledger: OPENING row, one row per done stock move
        in the range, and a final BALANCE row. Quantities in Mt (kg/1000),
        dates pre-formatted dd/mm/yyyy. Returns an EMPTY list when the
        product has no opening stock and no moves in the range.

        DATE SOURCING (Odoo 19): the move LINE dates are authoritative for
        the 'Update Quantity' flow - the user's date lands on the line
        while the move header keeps the creation date. The candidate set
        is therefore the UNION of (a) moves whose lines fall in range and
        (b) moves whose header falls in range - a header months outside
        the range still enters the ledger when its lines are inside it."""
        opening_qty = self._internal_qty_before(product, date_from)

        range_start = fields.Datetime.to_datetime(f'{date_from} 00:00:00')
        range_end = fields.Datetime.to_datetime(f'{date_to} 23:59:59')

        # (a) moves with at least one LINE dated inside the range
        in_range_lines = self.env['stock.move.line'].search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '>=', range_start),
            ('date', '<=', range_end),
        ])
        line_sourced_moves = in_range_lines.mapped('move_id')

        # (b) moves whose HEADER is dated inside the range
        header_sourced_moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '>=', range_start),
            ('date', '<=', range_end),
        ])

        moves = (line_sourced_moves | header_sourced_moves).filtered(
            lambda move: move.state == 'done').sorted(
            key=lambda move: (self._move_effective_date_obj(move) or date_from, move.id))

        if not moves and not opening_qty:
            return []

        rows: List[Dict[str, Any]] = [{
            'date': False, 'ref_no': '', 'description': 'OPENING',
            'qty_in': 0.0, 'qty_out': 0.0, 'balance': opening_qty / KG_PER_MT,
        }]
        balance = opening_qty

        for move in moves:
            qty_in, qty_out = self._classify_move_direction(move)
            balance += qty_in - qty_out
            rows.append({
                'date': self._move_effective_date(move),
                'ref_no': self._move_reference(move),
                'description': self._move_description(move),
                'qty_in': qty_in / KG_PER_MT,
                'qty_out': qty_out / KG_PER_MT,
                'balance': balance / KG_PER_MT,
            })

        rows.append({
            'date': False, 'ref_no': '', 'description': 'BALANCE',
            'qty_in': 0.0, 'qty_out': 0.0, 'balance': balance / KG_PER_MT,
        })
        return rows

    def _internal_qty_before(self, product, date_from) -> float:
        """On-hand in internal locations at the start of date_from (kg),
        computed from move LINES - the authoritative date source, so a
        line-dated adjustment before the range counts in the opening."""
        lines = self.env['stock.move.line'].search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '<', fields.Datetime.to_datetime(f'{date_from} 00:00:00')),
        ])
        qty = 0.0
        for line in lines:
            if line.location_dest_id.usage == 'internal':
                qty += line.quantity
            if line.location_id.usage == 'internal':
                qty -= line.quantity
        return qty

    def _classify_move_direction(self, move) -> tuple:
        """(qty_in, qty_out) in kg across the internal-stock boundary."""
        qty_in = 0.0
        qty_out = 0.0
        for line in move.move_line_ids:
            if line.location_dest_id.usage == 'internal' and line.location_id.usage != 'internal':
                qty_in += line.quantity
            elif line.location_id.usage == 'internal' and line.location_dest_id.usage != 'internal':
                qty_out += line.quantity
        return qty_in, qty_out

    def _move_reference(self, move) -> str:
        """Reference column: manual on-hand updates show the friendly
        'Product Quantity Updated (User)' phrasing from the moves
        history; everything else shows its document reference."""
        if self._is_inventory_adjustment(move):
            user_name = move.create_uid.name or 'User'
            return f"Product Quantity Updated ({user_name})"
        if move.picking_id:
            return move.picking_id.name or ''
        return move.reference or ''

    def _move_effective_date(self, move) -> str:
        """The move's effective date: move lines carry the authoritative
        date (Odoo 19's Update Quantity writes the line date; header edits
        may not propagate). First line's date, falling back to the move
        header. Pre-formatted dd/mm/yyyy."""
        effective = self._move_effective_date_obj(move)
        return effective.strftime('%d/%m/%Y') if effective else False

    def _move_effective_date_obj(self, move):
        """Date object twin of _move_effective_date: first move line's
        date when present, else the move header date."""
        if move.move_line_ids:
            first_line = move.move_line_ids[:1]
            if first_line.date:
                return first_line.date.date()
        if move.date:
            return move.date.date()
        return False

    def _is_inventory_adjustment(self, move) -> bool:
        """True for manual on-hand updates ('Product Quantity Updated'):
        Odoo 19 creates these as BARE moves (no picking) whose lines move
        from/to an inventory-usage location. Picking-based detection is
        kept as a secondary branch for adjustment pickings that do exist."""
        if move.picking_id:
            picking = move.picking_id
            picking_fields = picking._fields
            if ('is_inventory' in picking_fields and picking.is_inventory) \
                    or picking.picking_type_code == 'inventory':
                return True
        for line in move.move_line_ids:
            if line.location_id.usage == 'inventory' or line.location_dest_id.usage == 'inventory':
                return True
        return False

    def _move_description(self, move) -> str:
        """Human description from the move's context. arm_rice_mill fields
        (GRN / Gate Pass names) are GUARDED: this module loads before
        arm_rice_mill, so direct references would break a standalone
        install - the guard degrades gracefully when absent."""
        if self._is_inventory_adjustment(move):
            return 'ADJUSTMENT'

        picking = move.picking_id
        picking_fields = picking._fields if picking else {}
        if picking:
            if picking.picking_type_code == 'incoming':
                if 'grn_inspection_id' in picking_fields and picking.grn_inspection_id:
                    return f"GRN ({picking.grn_inspection_id.name})"
                if 'material_inspection_id' in picking_fields and picking.material_inspection_id:
                    return f"MATERIAL INSP ({picking.material_inspection_id.name})"
                return 'GRN / RECEIPT'
            if picking.picking_type_code == 'outgoing':
                if 'gate_pass_id' in picking_fields and picking.gate_pass_id:
                    return f"DELIVERY ({picking.gate_pass_id.name})"
                return 'DELIVERY / ISSUE'
            return 'INTERNAL TRANSFER'
        if move.origin_returned_move_id:
            return 'RETURN'
        return 'STOCK MOVE'


class ReportStockLedger(models.AbstractModel):
    """Report bridge: receives the wizard's data dict and exposes it to the
    QWeb template. Without this model, 'data' never reaches the template
    (the KeyError: 'data' failure mode)."""
    _name = 'report.am_broker_setup.report_stock_ledger'
    _description = 'Stock Ledger Report'

    def _get_report_values(self, docids, data=None):
        return {
            'data': data or {},
            'doc_ids': docids,
            'doc_model': 'stock.ledger.wizard',
        }