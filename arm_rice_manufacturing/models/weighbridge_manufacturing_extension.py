# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0


class WeighbridgeTicketManufacturing(models.Model):
    _inherit = 'weighbridge.ticket'

    # ==========================================
    # 1. EXISTING: BASMATI ISSUE MATERIAL FLOW
    # ==========================================
    issue_material_id = fields.Many2one(
        'issue.material', string='Issue Material Ref',
        domain="[('state', '=', 'confirmed'), ('rice_type', '=', 'basmati'), ('picking_id', '=', False)]"
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
        """Basmati Flow: Creates and validates the Internal Transfer from Weighbridge allocation."""
        self.ensure_one()
        self._validate_weight_allocation()

        if not self.issue_material_id:
            raise UserError(_("Please select an Issue Material reference before confirming."))

        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("Please configure an internal picking type."))

        issue = self.issue_material_id

        # FIX: issue.material uses 'source_location_ids' and 'dest_location_ids' (Many2many).
        # Take the first one for the picking header.
        header_source_id = issue.source_location_ids[:1].id if issue.source_location_ids else False
        header_dest_id = issue.dest_location_ids[:1].id if issue.dest_location_ids else False

        if not header_source_id or not header_dest_id:
            raise UserError(_("Please ensure both Source and Destination locations are set on the Issue Material."))

        picking = self.env['stock.picking'].create({
            'partner_id': issue.job_order_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': f"WB-MFG: {self.name} / {issue.name}",
            'location_id': header_source_id,
            'location_dest_id': header_dest_id,
        })

        for line in self.line_ids:
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.allocated_weight,
                'location_id': header_source_id,
                'location_dest_id': header_dest_id,
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
                    issue.write({'picking_id': picking.id})
                    return validate_res
            else:
                issue.write({'picking_id': picking.id})
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Internal Transfer',
                    'res_model': 'stock.picking',
                    'view_mode': 'form',
                    'res_id': picking.id,
                    'target': 'current',
                }

        issue.write({'picking_id': picking.id})
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
    # 2. NEW: FINISHED / BI-PRODUCTS WEIGHBRIDGE
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
        """Protocol 2.1 (SRP): Map header data from Log Sheet."""
        for rec in self:
            log = rec.log_sheet_id
            rec.mfg_bjo_1_id = log.job_order_1_id.id if log else False
            rec.mfg_bjo_2_id = log.job_order_2_id.id if log else False
            rec.mfg_partner_1_id = log.customer_1_id.id if log else False
            rec.mfg_partner_2_id = log.customer_2_id.id if log else False

    @api.onchange('is_finished_weighbridge')
    def _onchange_is_finished_weighbridge(self) -> None:
        """Protocol 2.1: Clear unrelated references when toggling the checkbox."""
        if self.is_finished_weighbridge:
            self.issue_material_id = False
        else:
            self.log_sheet_id = False

    @api.onchange('log_sheet_id')
    def _onchange_log_sheet_id(self) -> None:
        """Protocol 2.1 (SRP): Auto-populate lines with Process Rice from the Log Sheet's BJOs."""
        if not self.log_sheet_id:
            self.line_ids = [COMMAND_CLEAR_ALL]
            return

        line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]

        if self.log_sheet_id.job_order_1_id and self.log_sheet_id.job_order_1_id.product_id:
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'bjo_id': self.log_sheet_id.job_order_1_id.id,
                'product_id': self.log_sheet_id.job_order_1_id.product_id.id,
                'allocated_weight': 0.0,
            }))

        if self.log_sheet_id.job_order_2_id and self.log_sheet_id.job_order_2_id.product_id:
            line_vals.append((COMMAND_CREATE_NEW, 0, {
                'bjo_id': self.log_sheet_id.job_order_2_id.id,
                'product_id': self.log_sheet_id.job_order_2_id.product_id.id,
                'allocated_weight': 0.0,
            }))

        self.line_ids = line_vals

    def action_confirm_finished_weighbridge(self) -> None:
        """Protocol 2.1 (SRP): Dedicated confirmation for Finished Goods Weighbridge (no stock transfer)."""
        for rec in self:
            if rec.gross_weight <= 0 or rec.tare_weight <= 0:
                raise UserError(_("Please capture both First and Second weights before confirming."))
            rec._validate_weight_allocation()
            rec.state = 'confirmed'


class WeighbridgeTicketLineManufacturing(models.Model):
    _inherit = 'weighbridge.ticket.line'

    # Existing fields
    issue_material_id = fields.Many2one('issue.material', string='Issue Material')
    issue_material_line_id = fields.Many2one('issue.material.line', string='Issue Material Line')

    # NEW: Link to Brand Job Order for Finished Weighbridge lines
    bjo_id = fields.Many2one('brand.job.order', string='Brand Job Order')