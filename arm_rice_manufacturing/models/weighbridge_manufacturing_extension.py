# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Any, Dict, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class WeighbridgeTicketManufacturing(models.Model):
    _inherit = 'weighbridge.ticket'

    # ==========================================
    # 1. BASMATI ISSUE MATERIAL WEIGHING
    # (Linked IM must have its Manufacturing Order: stock is consumed by
    # the MO, never by a transfer from here.)
    # ==========================================
    issue_material_id = fields.Many2one(
        'issue.material', string='Issue Material Ref',
        domain="[('state', '=', 'confirmed'), ('rice_type', '=', 'basmati'), ('mrp_production_id', '!=', False)]"
    )
    mfg_job_order_id = fields.Many2one('brand.job.order', string='Brand Job Order', compute='_compute_mfg_data',
                                       store=True, readonly=True)
    mfg_prs_id = fields.Many2one('process.rice.spec', string='Rice Specification Ref', compute='_compute_mfg_data',
                                 store=True, readonly=True)
    mfg_partner_id = fields.Many2one('res.partner', string='Customer', compute='_compute_mfg_data', store=True,
                                     readonly=True)

    @api.depends('issue_material_id')
    def _compute_mfg_data(self):
        for rec in self:
            rec.mfg_job_order_id = rec.issue_material_id.job_order_id.id if rec.issue_material_id else False
            rec.mfg_prs_id = rec.mfg_job_order_id.process_rice_spec_id.id if rec.mfg_job_order_id else False
            rec.mfg_partner_id = rec.mfg_job_order_id.partner_id.id if rec.mfg_job_order_id else False

    @api.onchange('weighbridge_type')
    def _onchange_weighbridge_type(self):
        if self.weighbridge_type == 'manufacturing':
            self.gate_pass_id = False
            self.grn_inspection_id = False
            self.partner_id = False
            self.vehicle_number = False
            self.line_ids = [COMMAND_CLEAR_ALL]
        else:
            self.issue_material_id = False
            self.line_ids = [COMMAND_CLEAR_ALL]

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self):
        if not self.issue_material_id:
            self.line_ids = [COMMAND_CLEAR_ALL]
            return

        self.partner_id = self.issue_material_id.job_order_id.partner_id.id
        line_vals = []
        for im_line in self.issue_material_id.issue_line_ids:
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'issue_material_id': self.issue_material_id.id,
                'issue_material_line_id': im_line.id,
                'product_id': im_line.product_id.id,
                'bags': im_line.bags,
                'allocated_weight': im_line.qty_mt,
            }))
        self.line_ids = line_vals

    def action_confirm_manufacturing(self) -> Dict[str, Any]:
        """Basmati flow: the Weighbridge is the WEIGHING step of the Issue
        Material's Manufacturing Order. Confirming writes the weighed
        allocations back onto the issue lines and the MO's raw-move demand;
        physical stock is consumed once, when the Production Record completes
        the MO. No internal transfer is created."""
        self.ensure_one()
        self._validate_weight_allocation()

        issue = self.issue_material_id
        if not issue:
            raise UserError(_("Please select an Issue Material reference before confirming."))

        production = issue.mrp_production_id
        if not production:
            raise UserError(_(
                "Issue Material %(issue)s has no Manufacturing Order to weigh against. "
                "Confirm the Issue Material (Issue to Mill) first.",
                issue=issue.name))
        if production.state in ('done', 'cancel'):
            raise UserError(_(
                "Manufacturing Order %(order)s is already %(state)s: it can no longer be weighed.",
                order=production.name, state=production.state))

        weighed_lines = self.line_ids.filtered(lambda line: line.allocated_weight > 0)
        if not weighed_lines:
            raise UserError(_("Allocate a positive weight to at least one raw rice line before confirming."))

        for line in weighed_lines:
            if line.issue_material_line_id:
                line.issue_material_line_id.write({
                    'qty_mt': line.allocated_weight,
                    'bags': line.bags,
                })
            raw_move = production.move_raw_ids.filtered(
                lambda move: move.product_id == line.product_id)[:1]
            if raw_move:
                raw_move.write({'product_uom_qty': line.allocated_weight})

        self.state = 'confirmed'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issue Material',
            'res_model': 'issue.material',
            'view_mode': 'form',
            'res_id': issue.id,
            'target': 'current',
        }

    # ==========================================
    # 2. FINISHED / BI-PRODUCTS WEIGHBRIDGE
    # (Weighing only - stock enters via Production Record -> MO completion.)
    # ==========================================
    is_finished_weighbridge = fields.Boolean(string="Finished / Bi-Products", default=False)

    log_sheet_id = fields.Many2one(
        'production.log.sheet',
        string='Log Sheet Ref',
        domain="[('state', '=', 'confirmed')]"
    )

    mfg_bjo_1_id = fields.Many2one('brand.job.order', compute='_compute_log_sheet_data', store=True, readonly=True,
                                   string='1st Job Order')
    mfg_bjo_2_id = fields.Many2one('brand.job.order', compute='_compute_log_sheet_data', store=True, readonly=True,
                                   string='2nd Job Order')
    mfg_partner_1_id = fields.Many2one('res.partner', compute='_compute_log_sheet_data', store=True, readonly=True,
                                       string='1st Customer')
    mfg_partner_2_id = fields.Many2one('res.partner', compute='_compute_log_sheet_data', store=True, readonly=True,
                                       string='2nd Customer')

    wb_byproduct_line_ids = fields.One2many('production.log.byproduct.line', 'wb_ticket_id', string='Bi-Products')

    @api.depends('log_sheet_id')
    def _compute_log_sheet_data(self) -> None:
        for rec in self:
            log = rec.log_sheet_id
            rec.mfg_bjo_1_id = log.job_order_1_id.id if log else False
            rec.mfg_bjo_2_id = log.job_order_2_id.id if log else False
            rec.mfg_partner_1_id = log.customer_1_id.id if log else False
            rec.mfg_partner_2_id = log.customer_2_id.id if log else False

    @api.onchange('is_finished_weighbridge')
    def _onchange_is_finished_weighbridge(self) -> None:
        if self.is_finished_weighbridge:
            self.issue_material_id = False
        else:
            self.log_sheet_id = False

    @api.onchange('log_sheet_id')
    def _onchange_log_sheet_id(self) -> None:
        """Protocol 2.1 (SRP): Auto-populate lines with Process Rice from the
        Log Sheet's BJOs - one line per product (all products for IRRI)."""
        if not self.log_sheet_id:
            self.line_ids = [COMMAND_CLEAR_ALL]
            return

        line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]

        for job_order in (self.log_sheet_id.job_order_1_id, self.log_sheet_id.job_order_2_id):
            if not job_order:
                continue
            # Multi list for IRRI; falls back to the single product otherwise.
            for product in (job_order.process_rice_ids or job_order.product_id):
                line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'bjo_id': job_order.id,
                    'product_id': product.id,
                    'allocated_weight': 0.0,
                }))

        self.line_ids = line_vals

    def action_confirm_finished_weighbridge(self) -> None:
        """Protocol 2.1 (SRP): Dedicated confirmation for Finished Goods Weighbridge
        (weighing only - no stock transfer, no MO interaction)."""
        for rec in self:
            if rec.gross_weight <= 0 or rec.tare_weight <= 0:
                raise UserError(_("Please capture both First and Second weights before confirming."))
            rec._validate_weight_allocation()
            rec.state = 'confirmed'


class WeighbridgeTicketLineManufacturing(models.Model):
    _inherit = 'weighbridge.ticket.line'

    issue_material_id = fields.Many2one('issue.material', string='Issue Material')
    issue_material_line_id = fields.Many2one('issue.material.line', string='Issue Material Line')

    bjo_id = fields.Many2one('brand.job.order', string='Brand Job Order')