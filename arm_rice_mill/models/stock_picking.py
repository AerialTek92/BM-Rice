# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Dict, Any, List, Tuple

# --- Searchable Constants (Protocol 1.3) ---
ALLOWANCE_FILL_BAGS: str = 'FILL BAGS'
PICKING_INCOMING: str = 'incoming'
PICKING_OUTGOING: str = 'outgoing'


class StockPicking(models.Model):
    _inherit = ['stock.picking', 'smart.button.mixin']
    _order = 'id desc'

    # NEW: Compute all unique source locations from moves for UI clarity
    multi_source_location_ids = fields.Many2many(
        'stock.location',
        compute='_compute_multi_source_location_ids',
        string='Source Locations'
    )

    # --- Document References ---
    grn_inspection_id = fields.Many2one('grn.inspection', string='Inspection', readonly=True, copy=False)
    gate_pass_id = fields.Many2one('gate.pass', string='Gate Pass', readonly=True, copy=False)
    weighbridge_id = fields.Many2one('weighbridge.ticket', string='Weighbridge', readonly=True, copy=False)
    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract', store=True, readonly=True)
    buyer_id = fields.Many2one('hr.employee', string='Buyer', related='purchase_id.buyer_id', store=True, readonly=True)

    is_third_party = fields.Boolean(
        related='grn_inspection_id.is_third_party',
        string='Third Party / Outsider',
        store=True,
        readonly=True,
    )

    payment_certificate_ids = fields.One2many(
        'payment.certificate',
        'grn_id',
        string='Payment Certificates'
    )

    has_payment_cert = fields.Boolean(
        string='Has Payment Certificate',
        compute='_compute_has_payment_cert',
        store=True
    )

    location_dest_id = fields.Many2one(
        'stock.location',
        domain=[('usage', '=', 'internal')]
    )

    # PI flow: the receipt's source indent, related through the Purchase Order.
    purchase_indent_id = fields.Many2one(
        'purchase.indent', related='purchase_id.purchase_indent_id',
        string='Purchase Indent', store=True, readonly=True)

    material_inspection_id = fields.Many2one('material.inspection', string='Material Inspection',
                                             readonly=True, copy=False)

    # RICE-FLOW GATE: True while the auto-created receipt of a rice PO is
    # still waiting for its Weighbridge (or, third-party, its inspection
    # direct flow). Pending receipts are hidden from the Receipts list and
    # blocked from validation; the WB / inspection confirm sets the link
    # and frees them.
    is_pending_rice_receipt = fields.Boolean(
        string='Pending Weighbridge',
        compute='_compute_is_pending_rice_receipt',
        search='_search_is_pending_rice_receipt',
        help="True while a rice PO's auto-created receipt awaits its Weighbridge "
             "confirmation. Hidden from the Receipts list and blocked from validation "
             "until the Weighbridge (or the third-party inspection flow) takes it over.")

    # --- Header Details ---
    grn_date = fields.Date(string='GRN Date', default=fields.Date.today(), readonly=False)
    product_id = fields.Many2one('product.product', string='Product', help='Primary product for this GRN.',
                                 readonly=True)
    bags = fields.Integer(string='Bags', readonly=True)
    truck_type = fields.Many2one('master.truck.type', string='Truck Type', readonly=True)
    bilty_no = fields.Char(string='Bilty No.', readonly=True)

    filling_bags = fields.Integer(string='Filling Bags', compute='_compute_filling_bags', store=True, readonly=False)

    bilty_weight = fields.Float(string='Bilty Weight')
    deduction = fields.Float(string='Deduction', readonly=False)

    # --- Weights ---
    gross_weight = fields.Float(string='Gross Weight')
    tare_weight = fields.Float(string='Tare Weight')
    net_weight = fields.Float(string='Net Weight')

    # --- Actual Quality ---
    actual_moisture = fields.Float(string='Actual Moisture %', readonly=True)
    actual_broken = fields.Float(string='Actual Broken %', readonly=True)

    # --- Vehicle ---
    vehicle_number = fields.Char(string='Vehicle No.', readonly=True)
    driver_name = fields.Char(string='Driver Name', readonly=True)
    transporter_id = fields.Many2one('res.partner', string='Transporter', readonly=True)

    # Phase 4 Fix (DRY): Use related fields to pull TLS values directly from the Purchase Order
    po_no_of_trucks = fields.Integer(string='Trucks', related='purchase_id.total_trucks', store=False, readonly=True)
    po_total_tls = fields.Float(string='Recv. TLS', related='purchase_id.po_total_tls', store=False, readonly=True)
    po_remaining_tls = fields.Float(string='Rem. TLS', related='purchase_id.po_remaining_tls', store=False, readonly=True)
    po_original_tls = fields.Float(string='Orig. TLS', related='purchase_id.po_original_tls', store=False, readonly=True)

    # added price field
    price_unit = fields.Float(string="Unit Price", compute='_compute_price_unit', store=True, readonly=True)

    @api.depends('move_ids.location_id')
    def _compute_multi_source_location_ids(self) -> None:
        """Protocol 2.1 & 4.2: Single responsibility to map unique source locations from moves."""
        for picking in self:
            # Using mapped() returns a recordset, automatically ensuring unique locations
            picking.multi_source_location_ids = picking.move_ids.mapped('location_id')

    @api.depends('payment_certificate_ids')
    def _compute_has_payment_cert(self) -> None:
        """Protocol 2.1 (SRP): Automatically computed via One2many inverse."""
        for picking in self:
            picking.has_payment_cert = bool(picking.payment_certificate_ids)

    @api.depends('move_ids.purchase_line_id.price_unit')
    def _compute_price_unit(self) -> None:
        for picking in self:
            po_lines = picking.move_ids.mapped('purchase_line_id')
            if po_lines:
                # Assumes one primary product per GRN, matching your existing product_id/bags pattern.
                picking.price_unit = po_lines[:1].price_unit
            else:
                picking.price_unit = picking.price_unit or 0.0

    @api.depends('purchase_id', 'picking_type_code', 'weighbridge_id', 'grn_inspection_id',
                 'purchase_indent_id', 'material_inspection_id')
    def _compute_is_pending_rice_receipt(self) -> None:
        """Pending = a rice PO's incoming picking with no Weighbridge and no
        inspection link yet. Indent and Material Inspection receipts are
        exempt (their flows validate directly)."""
        for picking in self:
            picking.is_pending_rice_receipt = bool(
                picking.picking_type_code == 'incoming'
                and picking.purchase_id
                and not picking.purchase_indent_id
                and not picking.material_inspection_id
                and not picking.weighbridge_id
                and not picking.grn_inspection_id
            )

    def _search_is_pending_rice_receipt(self, operator: str, value: Any) -> List[Any]:
        """Search twin: the Receipts-list action domain excludes pending
        pickings (see stock_picking_views.xml)."""
        exclude = (operator == '=' and not value) or (operator == '!=' and value)
        if exclude:
            return ['|', '|', '|', '|',
                    ('picking_type_code', '!=', 'incoming'),
                    ('purchase_id', '=', False),
                    ('purchase_indent_id', '!=', False),
                    ('weighbridge_id', '!=', False),
                    ('grn_inspection_id', '!=', False)]
        return ['&', '&', '&', '&',
                ('picking_type_code', '=', 'incoming'),
                ('purchase_id', '!=', False),
                ('weighbridge_id', '=', False),
                ('grn_inspection_id', '=', False)]

    @api.model_create_multi
    def create(self, vals_list):
        """Custom DO sequences:
        - Export (RSC-linked): EXP/DO/YY/NNN — detected in vals (pre-create)
        - Local (SM-linked): SM/DO/YY/NNN — detected on the record (post-create)
        """
        # Pre-create: Export DOs (rice_sales_contract_id is in the vals)
        for vals in vals_list:
            if (vals.get('name', _('New')) == _('New')
                    and vals.get('rice_sales_contract_id')):
                picking_type_id = vals.get('picking_type_id')
                if picking_type_id:
                    picking_type = self.env['stock.picking.type'].browse(picking_type_id)
                    if picking_type.code == 'outgoing':
                        vals['name'] = self.env['ir.sequence'].next_by_code('do.export')

        pickings = super().create(vals_list)

        # Post-create: Local DOs (sale_id is a stored related field,
        # computed from group_id — available on the RECORD after creation)
        for picking in pickings:
            if (picking.picking_type_code == 'outgoing'
                    and not picking.rice_sales_contract_id
                    and picking.sale_id
                    and not picking.name.startswith(('SM/DO/', 'EXP/DO/'))):
                picking.name = self.env['ir.sequence'].next_by_code('do.local')

            # Existing: inherit contract from the Sales Memo
            if not picking.rice_sales_contract_id and picking.sale_id:
                if 'rice_sales_contract_id' in picking.sale_id._fields and picking.sale_id.rice_sales_contract_id:
                    picking.rice_sales_contract_id = picking.sale_id.rice_sales_contract_id.id
        return pickings

    def _apply_local_delivery_sequence(self) -> None:
        """Deterministic local-DO naming (SM/DO/YY/NNN). Called from the
        Sales Memo's action_confirm AFTER the stock rule created and
        natively named the pickings: whatever ordering quirks the picking
        creation machinery has, this window runs last and wins. Already-
        named pickings (SM/DO, EXP/DO) and contract-linked DOs are skipped,
        so no sequence number is ever consumed twice."""
        for picking in self:
            if (picking.picking_type_code == PICKING_OUTGOING
                    and not picking.rice_sales_contract_id
                    and not (picking.name or '').startswith(('SM/DO/', 'EXP/DO/'))):
                picking.name = self.env['ir.sequence'].next_by_code('do.local')

    # --- Fix: Name Search to allow searching STRICTLY by Vehicle No in Payment Certificate ---
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Search strictly by vehicle number if context dictates (Odoo 19 Compatible)."""
        if self.env.context.get('payment_cert_grn_view') and name:
            # 1. Preserve the field's default domain (incoming + done)
            # 2. And search strictly by Truck Number (vehicle_number)
            domain = (domain or []) + [('vehicle_number', operator, name)]

            records = self.search(domain, limit=limit)

            # Odoo 19 expects a list of (id, display_name)
            return [(rec.id, rec.display_name) for rec in records]

        return super().name_search(name, domain=domain, operator=operator, limit=limit)

    @api.depends('name', 'vehicle_number', 'purchase_id.broker_id', 'net_weight')
    def _compute_display_name(self) -> None:
        super()._compute_display_name()

        if self.env.context.get('payment_cert_grn_view'):
            for picking in self:
                parts = [picking.name or '']
                if picking.vehicle_number:
                    parts.append(picking.vehicle_number)
                if picking.purchase_id and picking.purchase_id.broker_id:
                    parts.append(picking.purchase_id.broker_id.name)

                if picking.net_weight > 0:
                    formatted_weight = f"{picking.net_weight:,.0f}"
                    parts.append(formatted_weight)

                picking.display_name = " | ".join(parts)

    @api.constrains('picking_type_id', 'grn_inspection_id', 'weighbridge_id')
    def _check_picking_type_integrity(self) -> None:
        """Protocol 1.3 & 3.1: Prevent architectural bypass of TLS logic via Operation Type changes."""
        for picking in self:
            # If the picking is part of the custom Rice Mill flow, lock the operation type context
            if picking.grn_inspection_id or picking.weighbridge_id:
                if picking.picking_type_code not in (PICKING_INCOMING, PICKING_OUTGOING):
                    raise ValidationError(_(
                        "Operation Type for Rice Mill GRNs/Returns must be strictly Incoming or Outgoing. "
                        "You cannot manually change it to an Internal Transfer."
                    ))

    # --- Final QC Related Fields ---
    final_sample_no = fields.Char(related='grn_inspection_id.sample_no', string='Final Sample No', readonly=True)
    final_b1_percent = fields.Float(related='grn_inspection_id.b1_percent', string='Final B1 %', readonly=True)
    final_damage_yellow_shriveled_percent = fields.Float(related='grn_inspection_id.damage_yellow_shriveled_percent',
                                                         string='Final Dmg/Yellow/Shriv %', readonly=True)
    final_chalky_immature_percent = fields.Float(related='grn_inspection_id.chalky_immature_percent',
                                                 string='Final Chalky/Imm %', readonly=True)
    final_foreign_grain_percent = fields.Float(related='grn_inspection_id.foreign_grain_percent',
                                               string='Final Foreign Grain %', readonly=True)
    final_fungus_grain_percent = fields.Float(related='grn_inspection_id.fungus_grain_percent', string='Final Fungus %',
                                              readonly=True)
    final_red_rice_percent = fields.Float(related='grn_inspection_id.red_rice_percent', string='Final Red Rice %',
                                          readonly=True)
    final_foreign_matter_percent = fields.Float(related='grn_inspection_id.foreign_matter_percent',
                                                string='Final Foreign Matter %', readonly=True)
    final_paddy_grain_percent = fields.Float(related='grn_inspection_id.paddy_grain_percent',
                                             string='Final Paddy Grain %', readonly=True)
    final_damage_grain_percent = fields.Float(related='grn_inspection_id.damage_grain_percent',
                                              string='Final Damage Grain %', readonly=True)
    final_inspection_status = fields.Selection(related='grn_inspection_id.inspection_status', string='Final QC Status',
                                               readonly=True)

    # --- Initial QC Related Fields ---
    initial_sample_no = fields.Char(related='grn_inspection_id.initial_sample_no', string='Initial Sample No',
                                    readonly=True)
    initial_moisture_percent = fields.Float(related='grn_inspection_id.initial_moisture_percent',
                                            string='Init Moisture %', readonly=True)
    initial_broken_percent = fields.Float(related='grn_inspection_id.initial_broken_percent', string='Init Broken %',
                                          readonly=True)
    initial_b1_percent = fields.Float(related='grn_inspection_id.initial_b1_percent', string='Init B1 %', readonly=True)
    initial_damage_yellow_shriveled_percent = fields.Float(
        related='grn_inspection_id.initial_damage_yellow_shriveled_percent', string='Init Dmg/Yellow/Shriv %',
        readonly=True)
    initial_chalky_immature_percent = fields.Float(related='grn_inspection_id.initial_chalky_immature_percent',
                                                   string='Init Chalky/Imm %', readonly=True)
    initial_foreign_grain_percent = fields.Float(related='grn_inspection_id.initial_foreign_grain_percent',
                                                 string='Init Foreign Grain %', readonly=True)
    initial_fungus_grain_percent = fields.Float(related='grn_inspection_id.initial_fungus_grain_percent',
                                                string='Init Fungus %', readonly=True)
    initial_red_rice_percent = fields.Float(related='grn_inspection_id.initial_red_rice_percent',
                                            string='Init Red Rice %', readonly=True)
    initial_foreign_matter_percent = fields.Float(related='grn_inspection_id.initial_foreign_matter_percent',
                                                  string='Init Foreign Matter %', readonly=True)
    initial_paddy_grain_percent = fields.Float(related='grn_inspection_id.initial_paddy_grain_percent',
                                               string='Init Paddy Grain %', readonly=True)
    initial_damage_grain_percent = fields.Float(related='grn_inspection_id.initial_damage_grain_percent',
                                                string='Init Damage Grain %', readonly=True)
    initial_inspection_status = fields.Selection(related='grn_inspection_id.initial_inspection_status',
                                                 string='Init QC Status', readonly=True)

    remarks = fields.Html(string='Remarks')

    @api.depends('net_weight', 'product_id', 'grn_date')
    def _compute_filling_bags(self) -> None:
        for picking in self:
            filling_bags = 0
            if picking.product_id and picking.net_weight > 0:
                product_tmpl = picking.product_id.product_tmpl_id
                check_date = picking.grn_date or fields.Date.today()

                if product_tmpl.allowance_type_ids:
                    fill_bag_type = product_tmpl.allowance_type_ids.filtered(
                        lambda t: t.name == ALLOWANCE_FILL_BAGS or t.code == ALLOWANCE_FILL_BAGS
                    )

                    if fill_bag_type:
                        fill_bag_lines = fill_bag_type[0].template_line_ids.filtered(
                            lambda l: (not l.from_date or l.from_date <= check_date)
                                      and (not l.to_date or l.to_date >= check_date)
                        )

                        if fill_bag_lines:
                            rate_per_kg = fill_bag_lines[:1].rate_per_kg
                            if rate_per_kg > 0:
                                filling_bags = int(picking.net_weight / rate_per_kg)

            picking.filling_bags = filling_bags

    # --- Navigation Smart Button Actions ---
    def action_view_purchase_order(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('purchase.order', self.purchase_id.id, 'Purchase Order')

    def action_view_inspection(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('grn.inspection', self.grn_inspection_id.id, 'Inspection')

    def action_view_gate_pass(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('gate.pass', self.gate_pass_id.id, 'Gate Pass')

    def action_view_weighbridge(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('weighbridge.ticket', self.weighbridge_id.id, 'Weighbridge')

    def action_view_sales_contract(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('rice.sales.contract', self.rice_sales_contract_id.id, 'Sales Contract')

    def unlink(self) -> bool:
        # H1: absolute protection - a GRN that produced Payment Certificates
        # is part of the financial chain and can never be deleted (the
        # certificates and any bills behind them would be orphaned). Runs
        # even under the bypass context: only removing the certificates
        # first can ever free the GRN.
        for picking in self:
            if picking.payment_certificate_ids:
                raise UserError(_(
                    "You cannot delete GRN %s: Payment Certificate(s) %s were "
                    "issued against it. Cancel or delete the certificates first.",
                    picking.name,
                    ", ".join(picking.payment_certificate_ids.mapped('name')),
                ))

        # Phase 3 Fix 4: Intercept native deletion to protect PO integrity
        # Allow deletion if explicitly bypassed by our custom action_delete_grn method
        if not self.env.context.get('bypass_grn_delete_check'):
            for picking in self:
                if picking.state == 'done' and picking.picking_type_code == PICKING_INCOMING and picking.grn_inspection_id:
                    raise UserError(_(
                        "You cannot delete a validated GRN directly using the Action menu. "
                        "Please use the 'Delete GRN' button on the picking to properly reverse stock and restore TLS."
                    ))

        for picking in self:
            if picking.state == 'done':
                picking.move_line_ids.write({'state': 'draft'})
                picking.move_ids.write({'state': 'draft'})
                picking.state = 'draft'
        return super().unlink()

    def button_validate(self) -> Dict[str, Any]:
        # RICE-FLOW GATE: the auto-created receipt of a rice PO must not be
        # validated until the Weighbridge confirms and takes it over (or the
        # third-party inspection direct flow does). Fires regardless of how
        # the user reaches the picking (Receipts menu, direct URL, list
        # multi-validate, RPC).
        for picking in self:
            if picking.is_pending_rice_receipt:
                raise UserError(_(
                    "This receipt belongs to Purchase Order %s and cannot be validated "
                    "yet. The GRN can only be validated after the Weighbridge is "
                    "confirmed (Confirm & View GRN on the Weighbridge ticket).",
                    picking.purchase_id.name or '',
                ))

        # FIX: Gate Pass enforcement is scoped to SALES Delivery Orders (picking has a Sale Order).
        # Both local and export sales DOs carry sale_id, and in both flows the Gate Pass is
        # Marked as Exited before validation - so the enforcement is preserved for them.
        # Purchase returns and the Delete-GRN reversal return have no Sale Order and no Gate
        # Pass: they must validate freely (this check previously blocked them).
        for picking in self:
            is_local_sales_delivery = (
                picking.picking_type_code == PICKING_OUTGOING
                and picking.sale_id
                and picking.state not in ('done', 'cancel')
            )
            if is_local_sales_delivery:
                if not picking.gate_pass_id or picking.gate_pass_id.state != 'done':
                    raise UserError(_(
                        "You cannot validate this Delivery Order yet. "
                        "Please ensure an Outbound Gate Pass has been created and Marked as Exited for this specific delivery."
                    ))

        # Phase 2 Fix: Let Odoo handle Lot/SN wizard natively.
        # We only safely auto-process Immediate Transfers and Backorders.
        res = super().button_validate()

        # FIX: Auto-process Immediate Transfer wizard to force stock update instantly
        if isinstance(res, dict) and res.get('res_model') == 'stock.immediate.transfer':
            wiz = self.env['stock.immediate.transfer'].with_context(res.get('context', {})).create({})
            res = wiz.process()

        # FIX: Auto-process Backorder Confirmation wizard
        if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
            wiz = self.env['stock.backorder.confirmation'].with_context(res.get('context', {})).create({})
            res = wiz.process()

        for picking in self:
            # Phase 4 Fix: ORM cache might not be updated after wizard processing. Force a re-read.
            if self.env['stock.picking'].browse(picking.id).state != 'done':
                continue

            # 1. Standard Incoming GRN: Deduct TLS from PO Line
            if picking.picking_type_code == PICKING_INCOMING and picking.grn_inspection_id:
                inspection = picking.grn_inspection_id

                tls_map: Dict[int, float] = {}
                for insp_line in inspection.inspection_line_ids:
                    if insp_line.purchase_order_line_id and insp_line.grn_insp_tls > 0:
                        tls_map[insp_line.purchase_order_line_id.id] = tls_map.get(insp_line.purchase_order_line_id.id,
                                                                                   0.0) + insp_line.grn_insp_tls

                for po_line_id, tls_used in tls_map.items():
                    po_line = self.env['purchase.order.line'].browse(po_line_id)
                    if po_line.exists():
                        po_line.available_tls = max(0.0, po_line.available_tls - tls_used)

            # 2. Supplier Return (Outgoing, no sale): Restore TLS to PO Line
            elif picking.picking_type_code == PICKING_OUTGOING:
                self._restore_tls_on_return(picking)

            # 3. Purchase Indent receipts: the indent flow has no
            # weighbridge - the received quantity IS the net weight (and
            # the primary product the first received move), so the Payment
            # Certificate's rate x net weight computes correctly.
            if (picking.picking_type_code == PICKING_INCOMING
                    and picking.purchase_indent_id):
                picking.net_weight = sum(picking.move_ids.mapped('quantity'))
                first_received = picking.move_ids.filtered(lambda move: move.quantity > 0)[:1]
                if first_received:
                    picking.product_id = first_received.product_id.id

        return res

    def _restore_tls_on_return(self, picking: 'stock.picking') -> None:
        """Protocol 2.1 (SRP): Handles restoring TLS when a GRN is returned."""
        for move in picking.move_ids:
            original_move = move.origin_returned_move_id

            # Ensure this move is actually a return of an original GRN move
            if original_move and original_move.picking_id.grn_inspection_id:
                original_inspection = original_move.picking_id.grn_inspection_id
                po_line = original_move.purchase_line_id

                if not po_line:
                    continue

                # Find the exact inspection line for this PO Line
                insp_line = original_inspection.inspection_line_ids.filtered(
                    lambda l: l.purchase_order_line_id.id == po_line.id
                )[:1]

                if insp_line and insp_line.grn_insp_tls > 0 and original_move.quantity > 0:
                    # Calculate proportional TLS to return (supports partial returns)
                    return_ratio = move.quantity / original_move.quantity
                    tls_to_restore = insp_line.grn_insp_tls * return_ratio

                    # Add TLS back to the Purchase Order Line
                    po_line.available_tls += tls_to_restore

    # ==========================================================
    # DELETE GRN SUPPORT (C2: honest pre-flight + exact lots)
    # ==========================================================

    def _get_reversible_moves(self) -> 'stock.move':
        """Protocol 4.1 (DRY): the moves that actually received stock and
        therefore need reversing (done moves with a positive quantity)."""
        self.ensure_one()
        return self.move_ids.filtered(lambda move: move.state == 'done' and move.quantity > 0)

    def _check_grn_reversal_lot_feasibility(self) -> None:
        """C2 pre-flight: every tracked product's received quantity must
        carry lot/serial information - the reversal re-creates those exact
        lots. Raises BEFORE any reversal work exists, so the error stays
        honest (the old version failed mid-savepoint and pointed users at
        a return picking the rollback had just erased)."""
        self.ensure_one()
        for move in self._get_reversible_moves():
            if move.product_id.tracking == 'none':
                continue
            lines_without_lot = move.move_line_ids.filtered(lambda line: not line.lot_id)
            if not move.move_line_ids or lines_without_lot:
                raise UserError(_(
                    "GRN %s cannot be reversed automatically: product %s was "
                    "received without Lot/Serial information. Create a manual "
                    "stock return for this GRN instead.",
                    self.name, move.product_id.display_name))

    def _set_reversal_move_lines(self) -> None:
        """C2 lot propagation: give every return move its done quantity
        using the EXACT lots and quantities the original GRN received (one
        move line per lot). Non-tracked products get a single full-quantity
        line. Explicit lines replace reservation: reservation would GUESS
        lots - the reversal must return what actually came in."""
        self.ensure_one()
        move_line_vals: List[Dict[str, Any]] = []
        for return_move in self.move_ids:
            source_move = return_move.origin_returned_move_id
            if return_move.product_id.tracking != 'none' and source_move:
                for source_line in source_move.move_line_ids:
                    move_line_vals.append({
                        'move_id': return_move.id,
                        'picking_id': return_move.picking_id.id,
                        'product_id': return_move.product_id.id,
                        'product_uom_id': return_move.product_id.uom_id.id,
                        'quantity': source_line.quantity,
                        'lot_id': source_line.lot_id.id,
                        # Reverse the original line's locations exactly.
                        'location_id': source_line.location_dest_id.id,
                        'location_dest_id': source_line.location_id.id,
                    })
            else:
                move_line_vals.append({
                    'move_id': return_move.id,
                    'picking_id': return_move.picking_id.id,
                    'product_id': return_move.product_id.id,
                    'product_uom_id': return_move.product_id.uom_id.id,
                    'quantity': return_move.product_uom_qty,
                    'location_id': return_move.location_id.id,
                    'location_dest_id': return_move.location_dest_id.id,
                })
        if move_line_vals:
            self.env['stock.move.line'].create(move_line_vals)
        for return_move in self.move_ids:
            return_move.picked = True

    def action_delete_grn(self) -> Dict[str, Any]:
        """Protocol 2.1: Mimics a full return (restoring TLS and stock), hard
        deletes the GRN, and redirects to receipts.

        C2 rework: lot/serial feasibility is checked BEFORE anything is
        created, and tracked products reverse the exact lots received."""
        self.ensure_one()
        picking = self

        if picking.state != 'done' or picking.picking_type_code != PICKING_INCOMING:
            return {'type': 'ir.actions.act_window_close'}

        # H1: fail fast, before any reversal work - a GRN with Payment
        # Certificates is part of the financial chain and cannot be deleted.
        if picking.payment_certificate_ids:
            raise UserError(_(
                "You cannot delete GRN %s: Payment Certificate(s) %s were "
                "issued against it. Cancel or delete the certificates first.",
                picking.name,
                ", ".join(picking.payment_certificate_ids.mapped('name')),
            ))

        # C2 pre-flight: honest failure before any work exists.
        picking._check_grn_reversal_lot_feasibility()

        po_id = picking.purchase_id.id

        # Phase 4 Fix: Wrap in savepoint for atomic transaction safety
        with self.env.cr.savepoint():
            # 1. Restore TLS on Purchase Order Lines (Qty received is handled natively by Odoo via origin_returned_move_id)
            if picking.grn_inspection_id:
                for insp_line in picking.grn_inspection_id.inspection_line_ids:
                    po_line = insp_line.purchase_order_line_id
                    if po_line:
                        if insp_line.grn_insp_tls > 0:
                            po_line.available_tls += insp_line.grn_insp_tls
                            insp_line.write({'grn_insp_tls': 0.0})

            # 2. Generate the Return Picking that reverses the physical stock
            # H4: prefer the picking type's own return type over an
            # arbitrary search hit.
            return_picking_type = picking.picking_type_id.return_picking_type_id \
                or self.env['stock.picking.type'].search(
                    [('code', '=', PICKING_OUTGOING), ('company_id', '=', picking.company_id.id)], limit=1)
            if not return_picking_type:
                raise UserError(_("Please configure an outgoing operation type for returns."))

            return_picking = self.env['stock.picking'].create({
                'partner_id': picking.partner_id.id,
                'picking_type_id': return_picking_type.id,
                'origin': f"Deletion Return: {picking.name}",
                'location_id': picking.location_dest_id.id,
                'location_dest_id': picking.location_id.id,
            })

            return_move_vals = []
            for move in picking._get_reversible_moves():
                return_move_vals.append({
                    'picking_id': return_picking.id,
                    'product_id': move.product_id.id,
                    'product_uom': move.product_uom.id,
                    'product_uom_qty': move.quantity,
                    'location_id': picking.location_dest_id.id,
                    'location_dest_id': picking.location_id.id,
                    'origin_returned_move_id': move.id,  # Native Odoo link for returns
                })
            self.env['stock.move'].create(return_move_vals)
            return_picking.action_confirm()

            # 3. Done quantities + the EXACT lots the GRN received.
            return_picking._set_reversal_move_lines()

            validate_res = return_picking.button_validate()
            if isinstance(validate_res, dict) and validate_res.get('res_model') == 'stock.immediate.transfer':
                wiz = self.env['stock.immediate.transfer'].with_context(validate_res.get('context', {})).create({})
                wiz.process()
            if isinstance(validate_res, dict) and validate_res.get('res_model') == 'stock.backorder.confirmation':
                wiz = self.env['stock.backorder.confirmation'].with_context(validate_res.get('context', {})).create({})
                wiz.process()

            # 4. Break the link so the original picking can be safely deleted
            return_picking.move_ids.write({'origin_returned_move_id': False})

            # 5. Hard Delete the Original GRN (Phase 3 Fix: pass bypass context)
            picking.with_context(bypass_grn_delete_check=True).unlink()

        # 6. Redirect to the list of receipts for the PO (Outside savepoint so it returns even if rolled back)
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_incoming')
        action['domain'] = [('purchase_id', '=', po_id)]
        action['name'] = _('Receipts')

        return action