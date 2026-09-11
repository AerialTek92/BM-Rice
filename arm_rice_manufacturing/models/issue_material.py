# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Any, Dict, List, Optional, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

MANUFACTURING_OPERATION_CODE: str = 'mrp_operation'


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

    # Legacy link: kept for records created before the MRP bridge (internal
    # transfers are no longer created by this module).
    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)

    # NEW: the native Manufacturing Order consuming the raw rice.
    mrp_production_id = fields.Many2one('mrp.production', string='Manufacturing Order', readonly=True, copy=False)

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

    # ==========================================================
    # MRP BRIDGE: ISSUE = CREATE THE MANUFACTURING ORDER
    # ==========================================================

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a Draft Issue Material can be confirmed. Current state: %s.", rec.state))
            if not rec.issue_line_ids:
                raise UserError(_("Please add raw materials before confirming."))
            if not rec.source_location_ids or not rec.dest_location_ids:
                raise UserError(_("Please select both Source and Destination locations before issuing."))
            if any(line.qty_mt <= 0 for line in rec.issue_line_ids):
                raise UserError(_("Every raw rice line needs a quantity greater than zero before issuing."))
            if any(not line.shell_id for line in rec.issue_line_ids):
                raise UserError(_("Every raw rice line needs a Source Location before issuing."))

            with self.env.cr.savepoint():
                rec._create_manufacturing_order()
                rec.state = 'confirmed'

                # Finding 2: the Job Order escalates when material is actually issued.
                if rec.job_order_id.state == 'confirmed':
                    rec.job_order_id.state = 'in_progress'

                linked_record = rec._link_to_production_record()
                if (linked_record and linked_record.state == 'done'
                        and linked_record.finished_material_weight > 0):
                    rec._complete_manufacturing_order(
                        linked_record.finished_material_weight,
                        linked_record.dest_location_id or rec.dest_location_ids[:1],
                    )
        return True

    def _create_manufacturing_order(self) -> None:
        """Protocol 2.1 (SRP): Create, confirm and reserve the native Manufacturing
        Order that will consume the raw rice and produce the process rice.
        No BoM is used: each job's components and quantities differ, so the
        components come straight from the issue lines."""
        self.ensure_one()

        finished_product = self.job_order_id.product_id
        if not finished_product:
            raise UserError(_(
                "The Job Order has no Process Rice product: cannot create a Manufacturing Order."))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', MANUFACTURING_OPERATION_CODE),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("Please configure a Manufacturing operation type for this company."))

        planned_qty = self.process_rice_qty or self.total_issue_qty
        if planned_qty <= 0:
            raise UserError(_("Cannot issue without a planned quantity: set Process Rice QTY or line quantities."))

        # NOTE: stock.move keeps the field name 'product_uom' in Odoo 19.
        raw_move_commands = [
            (COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.qty_mt,
                'location_id': line.shell_id.id,
            })
            for line in self.issue_line_ids
        ]

        production = self.env['mrp.production'].create({
            'origin': self.name,
            'product_id': finished_product.id,
            'product_qty': planned_qty,
            'product_uom_id': finished_product.uom_id.id,
            'picking_type_id': picking_type.id,
            'location_src_id': self.source_location_ids[:1].id,
            'location_dest_id': self.dest_location_ids[:1].id,
            'move_raw_ids': raw_move_commands,
        })
        production.action_confirm()
        production.action_assign()

        # Lot-tracked raw rice: carry the lot chosen on the issue line onto the
        # reserved move line so consumption stays traceable.
        for line in self.issue_line_ids:
            move = production.move_raw_ids.filtered(lambda m: m.product_id == line.product_id)[:1]
            if line.lot_id and move and move.move_line_ids:
                move.move_line_ids[:1].lot_id = line.lot_id

        self.mrp_production_id = production.id

    def _complete_manufacturing_order(self, finished_qty: float, dest_location: Optional['stock.location']) -> Any:
        """Protocol 2.1 (SRP): Finish the Manufacturing Order with the ACTUAL
        quantities: produces the finished rice into stock and consumes the raw
        rice. Planned qty is aligned to the actual so no backorder MO spawns."""
        self.ensure_one()
        production = self.mrp_production_id
        if not production or production.state in ('done', 'cancel'):
            return True

        if finished_qty <= 0:
            raise UserError(_(
                "The finished weight must be greater than zero to complete the Manufacturing Order."))

        if dest_location and production.location_dest_id != dest_location:
            production.write({'location_dest_id': dest_location.id})
            production.move_finished_ids.write({'location_dest_id': dest_location.id})

        production.product_qty = finished_qty
        production.qty_producing = finished_qty

        # Actual consumption = the issued quantities (one MO raw move per issue line).
        for move in production.move_raw_ids:
            issue_line = self.issue_line_ids.filtered(lambda line: line.product_id == move.product_id)[:1]
            if issue_line:
                move.quantity = issue_line.qty_mt

        return production.button_mark_done()

    def _link_to_production_record(self) -> Optional['production.record']:
        """Protocol 2.1 (SRP): Attach this issue to a Production Record that was
        completed without one (reverse flow). Returns the linked record."""
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
        return production or None

    def action_cancel(self) -> None:
        for rec in self:
            if rec.state not in ('draft', 'confirmed'):
                raise UserError(_("Only a Draft or Confirmed Issue Material can be cancelled. Current state: %s.", rec.state))
            if rec.mrp_production_id and rec.mrp_production_id.state == 'done':
                raise UserError(_(
                    "The Manufacturing Order for %(issue)s is already completed: raw rice has been "
                    "consumed and finished rice produced. Reverse it from the Manufacturing Order "
                    "instead of cancelling here.",
                    issue=rec.name,
                ))
            if rec.mrp_production_id and rec.mrp_production_id.state != 'cancel':
                rec.mrp_production_id.action_cancel()
            if rec.picking_id and rec.picking_id.state != 'cancel':
                rec.picking_id.action_cancel()
            rec.state = 'cancel'

    def unlink(self) -> bool:
        for rec in self:
            if rec.mrp_production_id and rec.mrp_production_id.state == 'done':
                raise UserError(_(
                    "You cannot delete Issue Material %(issue)s: its Manufacturing Order has already "
                    "consumed stock. Cancel it instead.",
                    issue=rec.name,
                ))
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_(
                    "You cannot delete an Issue Material that has a validated stock transfer. "
                    "Please cancel it instead."
                ))
        pickings = self.mapped('picking_id')
        open_productions = self.mapped('mrp_production_id').filtered(
            lambda production: production.state not in ('done', 'cancel'))
        res = super().unlink()
        draft_pickings = pickings.filtered(lambda p: p.state in ('draft', 'cancel'))
        if draft_pickings:
            draft_pickings.unlink()
        if open_productions:
            open_productions.action_cancel()
        return res

    def action_reset_to_draft(self) -> None:
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_("Only a Cancelled Issue Material can be reset to draft. Current state: %s.", rec.state))
            rec.state = 'draft'

    def action_view_picking(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('stock.picking', self.picking_id.id, 'Internal Transfer')

    def action_view_manufacturing_order(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('mrp.production', self.mrp_production_id.id, 'Manufacturing Order')

    def action_view_production_log_sheets(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.log.sheet', 'issue_material_id', 'Production Log Sheet')

    def action_view_production_qcs(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.quality.control', 'issue_material_id',
                                          'Production Quality Control')

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
                'default_brand_id': self.job_order_id.brand_id.id,
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
                'default_brand_id': self.job_order_id.brand_id.id,
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
    shell_id = fields.Many2one('stock.location', string='Src Location', domain="[('usage', '=', 'internal')]",
                               required=True)
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