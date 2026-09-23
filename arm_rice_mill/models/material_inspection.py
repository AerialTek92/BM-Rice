# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CREATE_NEW: int = 0

PICKING_INCOMING: str = 'incoming'


class MaterialInspection(models.Model):
    _name = 'material.inspection'
    _description = 'Material Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Insp. No.', index=True, readonly=True, copy=False,
                       default=lambda self: _('New'))
    date = fields.Date(string='Date', default=fields.Date.today(), required=True)

    supplier_id = fields.Many2one(
        'res.partner', string='Supplier',
        domain=[('partner_assign_type', '=', 'vendor')])

    purchase_order_id = fields.Many2one(
        'purchase.order', string='PO No.',
        domain="[('purchase_indent_id', '!=', False), ('state', 'in', ('purchase', 'done'))]",
        required=True)
    po_date = fields.Datetime(related='purchase_order_id.date_order', string='PO Date',
                              store=True, readonly=True)

    dc_ref_no = fields.Char(string='D.C Ref No')
    ref_no = fields.Char(string='Ref No')
    department = fields.Char(string='Department')

    inspection_line_ids = fields.One2many('material.inspection.line', 'inspection_id', string='Inspection Items')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # GRN receipts generated from this inspection
    grn_picking_ids = fields.One2many('stock.picking', 'material_inspection_id', string='GRNs')
    grn_count = fields.Integer(string='GRNs', compute='_compute_grn_count')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'MaterialInspection':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('material.inspection') or _('New')
        return super().create(vals_list)

    def _compute_grn_count(self) -> None:
        counts = self._get_related_record_count_batch('stock.picking', 'material_inspection_id')
        for rec in self:
            rec.grn_count = counts.get(rec.id, 0)

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self) -> None:
        """PO selected: map supplier + department and prefill the item lines
        from the PO lines (Accepted defaults to True)."""
        if not self.purchase_order_id:
            self.supplier_id = False
            self.inspection_line_ids = [(5, 0, 0)]
            return

        po = self.purchase_order_id
        self.supplier_id = po.partner_id.id
        self.department = po.purchase_indent_id.department or False

        line_vals = [(5, 0, 0)]
        for po_line in po.order_line.filtered(lambda l: l.product_id):
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'product_id': po_line.product_id.id,
                'description': po_line.name or po_line.product_id.display_name,
                'product_qty': po_line.product_qty,
                'accepted': True,
            }))
        self.inspection_line_ids = line_vals

    def action_confirm(self) -> None:
        for rec in self:
            if not rec.inspection_line_ids:
                raise UserError(_("Please add at least one item before confirming the Material Inspection."))
            rec.state = 'confirmed'

    def action_create_grn(self) -> Dict[str, Any]:
        """Inspection -> GRN: build the incoming receipt for the PO with the
        ACCEPTED lines only (done quantities preset), linked to this
        inspection. The user validates it - validation sets net weight via
        the existing indent-receipt logic."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Please confirm the Material Inspection before creating the GRN."))

        accepted_lines = self.inspection_line_ids.filtered(lambda l: l.accepted and l.product_qty > 0)
        if not accepted_lines:
            raise UserError(_("Mark at least one line as Accepted before creating the GRN."))

        po = self.purchase_order_id
        picking_type = po.picking_type_id or self.env['stock.picking.type'].search(
            [('code', '=', PICKING_INCOMING), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an incoming operation type."))

        picking = self.env['stock.picking'].create({
            'partner_id': po.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': f"{po.name} / {self.name}",
            'purchase_id': po.id,
            'material_inspection_id': self.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
        })

        for line in accepted_lines:
            po_line = po.order_line.filtered(lambda l: l.product_id == line.product_id)[:1]
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'picking_type_id': picking_type.id,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.product_qty,
                'quantity': line.product_qty,
                'picked': True,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'purchase_line_id': po_line.id if po_line else False,
                'origin': picking.origin,
            })

        picking.action_confirm()
        picking.action_assign()
        return self._open_form_view('stock.picking', picking.id, 'GRN')

    def action_view_grns(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('stock.picking', 'material_inspection_id', 'GRNs')

    def action_mark_done(self) -> None:
        for rec in self: rec.state = 'done'

    def action_cancel(self) -> None:
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'


class MaterialInspectionLine(models.Model):
    _name = 'material.inspection.line'
    _description = 'Material Inspection Line'

    inspection_id = fields.Many2one('material.inspection', string='Inspection', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item', required=True)
    item_code = fields.Char(string='Item Code', related='product_id.default_code', store=True, readonly=True)
    description = fields.Char(string='Item Description')
    uom_id = fields.Many2one('uom.uom', string='Unit',
                             related='product_id.uom_id', store=True, readonly=True)
    product_qty = fields.Float(string='Quantity', required=True, default=1.0)
    accepted = fields.Boolean(string='Accepted', default=True)