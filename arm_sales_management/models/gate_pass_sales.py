# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# --- Outbound Gate Pass (Local Sales) constants ---
OUTBOUND_PASS_TYPE: str = 'outbound'
GATE_PASS_WB_CONTEXT: str = 'wb_gate_pass_view'


class GatePassLocalSales(models.Model):
    _inherit = 'gate.pass'

    # D/O Date shown readonly on the outbound Gate Pass, read from the
    # selected Delivery Order (sales module's delivery_order_date field).
    delivery_order_date = fields.Date(
        related='delivery_picking_id.delivery_order_date',
        string='D/O Date',
        readonly=True,
    )

    # ==========================================================
    # WEIGHBRIDGE PICKER: "GP/26/0001 | ABC-123", searchable by
    # Vehicle No (or GP No). Context-gated so every other gate pass
    # picker in the system keeps its plain name.
    # ==========================================================

    @api.depends('name', 'vehicle_number')
    @api.depends_context('wb_gate_pass_view')
    def _compute_display_name(self) -> None:
        if self.env.context.get(GATE_PASS_WB_CONTEXT):
            for rec in self:
                if rec.vehicle_number:
                    rec.display_name = f"{rec.name or ''} | {rec.vehicle_number}"
                else:
                    rec.display_name = rec.name or ''
        else:
            super()._compute_display_name()

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """In the Weighbridge GP picker: match by Vehicle No OR GP number."""
        if self.env.context.get(GATE_PASS_WB_CONTEXT) and name:
            domain = (domain or []) + [
                '|',
                ('vehicle_number', operator, name),
                ('name', operator, name),
            ]
            records = self.search(domain, limit=limit)
            return [(rec.id, rec.display_name) for rec in records]
        return super().name_search(name, domain=domain, operator=operator, limit=limit)

    # ==========================================================
    # OUTBOUND FORM FLOW: Customer -> Delivery Order
    # ==========================================================

    @api.onchange('partner_id')
    def _onchange_partner_id_outbound(self) -> None:
        """Customer changed on an outbound Gate Pass: drop the Delivery Order
        if it no longer belongs to the new customer."""
        if (self.pass_type == OUTBOUND_PASS_TYPE
                and self.delivery_picking_id
                and self.delivery_picking_id.partner_id != self.partner_id):
            self.delivery_picking_id = False

    @api.onchange('delivery_picking_id')
    def _onchange_delivery_picking_id_outbound(self) -> None:
        """D/O selected: map its customer and date; derive the Sales Memo
        (machinery - not user-facing here, but downstream consumers read it)."""
        if not self.delivery_picking_id or self.pass_type != OUTBOUND_PASS_TYPE:
            return

        picking = self.delivery_picking_id

        # Customer follows the Delivery Order (single source of truth).
        if not self.partner_id or self.partner_id != picking.partner_id:
            self.partner_id = picking.partner_id.id

        # Machinery: the SM derived from the D/O.
        self.sale_order_id = picking.sale_id.id

        # If Export, auto-map the Sales Contract straight from the Delivery
        # Order's contract link (export DOs have no Sales Memo).
        if self.is_export and picking.rice_sales_contract_id:
            self.export_sales_contract_id = picking.rice_sales_contract_id.id
        line_vals = [(5, 0, 0)]
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            sale_line = move.sale_line_id
            line_vals.append((0, 0, {
                'sale_order_id': picking.sale_id.id,
                'sale_line_id': sale_line.id if sale_line else False,
                'product_id': move.product_id.id,
                'do_demand_qty': move.quantity,
                'location_dest_id': move.location_dest_id.id,
                'return_qty': move.product_uom_qty,
                'pcs': move.pcs or 0.0,
                'ctn': move.ctn or 0.0,
                'gross': 0.0,
                'net': 0.0,
                'additional_weight': move.additional_weight or 0.0,
                'total_weight': move.total_weight or 0.0,
            }))
        self.gate_pass_line_ids = line_vals

    @api.constrains('delivery_picking_id', 'pass_type')
    def _check_delivery_order_commercially_approved(self) -> None:
        """Server-side twin of the D/O dropdown filter (list edits, imports, RPC).
        Export deliveries are out of scope: no commercial validation step."""
        for gate_pass in self:
            picking = gate_pass.delivery_picking_id
            if gate_pass.pass_type != OUTBOUND_PASS_TYPE or not picking:
                continue
            if picking.state in ('done', 'cancel'):
                continue
            if picking._requires_commercial_approval() and not picking.is_commercially_validated:
                raise ValidationError(_(
                    "Delivery Order %(picking)s has not been commercially validated yet. "
                    "The Sales user must approve its D/O Qty before a Gate Pass can reference it.",
                    picking=picking.name,
                ))