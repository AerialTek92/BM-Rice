# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple
from datetime import timedelta

KG_PER_TRUCK = 30000.0
KG_PER_BAG = 100.0
DELIVERY_FROM_OFFSET_DAYS = 1
DELIVERY_TO_OFFSET_DAYS = 8
DEFAULT_MOISTURE_PERCENT = 15.0
DEFAULT_BROKEN_PERCENT = 20.0
COMMAND_CREATE_NEW: int = 0


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'smart.button.mixin']

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Rice Sales Contract')
    contract_type = fields.Selection(
        related='rice_sales_contract_id.contract_type',
        string='Contract Type',
        readonly=True,
        store=True
    )
    broker_id = fields.Many2one('res.partner', string='Broker')
    buyer_id = fields.Many2one('hr.employee', string='Buyer')

    # NEW: Reference PO No. for old system references
    ref_po_no = fields.Char(string='Ref. PO No.')
    grn_inspection_ids = fields.One2many('grn.inspection', 'purchase_order_id', string='GRN Inspections')

    delivery_date_from = fields.Date(string='Date From')
    delivery_date_to = fields.Date(string='Due Date')
    product_id = fields.Many2one('product.product', string='Product', compute='_compute_product_id', store=True)
    grn_inspection_count = fields.Integer(string='Inspections', compute='_compute_grn_inspection_count')

    # Computed fields for the List View
    total_trucks = fields.Integer(string='Trucks', compute='_compute_po_totals', store=True)
    total_qty_ordered = fields.Float(string='Qty', compute='_compute_po_totals', store=True)
    total_qty_received = fields.Float(string='Received', compute='_compute_po_totals', store=True)
    unit_price = fields.Float(string='Rate', compute='_compute_po_totals', store=True)
    total_qty_remaining = fields.Float(string='Remaining Qty', compute='_compute_po_totals', store=True)

    total_available_tls = fields.Float(string='Avail. TLS', compute='_compute_po_totals', store=True)

    # REMOVED dummy _compute_can_edit_rfq. The approval_matrix mixin handles it automatically.

    remarks = fields.Html(string='Remarks')

    po_original_tls = fields.Float(
        string="PO. TLS",
        compute="_compute_tls_values",
        store=False,
    )

    po_total_tls = fields.Float(
        string="Recv. TLS",
        compute="_compute_tls_values",
        store=False,
    )

    po_remaining_tls = fields.Float(
        string="Rem. TLS",
        compute="_compute_tls_values",
        store=False,
    )

    @api.depends('order_line.no_of_trucks', 'order_line.available_tls')
    def _compute_tls_values(self):
        for order in self:
            # Calculate Original TLS directly from the PO lines
            order.po_original_tls = sum(line.no_of_trucks for line in order.order_line)
            received_tls = sum((line.no_of_trucks - line.available_tls) for line in order.order_line)

            if received_tls < 0:
                received_tls = 0

            order.po_total_tls = received_tls

            remaining = order.po_original_tls - order.po_total_tls
            if remaining < 0:
                remaining = 0
            order.po_remaining_tls = remaining

    is_third_party_po = fields.Boolean(
        string='Third Party / Outsider',
        compute='_compute_is_third_party_po',
        store=True, )

    @api.depends('grn_inspection_ids.is_third_party')
    def _compute_is_third_party_po(self) -> None:
        for order in self:
            order.is_third_party_po = any(order.grn_inspection_ids.mapped('is_third_party'))

    state_display = fields.Char(string='Status', compute='_compute_state_display', store=False)

    def _compute_grn_inspection_count(self) -> None:
        counts = self._get_related_record_count_batch('grn.inspection', 'purchase_order_id')
        for rec in self:
            rec.grn_inspection_count = counts.get(rec.id, 0)

    @api.depends('order_line.product_id')
    def _compute_product_id(self) -> None:
        for order in self:
            order.product_id = order.order_line[:1].product_id

    @api.depends('order_line.product_qty', 'order_line.qty_received', 'order_line.price_unit',
                 'order_line.no_of_trucks', 'order_line.available_tls')
    def _compute_po_totals(self) -> None:
        for order in self:
            order.total_trucks = sum(line.no_of_trucks for line in order.order_line)
            order.total_qty_ordered = sum(line.product_qty for line in order.order_line)
            order.total_qty_received = sum(line.qty_received for line in order.order_line)
            order.total_qty_remaining = order.total_qty_ordered - order.total_qty_received
            order.total_available_tls = sum(line.available_tls for line in order.order_line)
            first_line = order.order_line[:1]
            order.unit_price = first_line.price_unit if first_line else 0.0

    @api.depends('state', 'po_original_tls', 'po_remaining_tls')
    def _compute_state_display(self) -> None:
        state_labels = dict(self._fields['state']._description_selection(self.env))
        for order in self:
            # Show GRN status only for purchased/done orders with TLS
            if order.state in ('purchase', 'done') and order.po_original_tls > 0:
                remaining = order.po_remaining_tls
                total = order.po_original_tls

                if remaining <= 0:
                    order.state_display = 'GRN Completed + PO Completed'
                elif remaining < total:
                    order.state_display = 'GRN Coming'
                else:
                    order.state_display = 'Purchase Order'
            elif order.state in ('draft', 'sent'):
                order.state_display = state_labels.get(order.state, '')
            elif order.state == 'cancel':
                order.state_display = 'Cancelled'
            else:
                order.state_display = state_labels.get(order.state, '')

    @api.depends('name', 'order_line.product_id', 'order_line.price_unit')
    def _compute_display_name(self):
        if self.env.context.get('show_po_product_and_price'):
            for order in self:
                line = order.order_line[:1]
                if line and line.product_id:
                    order.display_name = f"{order.name} | {line.product_id.name} | {line.price_unit}"
                else:
                    order.display_name = order.name or _('Draft')
        else:
            super()._compute_display_name()

    @api.onchange('date_order')
    def _onchange_date_order_set_delivery_dates(self) -> None:
        if self.date_order:
            order_date = self.date_order.date()
            self.delivery_date_from = order_date + timedelta(days=DELIVERY_FROM_OFFSET_DAYS)
            self.delivery_date_to = self.delivery_date_from + timedelta(days=DELIVERY_TO_OFFSET_DAYS)
        else:
            self.delivery_date_from = False
            self.delivery_date_to = False

    def _prepare_inspection_line_vals(self) -> List[Tuple[int, int, Dict[str, Any]]]:
        self.ensure_one()
        line_vals: List[Tuple[int, int, Dict[str, Any]]] = []

        valid_lines = self.order_line.filtered(
            lambda l: l.product_id and l.product_qty > 0
        )

        if not valid_lines:
            raise UserError(_("No valid product lines found for GRN inspection."))

        for line in valid_lines:
            # Phase 5 Fix: Decouple GRN qty from native qty_received.
            # Calculate base quantity per truck (TLS) to prevent negative over-receipts.
            base_qty = (line.product_qty / line.no_of_trucks) if line.no_of_trucks else line.product_qty

            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'purchase_order_id': line.order_id.id,
                'purchase_order_line_id': line.id,
                'product_id': line.product_id.id,
                'base_qty_received': base_qty,
                'total_qty_remaining': base_qty,  # Default to 1 TLS initially
                'crop': line.crop_year.id if line.crop_year else False,
                'bags': line.no_of_bags or 0,
                'po_tls': line.available_tls or 0.0,
                'unit_price': line.price_unit or 0.0,
            }))
        return line_vals

    def action_create_grn_inspection(self) -> Dict[str, Any]:
        self.ensure_one()

        product_lines = self.order_line.filtered(lambda l: l.product_id)
        if not product_lines:
            raise UserError(_("Please add at least one product line before creating a GRN Inspection."))

        first_po_line = product_lines[:1]

        inspection_remarks = f"<b>GRN inspection Remarks:</b><br/>"
        if self.remarks:
            inspection_remarks = f"{self.remarks}<br/><br/>{inspection_remarks}"

        inspection = self.env['grn.inspection'].create({
            'purchase_order_id': self.id,
            'partner_id': self.partner_id.id,
            'ref_po_no': self.ref_po_no,
            'inspection_line_ids': self._prepare_inspection_line_vals(),
            'moisture_percent': first_po_line.moisture_percent if first_po_line else DEFAULT_MOISTURE_PERCENT,
            'broken_percent': first_po_line.broken_percent if first_po_line else DEFAULT_BROKEN_PERCENT,
            'remarks': inspection_remarks,
        })
        return self._open_form_view('grn.inspection', inspection.id, 'GRN Inspection')

    def action_view_grn_inspections(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('grn.inspection', 'purchase_order_id', 'GRN Inspection')

    def action_view_picking(self) -> Dict[str, Any]:
        """Receipts smart button: open with the rice receipts list so the
        purchase-flow columns (Trucks, Vehicle No., TLS values) are visible.

        The smart button builds its own action around the generic Transfers
        action with a PO domain - the act_window view attachment on the
        Receipts menu action never reaches it - so the list mode is pointed
        at the receipts view here, at the moment the button is clicked."""
        result = super().action_view_picking()

        # Only restyle the multi-record list result. Native behavior is kept for:
        # - single receipt: opens the form directly (res_id is set)
        # - no receipts: closes or opens an empty list (nothing to restyle)
        is_receipts_list = (
            result.get('res_model') == 'stock.picking' and not result.get('res_id')
        )
        if is_receipts_list:
            receipts_list_view = self.env.ref('arm_rice_mill.view_picking_tree_rice_receipts')
            picking_form_view = self.env.ref('stock.view_picking_form')
            result['views'] = [
                (receipts_list_view.id, 'list'),
                (picking_form_view.id, 'form'),
            ]
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    rice_contract_line_id = fields.Many2one(
        'rice.sales.contract.line',
        string='Contract Line Ref',
        ondelete='restrict'  # ← ADDED: Prevent orphaned records
    )
    no_of_trucks = fields.Integer(string='No of Trucks')
    no_of_bags = fields.Float(string='No of Bags', compute='_compute_no_of_bags', store=True, readonly=False)
    crop_year = fields.Many2one('master.crop.year', string='Crop')
    broken_percent = fields.Float(string='Broken %', default=DEFAULT_BROKEN_PERCENT)
    moisture_percent = fields.Float(string='Moisture %', default=DEFAULT_MOISTURE_PERCENT)
    transaction_type = fields.Selection([('cash', 'Cash'), ('credit', 'Credit')], string='Soda Type', default='cash')
    credit_days = fields.Integer(string='Credit Days')
    available_tls = fields.Float(string='Available TLS')

    @api.depends('product_qty')
    def _compute_no_of_bags(self) -> None:
        for line in self:
            if line.product_qty and line.product_qty > 0:
                line.no_of_bags = line.product_qty / KG_PER_BAG
            else:
                line.no_of_bags = 0.0

    @api.onchange('no_of_trucks')
    def _onchange_no_of_trucks(self) -> None:
        if self.no_of_trucks > 0:
            self.product_qty = self.no_of_trucks * KG_PER_TRUCK
            self.available_tls = self.no_of_trucks