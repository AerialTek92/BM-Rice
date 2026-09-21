# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Dict, Any


class WeighbridgeTicket(models.Model):
    _inherit = 'weighbridge.ticket'

    ticket_type = fields.Selection([
        ('procurement', 'Procurement'),
        ('manufacturing', 'Manufacturing')
    ], string='Ticket Type', default='procurement', tracking=True)

    issue_material_id = fields.Many2one('issue.material', string='Issue Material Ref',
                                        domain="[('state', '=', 'confirmed')]")
    production_record_id = fields.Many2one('production.record', string='Production Record')

    @api.onchange('ticket_type')
    def _onchange_ticket_type(self):
        if self.ticket_type == 'procurement':
            self.issue_material_id = False
            self.production_record_id = False
        elif self.ticket_type == 'manufacturing':
            self.gate_pass_id = False
            self.grn_inspection_id = False
            self.rice_sales_contract_id = False

        self.line_ids = [(5, 0, 0)]

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id_manufacturing(self):
        if not self.issue_material_id:
            return

        issue = self.issue_material_id
        self.vehicle_number = issue.vehicle_no
        self.partner_id = issue.job_order_id.partner_id.id
        self.ticket_type = 'manufacturing'

        line_vals = [(5, 0, 0)]
        for line in issue.issue_line_ids:
            line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'bags': line.bags,
                'allocated_weight': 0.0,
            }))
        self.line_ids = line_vals

    def action_confirm(self):
        for rec in self:
            if rec.ticket_type == 'manufacturing':
                if not rec.line_ids:
                    raise UserError(_("You must allocate the weight to materials before confirming."))
                if round(rec.total_allocated_weight, 2) > round(rec.net_weight, 2):
                    raise ValidationError(_(
                        "Total allocated weight (%(allocated)s kg) cannot exceed the Net Weight (%(net)s kg).",
                        allocated=rec.total_allocated_weight, net=rec.net_weight
                    ))
                rec.state = 'confirmed'
                return True

        return super().action_confirm()

    def action_create_production_record(self) -> Dict[str, Any]:
        self.ensure_one()

        pr = self.env['production.record'].create({
            'job_order_id': self.issue_material_id.job_order_id.id,
            'issue_material_id': self.issue_material_id.id,
            'weighbridge_ticket_id': self.id,
            'raw_material_weight': self.net_weight,
            'location_id': self.issue_material_id.dest_location_id.id,
            'dest_location_id': self.issue_material_id.location_id.id,
            'production_date': fields.Date.today(),
        })

        self.production_record_id = pr.id
        return pr._open_form_view('production.record', pr.id, 'Production Record')

    def action_complete_manufacturing_process(self) -> None:
        for rec in self:
            if rec.ticket_type == 'manufacturing' and rec.production_record_id and rec.production_record_id.state == 'done':
                rec.state = 'done'
            else:
                raise UserError(
                    _("The Production Record must be fully processed (Received from Mill) before completing the Weighbridge."))

    # NEW: Auto-complete the Weighbridge process when the 2nd weight is captured
    def action_capture_tare_weight(self):
        res = super().action_capture_tare_weight()
        for rec in self:
            # If the Mill team already finished, and the WB team just added the 2nd weight, finish the WB!
            if rec.ticket_type == 'manufacturing' and rec.production_record_id and rec.production_record_id.state == 'done' and rec.tare_weight > 0:
                rec.state = 'done'
        return res