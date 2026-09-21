# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CREATE_NEW: int = 0


class PurchaseIndent(models.Model):
    _name = 'purchase.indent'
    _description = 'Purchase Indent'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Indent No.', index=True, readonly=True, copy=False,
                       default=lambda self: _('New'))
    indent_date = fields.Date(string='Date', default=fields.Date.today(), required=True)
    payment_mode = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
        ('bank_transfer', 'Bank Transfer'),
    ], string='Payment Mode', default='cash', tracking=True)
    department = fields.Char(string='Department')

    # WHERE the indented items are needed (informational: the receipt's
    # destination is governed by the PO's picking type).
    location_id = fields.Many2one(
        'stock.location', string='Location',
        domain=[('usage', '=', 'internal')],
    )

    # The vendor the indent is placed with - becomes the PO's vendor.
    # Vendor OR Broker, matching the Purchase Order's own vendor domain.
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor',
        domain=[('partner_assign_type', '=', 'vendor')],
        context={'res_partner_search_mode': 'supplier'},
    )

    indent_line_ids = fields.One2many('purchase.indent.line', 'indent_id', string='Indent Items')

    material_issue_note_ids = fields.One2many('material.issue.note', 'purchase_indent_id', string='Material Issue Notes')
    material_issue_note_count = fields.Integer(string='Issue Notes', compute='_compute_material_issue_note_count')

    # Footer
    remarks = fields.Text(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    purchase_order_ids = fields.One2many('purchase.order', 'purchase_indent_id', string='Purchase Orders')
    purchase_order_count = fields.Integer(string='Purchase Orders', compute='_compute_purchase_order_count')

    # Header display: total of the lines' Net Amounts
    total_net_amount = fields.Float(
        string='Total Net Amount', compute='_compute_total_net_amount', store=True)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'PurchaseIndent':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('purchase.indent') or _('New')
        return super().create(vals_list)

    def _compute_purchase_order_count(self) -> None:
        counts = self._get_related_record_count_batch('purchase.order', 'purchase_indent_id')
        for rec in self:
            rec.purchase_order_count = counts.get(rec.id, 0)

    @api.depends('indent_line_ids.net_amount')
    def _compute_total_net_amount(self) -> None:
        for rec in self:
            rec.total_net_amount = sum(rec.indent_line_ids.mapped('net_amount'))

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.indent_line_ids:
                raise UserError(_("Please add at least one item before confirming the Purchase Indent."))
            rec.state = 'confirmed'

    def action_create_purchase_order(self) -> Dict[str, Any]:
        """PI -> PO: create a draft Purchase Order carrying the indent items
        (qty + rate) under the indent's Vendor. The PO then follows the
        DIRECT flow (GRN receipt -> Payment Certificate) - no QC, Gate Pass
        or Weighbridge steps."""
        self.ensure_one()
        if self.state not in ('confirmed', 'done'):
            raise UserError(_("Please confirm the Purchase Indent before creating a Purchase Order."))
        if not self.vendor_id:
            raise UserError(_("Please set the Vendor on the indent before creating a Purchase Order."))

        valid_lines = self.indent_line_ids.filtered(lambda l: l.product_id and l.product_qty > 0)
        if not valid_lines:
            raise UserError(_("The indent has no valid item lines to order."))

        order_lines = [(COMMAND_CREATE_NEW, 0, {
            'product_id': line.product_id.id,
            'name': line.description or line.product_id.display_name or line.product_id.name,
            'product_qty': line.product_qty,
            'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
            'price_unit': line.rate or 0.0,
        }) for line in valid_lines]

        order_vals: Dict[str, Any] = {
            'partner_id': self.vendor_id.id,
            'purchase_indent_id': self.id,
            'origin': self.name,
            'date_order': fields.Datetime.now(),
            'order_line': order_lines,
        }

        # Payment mode + location context carried onto the PO for reference.
        po_remarks = f"<b>From Purchase Indent {self.name}</b>"
        if self.payment_mode:
            po_remarks += f" | Payment Mode: {dict(self._fields['payment_mode']._description_selection(self.env)).get(self.payment_mode, self.payment_mode)}"
        if self.department:
            po_remarks += f" | Department: {self.department}"
        if self.location_id:
            po_remarks += f" | Location: {self.location_id.display_name}"
        po_remarks += "<br/>"
        if self.remarks:
            po_remarks += f"{self.remarks}<br/>"
        order_vals['remarks'] = po_remarks

        order = self.env['purchase.order'].create(order_vals)
        return self._open_form_view('purchase.order', order.id, 'Purchase Order')

    def _compute_material_issue_note_count(self) -> None:
        counts = self._get_related_record_count_batch('material.issue.note', 'purchase_indent_id')
        for rec in self:
            rec.material_issue_note_count = counts.get(rec.id, 0)

    def action_create_material_issue_note(self) -> Dict[str, Any]:
        """PI -> MIN: the issue note carries the indent's items and
        department; the PO is then raised from the note."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Please confirm the Purchase Indent before creating a Material Issue Note."))

        note = self.env['material.issue.note'].create({
            'purchase_indent_id': self.id,
            'date': fields.Date.today(),
            'department': self.department,
            'remarks': self.remarks,
            'material_issue_line_ids': [(COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'description': line.description,
                'product_qty': line.product_qty,
            }) for line in self.indent_line_ids],
        })
        return self._open_form_view('material.issue.note', note.id, 'Material Issue Note')

    def action_view_material_issue_notes(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('material.issue.note', 'purchase_indent_id', 'Material Issue Notes')

    def action_view_purchase_orders(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('purchase.order', 'purchase_indent_id', 'Purchase Orders')

    def action_mark_done(self) -> None:
        for rec in self: rec.state = 'done'

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'


class PurchaseIndentLine(models.Model):
    _name = 'purchase.indent.line'
    _description = 'Purchase Indent Line'

    indent_id = fields.Many2one('purchase.indent', string='Indent', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain=[('is_purchase_indent', '=', True)],
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one('uom.uom', string='Unit',
                             related='product_id.uom_id', store=True, readonly=True)
    product_qty = fields.Float(string='Qty', required=True, default=1.0)
    rate = fields.Float(string='Rate')
    net_amount = fields.Float(
        string='Net Amount', compute='_compute_net_amount', store=True)

    @api.depends('product_qty', 'rate')
    def _compute_net_amount(self) -> None:
        """Net Amount = Qty x Rate (server truth after save)."""
        for line in self:
            line.net_amount = (line.product_qty or 0.0) * (line.rate or 0.0)