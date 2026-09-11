# from odoo import models, fields, api, _, Command
# from odoo.exceptions import UserError
# from typing import Dict, Any, List
#
#
# # --- FIX: hr.employee mein version_revision add karna ---
# class HrEmployee(models.Model):
#     _inherit = 'hr.employee'
#
#     version_revision = fields.Integer(string='Version Revision Fix', default=0)
#
#
# # --- FIX: Public profiles mein bhi field add karna taake Access Error na aaye ---
# class HrEmployeePublic(models.Model):
#     _inherit = 'hr.employee.public'
#
#     version_revision = fields.Integer(string='Version Revision Fix', readonly=True)
#
#
# # --- PURCHASE ORDER: Mukammal Logic ---
# class PurchaseOrder(models.Model):
#     _inherit = ['purchase.order', 'approval.tracker.mixin']
#
#     @api.model_create_multi
#     def create(self, vals_list: List[Dict[str, Any]]) -> 'PurchaseOrder':
#         """Batch create with matrix application and notification"""
#         orders = super(PurchaseOrder, self).create(vals_list)
#         for order in orders:
#             matrix = order._apply_default_approval_matrix()
#             if matrix:
#                 line_vals = []
#                 for m_line in matrix.line_ids:
#                     line_vals.append(Command.create({
#                         'res_model': 'purchase.order',
#                         'res_id': order.id,
#                         'sequence': m_line.sequence,
#                         'label': m_line.label,
#                         'employee_id': m_line.employee_id.id if m_line.employee_id else False,
#                         'group_id': m_line.group_id.id if m_line.group_id else False,
#                         'status': 'waiting',
#                     }))
#                 if line_vals:
#                     order.write({'approval_line_ids': line_vals})
#
#                 # Pehli email trigger (Finance Manager)
#                 if order.approval_status == 'prepared':
#                     order.action_notify_approver_by_label('Verify', 'email_template_po_verification')
#         return orders
#
#     def write(self, vals):
#         """Status change hone par email trigger karna"""
#         res = super(PurchaseOrder, self).write(vals)
#         if 'approval_status' in vals:
#             status = vals.get('approval_status')
#             for rec in self:
#                 if status == 'prepared':
#                     rec.action_notify_approver_by_label('Verify', 'email_template_po_verification')
#                 elif status == 'verified':
#                     # Agli stage (Senior Manager)
#                     rec.action_notify_approver_by_label('Approval', 'email_template_po_final_approval')
#         return res
#
#     def action_notify_approver_by_label(self, label_name, template_xmlid):
#         """Database se approver dhoond kar email bhejne ka engine"""
#         self.ensure_one()
#         # Direct database search taake cache ka error na aaye
#         line = self.env['approval.line'].sudo().search([
#             ('res_model', '=', 'purchase.order'),
#             ('res_id', '=', self.id),
#             ('label', '=ilike', label_name.strip())
#         ], limit=1)
#
#         if line and line.employee_id:
#             user = line.employee_id.user_id
#             email_to = user.email if user else line.employee_id.work_email
#             approver_name = line.employee_id.name
#
#             if email_to:
#                 # ZAROORI: Apna folder name check kar lein (approval_matrix)
#                 module_name = 'approval_matrix'
#                 template = self.env.ref(f'{module_name}.{template_xmlid}', raise_if_not_found=False)
#
#                 if template:
#                     template.with_context(approver_name=approver_name).send_mail(
#                         self.id, force_send=True, email_values={'email_to': email_to}
#                     )
#                     self.message_post(
#                         body=_(f"Approval email sent to <b>{approver_name}</b> for stage: <b>{label_name}</b>"))
#                     return True
#         return False
#
#     def button_confirm(self):
#         """Confirmation security check"""
#         for order in self:
#             is_admin = self.env.user.has_group('base.group_system')
#             if hasattr(order, 'approval_line_ids') and order.approval_line_ids:
#                 if order.approval_status != 'approved' and not is_admin:
#                     raise UserError(_("You cannot confirm this order until all approvals are completed."))
#         return super().button_confirm()
#
#     def _apply_default_approval_matrix(self):
#         """Rice Type matrix logic"""
#         self.ensure_one()
#         rice_type = False
#         if self.order_line and self.order_line[0].product_id:
#             if hasattr(self.order_line[0].product_id, 'is_brown_rice') and self.order_line[0].product_id.is_brown_rice:
#                 rice_type = 'basmati'
#         if rice_type:
#             matrix = self.env['approval.matrix'].search(
#                 [('model_id.model', '=', 'purchase.order'), ('rice_type', '=', rice_type)], limit=1)
#             if matrix: return matrix
#         return self.env['approval.matrix'].search(
#             [('model_id.model', '=', 'purchase.order'), ('rice_type', '=', 'all')], limit=1)


from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError


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
        # 1. Pehle mixin ka kaam hone dein (Status change aur line update)
        res = super(PurchaseOrder, self).action_approve()

        # 2. STATUS CHECK: Agar status 'verified' ho gaya hai (Finance ne click kiya)
        # to agli mail Senior Manager ko trigger karein
        for rec in self:
            if rec.approval_status == 'verified':
                rec.action_notify_waiting_approver()
            elif rec.approval_status == 'approved':
                rec.message_post(body="✅ All approvals done via UI button.")

        return res

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            matrix = order._apply_default_approval_matrix()
            if matrix:
                line_vals = [Command.create({
                    'res_model': 'purchase.order', 'res_id': order.id,
                    'sequence': m.sequence, 'label': m.label,
                    'employee_id': m.employee_id.id, 'status': 'waiting',
                }) for m in matrix.line_ids]
                order.sudo().write({'approval_line_ids': line_vals})
                # Pehla email trigger
                order.action_notify_waiting_approver()
        return orders

    def _apply_default_approval_matrix(self):
        return self.env['approval.matrix'].sudo().search([('model_id.model', '=', 'purchase.order')], limit=1)
