# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Any, Dict, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class ProductionRecord(models.Model):
    _name = 'production.record'
    _description = 'Rice Recovery'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Recovery No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    operator_name = fields.Char(string='Operator Name')
    shift = fields.Selection([('morning', 'Morning'), ('evening', 'Evening'), ('night', 'Night')], string='Shift')
    day = fields.Char(string='Day')

    # Date range, handled like production.planning's milling date range:
    # display field derived from From/To (single date shows once), validation
    # keeps From before To.
    production_date_from = fields.Date(string='Date From', default=fields.Date.today(), required=True)
    production_date_to = fields.Date(string='Date To')
    production_date = fields.Char(string='Production Date', compute='_compute_production_date', store=True)

    # Basmati: the single Process Rice. IRRI: hidden internal value.
    product_id = fields.Many2one('product.product', string='Process Rice')

    # View helper: drives per-rice-type visibility on this form.
    rice_type = fields.Selection(related='job_order_id.rice_type', string='Rice Type',
                                 store=True, readonly=True)

    job_order_id = fields.Many2one('brand.job.order', string='Job Order No.', required=True,
                                   context={'production_record_job_view': True})
    issue_material_id = fields.Many2one(
        'issue.material',
        string='Issue Material Ref',
        domain="[('job_order_id', '=', job_order_id), ('state', '=', 'confirmed')]"
    )
    process_rice_qty = fields.Float(string='Process Rice QTY')

    mrp_production_id = fields.Many2one(
        related='issue_material_id.mrp_production_id',
        string='Manufacturing Order',
        readonly=True,
    )

    source_location_ids = fields.Many2many(
        'stock.location',
        string='Source Locations',
        domain="[('usage', '=', 'internal')]"
    )
    dest_location_id = fields.Many2one('stock.location', string='Destination Location', required=True,
                                       domain="[('usage', '=', 'internal')]")

    finished_wb_ticket_id = fields.Many2one(
        'weighbridge.ticket',
        string='Finished W/B Ref',
        domain="['|', ('mfg_bjo_1_id', '=', job_order_id), ('mfg_bjo_2_id', '=', job_order_id), "
               "('is_finished_weighbridge', '=', True), ('state', '=', 'confirmed')]"
    )

    # --- Section: Weights & Yield ---
    # finished_material_weight = TOTAL process rice weight (all products) -
    # the recovery basis.
    raw_material_weight = fields.Float(string='Raw Material Weight')
    finished_material_weight = fields.Float(string='Finished Material Weight')

    # Internal machinery (hidden in the view): the weight produced through the
    # Manufacturing Order - Odoo's MO produces one product by framework design.
    # For IRRI this is the derived internal product's weighed weight; the other
    # products enter stock via the transfer with their own weights.
    primary_finished_weight = fields.Float(
        string='Mfg Output Weight',
        help="Internal: quantity produced through the Manufacturing Order.",
    )

    # Brand display from the Job Order (carried through like Process Rice).
    brand_id = fields.Many2one(related='job_order_id.brand_id', string='Brand', readonly=True)
    brand_ids = fields.Many2many(related='job_order_id.brand_ids', string='Brand', readonly=True)

    byproduct_weight = fields.Float(string='Bi-Product Weight (MT)', compute='_compute_byproduct_weight', store=True)
    recovery_pct = fields.Float(string='Recovery %', compute='_compute_recovery_pct', store=True, readonly=True)

    # --- Section: Bags & Quality ---
    finished_bags = fields.Integer(string='Finished Bags')
    empty_bag_weight = fields.Float(string='Empty Bag Weight (MT)')
    moisture = fields.Float(string='Moisture %')
    agl = fields.Float(string='AGL (MM)')

    byproduct_line_ids = fields.One2many('production.record.line', 'production_id', string='Bi-Products')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)
    remarks = fields.Html(string='Remarks')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionRecord':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.record.rework' if vals.get('is_reworking') else 'production.record'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals_list)

    # ==========================================
    # DATE RANGE (production.planning pattern)
    # ==========================================

    @api.depends('production_date_from', 'production_date_to')
    def _compute_production_date(self) -> None:
        """Display field: 'Sep 2' when both are the same date, otherwise
        'Sep 2 to Sep 5'. Mirrors the milling date range behavior."""
        for rec in self:
            date_from = rec.production_date_from
            date_to = rec.production_date_to
            if date_from and date_to:
                if date_from == date_to:
                    rec.production_date = date_from.strftime('%d %b %Y')
                else:
                    rec.production_date = f"{date_from.strftime('%d %b %Y')} to {date_to.strftime('%d %b %Y')}"
            elif date_from:
                rec.production_date = date_from.strftime('%d %b %Y')
            else:
                rec.production_date = False

    @api.constrains('production_date_from', 'production_date_to')
    def _check_production_date_range(self) -> None:
        for rec in self:
            if rec.production_date_from and rec.production_date_to:
                if rec.production_date_to < rec.production_date_from:
                    raise UserError(_(
                        "Date To (%(to)s) cannot be earlier than Date From (%(from)s).",
                        to=rec.production_date_to,
                        from_=rec.production_date_from,
                    ))

    @api.depends('byproduct_line_ids.qty')
    def _compute_byproduct_weight(self):
        for rec in self:
            rec.byproduct_weight = sum(rec.byproduct_line_ids.mapped('qty'))

    @api.depends('finished_material_weight', 'raw_material_weight')
    def _compute_recovery_pct(self):
        for rec in self:
            if rec.raw_material_weight > 0:
                rec.recovery_pct = (rec.finished_material_weight / rec.raw_material_weight) * 100
            else:
                rec.recovery_pct = 0.0

    @api.onchange('job_order_id')
    def _onchange_job_order_id(self):
        if not self.job_order_id:
            self.remarks = False
            self.moisture = 0.0
            self.agl = 0.0
            self.process_rice_qty = 0.0
            self.product_id = False
            self.byproduct_line_ids = [(5, 0, 0)]
            return

        bjo = self.job_order_id
        prd_remarks = ""
        if bjo.remarks:
            prd_remarks = f"{bjo.remarks}<br/><br/><b>Rice Recovery Remarks:</b><br/>"
        else:
            prd_remarks = "<b>Rice Recovery Remarks:</b><br/>"

        prs = bjo.process_rice_spec_id
        moisture_val = 0.0
        agl_val = 0.0
        if prs:
            moisture_val = prs.n_moisture_percent
            agl_val = prs.n_agl

        byproduct_vals = [(5, 0, 0)]
        log_sheets = self.env['production.log.sheet'].search([
            '|',
            ('job_order_1_id', '=', bjo.id),
            ('job_order_2_id', '=', bjo.id)
        ])

        for log_sheet in log_sheets:
            for line in log_sheet.byproduct_line_ids:
                byproduct_vals.append((0, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.weight,
                    'bags': line.bags,
                    'coverage_ratio': line.percent
                }))

        self.update({
            'remarks': prd_remarks,
            'moisture': moisture_val,
            'agl': agl_val,
            'product_id': bjo.product_id.id,
            'process_rice_qty': bjo.process_rice_qty,
            'byproduct_line_ids': byproduct_vals
        })

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self) -> None:
        if not self.issue_material_id:
            self.update({
                'source_location_ids': [(5, 0, 0)],
                'dest_location_id': False,
                'raw_material_weight': 0.0,
                'byproduct_line_ids': [(5, 0, 0)]
            })
            return

        issue = self.issue_material_id

        # Actual issued quantity: the issue lines carry the weighed actuals
        # (the manufacturing weighbridge writes them back at confirmation).
        validated_qty = issue.total_issue_qty

        dest_loc_id = issue.dest_location_ids[:1].id if issue.dest_location_ids else False

        log_sheets = self.env['production.log.sheet'].search([
            ('issue_material_id', '=', issue.id)
        ])

        byproduct_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for log_sheet in log_sheets:
            for line in log_sheet.byproduct_line_ids:
                byproduct_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.weight,
                    'bags': line.bags,
                    'coverage_ratio': line.percent
                }))

        self.update({
            'raw_material_weight': validated_qty,
            'source_location_ids': [(6, 0, issue.source_location_ids.ids)],
            'dest_location_id': dest_loc_id,
            'byproduct_line_ids': byproduct_vals
        })

    @api.onchange('finished_wb_ticket_id')
    def _onchange_finished_wb_ticket_id(self) -> None:
        """Protocol 2.1 (SRP): Pull finished weights and by-products from the
        Weighbridge, split per product for IRRI multi-product jobs.

        finished_material_weight = TOTAL of all process rice lines (recovery basis).
        primary_finished_weight  = the internal (hidden) product's lines - the
        quantity the MO produces. The other products join the transfer lines
        so they also enter stock with their weighed quantities."""
        if not self.finished_wb_ticket_id:
            return

        wb = self.finished_wb_ticket_id

        allocated_lines = wb.line_ids.filtered(lambda l: l.bjo_id == self.job_order_id)
        self.finished_material_weight = sum(allocated_lines.mapped('allocated_weight'))

        internal_product = self.job_order_id.product_id
        internal_lines = allocated_lines.filtered(lambda l: l.product_id == internal_product)
        self.primary_finished_weight = sum(internal_lines.mapped('allocated_weight'))

        byproduct_vals = [COMMAND_CLEAR_ALL]

        # IRRI multi-product: the OTHER process rice products enter stock via
        # the transfer, with their weighed quantities.
        other_products = self.job_order_id.process_rice_ids - internal_product
        for product in other_products:
            product_lines = allocated_lines.filtered(lambda l: l.product_id == product)
            product_weight = sum(product_lines.mapped('allocated_weight'))
            if product_weight > 0:
                byproduct_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': product.id,
                    'qty': product_weight,
                    'bags': 0,
                    'coverage_ratio': 0.0,
                }))

        for line in wb.wb_byproduct_line_ids:
            byproduct_vals.append((COMMAND_CREATE_NEW, 0, {
                'product_id': line.product_id.id,
                'qty': line.weight,
                'bags': line.bags,
                'coverage_ratio': line.percent
            }))
        self.byproduct_line_ids = byproduct_vals

    def _get_mo_production_weight(self) -> float:
        """Protocol 4.1 (DRY): the quantity the Manufacturing Order produces.
        Multi-product: the internal product's weight. Fallback (manual entry,
        no weighbridge): the total finished weight - which equals the internal
        weight in every single-product scenario."""
        self.ensure_one()
        if self.primary_finished_weight > 0:
            return self.primary_finished_weight
        return self.finished_material_weight

    def action_create_issue_material_from_production(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Material',
            'res_model': 'issue.material',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.job_order_id.id,
                'default_issue_date': fields.Date.today(),
            }
        }

    def action_confirm(self) -> None:
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a Draft Rice Recovery record can be confirmed. Current state: %s.", rec.state))
            if not rec.byproduct_line_ids:
                raise UserError(_("Please add finished goods/by-products before confirming."))
            rec.state = 'confirmed'

    def action_receive_from_mill(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(
                    _("Receive from Mill is only possible from the Confirmed state. Current state: %s.", rec.state))
            if not rec.source_location_ids or not rec.dest_location_id:
                raise UserError(_("Please select both Source and Destination locations before receiving."))

            rec._check_manufacturing_completion_readiness()

            # 1. By-products AND other process rice products into stock.
            transfer_result = rec._create_internal_transfer()

            # 2. Finish the Manufacturing Order: consumes raw rice, produces
            #    the internal process rice product with its actual weighed quantity.
            mo_result = True
            if rec.issue_material_id:
                mo_result = rec.issue_material_id._complete_manufacturing_order(
                    rec._get_mo_production_weight(), rec.dest_location_id)

            rec.state = 'done'

            if not rec.issue_material_id:
                return rec.action_create_issue_material_from_production()

            if isinstance(transfer_result, dict):
                return transfer_result
            if isinstance(mo_result, dict):
                return mo_result
        return True

    def _check_manufacturing_completion_readiness(self) -> None:
        """Protocol 2.1: Fast-fail checks for completing the linked MO."""
        self.ensure_one()
        production = self.mrp_production_id
        if not production or production.state in ('done', 'cancel'):
            return

        if self._get_mo_production_weight() <= 0:
            raise UserError(_(
                "The Finished Material Weight must be greater than zero before receiving "
                "from the mill - it drives the quantity of process rice produced into stock."))

        untracked_lots = production.move_raw_ids.filtered(
            lambda move: move.product_id.tracking != 'none'
            and move.state not in ('done', 'cancel')
            and not move.move_line_ids.mapped('lot_id')
        )
        if untracked_lots:
            raise UserError(_(
                "Lot-tracked raw rice on Manufacturing Order %(order)s has no lots assigned. "
                "Open the Manufacturing Order, assign lots, then receive from the mill again.",
                order=production.name,
            ))

    def _create_internal_transfer(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an internal picking type."))

        header_source_id = self.source_location_ids[0].id if self.source_location_ids else self.dest_location_id.id

        picking = self.env['stock.picking'].create({
            'partner_id': self.job_order_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': self.name,
            'location_id': header_source_id,
            'location_dest_id': self.dest_location_id.id,
        })

        for line in self.byproduct_line_ids:
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.qty,
                'location_id': header_source_id,
                'location_dest_id': self.dest_location_id.id,
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
            if rec.state not in ('draft', 'confirmed'):
                raise UserError(
                    _("Only a Draft or Confirmed Rice Recovery record can be cancelled. Current state: %s.", rec.state))
            if rec.picking_id and rec.picking_id.state != 'cancel':
                rec.picking_id.action_cancel()
            rec.state = 'cancel'

    def unlink(self) -> bool:
        for rec in self:
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_(
                    "You cannot delete a Rice Recovery record that has a validated stock transfer. "
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
            if rec.state != 'cancel':
                raise UserError(
                    _("Only a Cancelled Rice Recovery record can be reset to draft. Current state: %s.", rec.state))
            rec.state = 'draft'

    def action_view_picking(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('stock.picking', self.picking_id.id, 'Internal Transfer')

    def action_view_manufacturing_order(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_form_view('mrp.production', self.mrp_production_id.id, 'Manufacturing Order')


class ProductionRecordLine(models.Model):
    _name = 'production.record.line'
    _description = 'Rice Recovery Line'

    production_id = fields.Many2one('production.record', string='Rice Recovery', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    location_id = fields.Many2one('stock.location', string='Location',
                                  default=lambda self: self.env.ref('stock.stock_location_stock').id)
    qty = fields.Float(string='Quantity')
    bags = fields.Integer(string='Bags')
    coverage_ratio = fields.Float(string='Coverage Ratio (%)')