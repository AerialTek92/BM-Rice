# -*- coding: utf-8 -*-

from typing import Any, Tuple

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError

# States in which confirmation is still meaningful (later states are no-ops
# for the guard: re-calling confirm on an already-confirmed order must not
# raise on stale approval history).
CONFIRMABLE_STATES: Tuple[str, ...] = ('draft', 'sent')


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'approval.tracker.mixin']

    def action_notify_waiting_approver(self):
        """Next waiting approver ko email bhejna"""
        self.ensure_one()

        next_line = self.env['approval.line'].sudo().search([
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', self.id),
            ('status', '=', 'waiting')
        ], order='sequence asc', limit=1)

        if not next_line:
            return False

        if next_line.employee_id:
            approver = next_line.employee_id
            email_to = approver.work_email or (approver.user_id.login if approver.user_id else False)

            if email_to:
                template_id = 'email_template_po_verification' if next_line.label == 'Verify' else 'email_template_po_final_approval'
                template = self.env.ref(f'approval_matrix.{template_id}', raise_if_not_found=False)

                if not template:
                    template = self.env['mail.template'].sudo().search([('name', '=', template_id)], limit=1)

                if template:
                    template.sudo().with_context(approver_name=approver.name).send_mail(
                        self.id, force_send=True, email_values={'email_to': email_to}
                    )
                    self.sudo().message_post(
                        body=f"🚀 Notification sent to <b>{approver.name}</b> for stage <b>{next_line.label}</b>")
                    return True
        return False

    def action_approve(self):
        """UI ka 'Verify' ya 'Approve' button jab click ho"""
        # 1. Pehle mixin ka kaam hone dein (sync + status change + line update)
        res = super().action_approve()

        # 2. STATUS CHECK: 'verified' -> agli mail; 'approved' -> chatter note.
        for rec in self:
            if rec.approval_status == 'verified':
                rec.action_notify_waiting_approver()
            elif rec.approval_status == 'approved':
                rec.message_post(body="✅ All approvals done via UI button.")

        return res

    def button_confirm(self) -> Any:
        """H20: server-side twin of the view's Confirm gate. Only fully
        approved orders may be confirmed - covers every path the view cannot
        reach (RPC, imports, batch actions). Admin keeps the deliberate
        bypass; orders WITHOUT approval lines carry no approval requirement."""
        is_admin = self.env.user.has_group('base.group_system')
        for order in self:
            if order.state not in CONFIRMABLE_STATES:
                continue
            if not order.approval_line_ids:
                continue
            if order.approval_status != 'approved' and not is_admin:
                raise UserError(_(
                    "You cannot confirm Purchase Order %(order)s until all "
                    "approvals are completed.", order=order.name))
        return super().button_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            matrix = order._apply_default_approval_matrix()
            if matrix:
                line_vals = [Command.create({
                    'res_model': 'purchase.order', 'res_id': order.id,
                    'sequence': m_line.sequence, 'label': m_line.label,
                    'employee_id': m_line.employee_id.id if m_line.employee_id else False,
                    'group_id': m_line.group_id.id if m_line.group_id else False,
                    'matrix_line_id': m_line.id,
                    'status': 'waiting',
                }) for m_line in matrix.line_ids]
                order.sudo().write({'approval_line_ids': line_vals})
                # Pehla email trigger
                order.action_notify_waiting_approver()
        return orders

    def _apply_default_approval_matrix(self):
        return self.env['approval.matrix'].sudo().search([('model_id.model', '=', 'purchase.order')], limit=1)

    def _execute_post_approval(self):
        """Final approval confirms the Purchase Order - the same auto-confirm
        contract Payment Certificate and Brand Job Order already follow."""
        self.ensure_one()
        if self.state in CONFIRMABLE_STATES:
            self.button_confirm()