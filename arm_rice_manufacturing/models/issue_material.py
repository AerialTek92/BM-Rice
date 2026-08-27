# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class IssueMaterial(models.Model):
    _name = 'issue.material'
    _description = 'Issue Material'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Issue No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    issue_date = fields.Date(string='Issue Date', default=fields.Date.today(), required=True)
    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True)
    raw_rice_ids = fields.Many2many(related='job_order_id.raw_rice_ids', string='Raw Rice', readonly=True)
    process_rice_qty = fields.Float(string='Process Rice QTY')
    milling_date = fields.Date(string='Milling Date', tracking=True)

    # FIX: Removed required=True and used unique column1/column2 names to avoid ORM collisions
    source_location_ids = fields.Many2many(
        'stock.location',
        'issue_material_source_loc_rel',
        'issue_material_src_id',
        'src_location_id',
        string='Source Locations',
        domain="[('usage', '=', 'internal')]"
    )
    dest_location_ids = fields.Many2many(
        'stock.location',
        'issue_material_dest_loc_rel',
        'issue_material_dest_id',
        'dest_location_id',
        string='Destination Locations',
        domain="[('usage', '=', 'internal')]"
    )

    total_issue_qty = fields.Float(string='Total Issue Qty (MT)', compute='_compute_total_issue_qty', store=True)
    total_issue_bags = fields.Float(string='Total Issue Bags', compute='_compute_total_issue_bags', store=True)

    issue_line_ids = fields.One2many('issue.material.line', 'issue_id', string='Raw Rice Details')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')], string='Status',
                             default='draft', tracking=True)

    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)
    rice_type = fields.Selection(related='job_order_id.rice_type', string='Rice Type', store=True, readonly=True)
    remarks = fields.Html(string='Remarks')

    log_sheet_count = fields.Integer(string='Log Sheets', compute='_compute_log_sheet_count')
    qc_count = fields.Integer(string='Quality Controls', compute='_compute_qc_count')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'IssueMaterial':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'issue.material.rework' if vals.get('is_reworking') else 'issue.material'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    def _compute_log_sheet_count(self) -> None:
        for rec in self:
            rec.log_sheet_count = rec._get_related_record_count('production.log.sheet', 'issue_material_id')

    def _compute_qc_count(self) -> None:
        for rec in self:
            rec.qc_count = rec._get_related_record_count('production.quality.control', 'issue_material_id')

    @api.depends('issue_line_ids.qty_mt')
    def _compute_total_issue_qty(self) -> None:
        for rec in self:
            rec.total_issue_qty = sum(rec.issue_line_ids.mapped('qty_mt'))

    @api.depends('issue_line_ids.bags')
    def _compute_total_issue_bags(self) -> None:
        for rec in self:
            rec.total_issue_bags = sum(rec.issue_line_ids.mapped('bags'))

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self):
        if not self.job_order_id:
            self.remarks = False
            return
        bjo = self.job_order_id
        im_remarks = ""
        if bjo.remarks:
            im_remarks = f"{bjo.remarks}<br/><br/><b>Issue Material Remarks:</b><br/>"
        else:
            im_remarks = "<b>Issue Material Remarks:</b><br/>"

        self.update({
            'process_rice_qty': bjo.process_rice_qty,
            'remarks': im_remarks,
        })

    @api.onchange('source_location_ids', 'job_order_id')
    def _onchange_source_location_ids_fetch_products(self) -> None:
        if not self.source_location_ids or not self.raw_rice_ids:
            self.issue_line_ids = [COMMAND_CLEAR_ALL]
            return

        quants = self.env['stock.quant'].search([
            ('location_id', 'child_of', self.source_location_ids.ids),
            ('quantity', '>', 0),
            ('product_id', 'in', self.raw_rice_ids.ids)
        ])

        if not quants:
            self.issue_line_ids = [COMMAND_CLEAR_ALL]
            return

        line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        unique_products = quants.mapped('product_id')

        for product in unique_products:
            first_quant = quants.filtered(lambda q: q.product_id == product)[:1]
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'product_id': product.id,
                'lot_id': first_quant.lot_id.id if first_quant.lot_id else False,
                'shell_id': first_quant.location_id.id if first_quant.location_id else False,
                'qty_mt': 0.0,
                'bags': 0,
            }))
        self.issue_line_ids = line_vals

    def action_confirm(self):
        for rec in self:
            if not rec.issue_line_ids:
                raise UserError(_("Please add raw materials before confirming."))
            if not rec.source_location_ids or not rec.dest_location_ids:
                raise UserError(_("Please select both Source and Destination locations before issuing."))

            with self.env.cr.savepoint():
                if rec.rice_type == 'basmati':
                    rec.state = 'confirmed'
                else:
                    res = rec._create_internal_transfer()
                    rec.state = 'confirmed'
                    rec._link_to_production_record()

            if rec.rice_type != 'basmati' and res:
                return res
        return True

    def _link_to_production_record(self) -> None:
        self.ensure_one()
        production = self.env['production.record'].search([
            ('job_order_id', '=', self.job_order_id.id),
            ('issue_material_id', '=', False),
            ('state', '=', 'done')
        ], limit=1, order='id desc')

        if production:
            production.write({
                'issue_material_id': self.id,
                'raw_material_weight': self.total_issue_qty,
            })

    def _create_internal_transfer(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an internal picking type."))

        header_location_id = self.source_location_ids[0].id if self.source_location_ids else (self.dest_location_ids[0].id if self.dest_location_ids else False)
        default_dest_id = self.dest_location_ids[0].id if self.dest_location_ids else False

        if not header_location_id or not default_dest_id:
            raise UserError(_("Please select Source and Destination locations."))

        picking = self.env['stock.picking'].create({
            'partner_id': self.job_order_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': self.name,
            'location_id': header_location_id,
            'location_dest_id': default_dest_id,
        })

        for line in self.issue_line_ids:
            if not line.shell_id:
                raise UserError(_("Please specify a Source Location for product: %s") % line.product_id.name)

            move_dest_id = line.dest_id.id if line.dest_id else default_dest_id

            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.qty_mt,
                'location_id': line.shell_id.id,
                'location_dest_id': move_dest_id,
            })

        picking.action_confirm()
        picking.action_assign()

        if picking.state != 'done':
            for move in picking.move_ids:
                move.write({'quantity': move.product_uom_qty, 'picked': True})

            needs_tracking = any(m.product_id.tracking != 'none' for m in picking.move_ids)
            if not needs_tracking:
                validate_res = picking.button_validate()
                if isinstance(validate_res, dict):
                    return validate_res
            else:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Internal Transfer',
                    'res_model': 'stock.picking',
                    'view_mode': 'form',
                    'res_id': picking.id,
                    'target': 'current',
                }

        self.picking_id = picking.id
        return True

    def action_cancel(self) -> None:
        for rec in self:
            if rec.picking_id and rec.picking_id.state != 'cancel':
                rec.picking_id.action_cancel()
            rec.state = 'cancel'

    def unlink(self) -> bool:
        for rec in self:
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_(
                    "You cannot delete an Issue Material that has a validated stock transfer. "
                    "Please cancel it instead."
                ))
        pickings = self.mapped('picking_id')
        res = super().unlink()
        draft_pickings = pickings.filtered(lambda p: p.state in ('draft', 'cancel'))
        if draft_pickings:
            draft_pickings.unlink()
        return res

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

    def action_view_picking(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('stock.picking', self.picking_id.id, 'Internal Transfer')

    def action_view_production_log_sheets(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.log.sheet', 'issue_material_id', 'Production Log Sheet')

    def action_view_production_qcs(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.quality.control', 'issue_material_id', 'Production Quality Control')

    def action_create_production_log_sheet(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Log Sheet',
            'res_model': 'production.log.sheet',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_issue_material_id': self.id,
                'default_job_order_1_id': self.job_order_id.id,
                'default_customer_1_id': self.job_order_id.partner_id.id,
            }
        }

    def action_create_production_qc(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Quality Control',
            'res_model': 'production.quality.control',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_issue_material_id': self.id,
                'default_job_order_id': self.job_order_id.id,
                'default_customer_id': self.job_order_id.partner_id.id,
            }
        }


class IssueMaterialLine(models.Model):
    _name = 'issue.material.line'
    _description = 'Issue Material Line'

    issue_id = fields.Many2one('issue.material', string='Issue', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Raw Rice', required=True)
    qty_mt = fields.Float(string='Qty (MT)')

    qty_on_hand = fields.Float(
        string='On Hand',
        compute='_compute_qty_on_hand',
        help="Available quantity in the selected Source Location."
    )

    bags = fields.Integer(string='Bags')

    lot_id = fields.Many2one('stock.lot', string='Lot No', domain="[('product_id', '=', product_id)]")
    shell_id = fields.Many2one('stock.location', string='Src Location', domain="[('usage', '=', 'internal')]", required=True)
    # FIX: Removed required=True to prevent database upgrade failures
    dest_id = fields.Many2one('stock.location', string='Dest Location', domain="[('usage','=', 'internal')]")

    @api.depends('product_id', 'shell_id')
    def _compute_qty_on_hand(self) -> None:
        for line in self:
            if line.product_id and line.shell_id:
                product = line.product_id.with_context(location=line.shell_id.id)
                line.qty_on_hand = product.qty_available
            else:
                line.qty_on_hand = 0.0

    @api.onchange('product_id')
    def _onchange_product_id_set_lot_shell(self):
        if self.product_id and self.issue_id.source_location_ids:
            quant = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', 'child_of', self.issue_id.source_location_ids.ids),
                ('quantity', '>', 0)
            ], limit=1, order='id asc')

            if quant:
                self.lot_id = quant.lot_id.id if quant.lot_id else False
                self.shell_id = quant.location_id.id
            else:
                self.lot_id = False
                self.shell_id = False
        else:
            self.lot_id = False
            self.shell_id = False