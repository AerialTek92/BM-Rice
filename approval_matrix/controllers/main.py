# from odoo import http
# from odoo.http import request
#
#
# class PurchaseOrderApprovalController(http.Controller):
#
#     @http.route('/po/approval/<int:res_id>/<string:action_type>', type='http', auth='user', website=True)
#     def po_approval_action(self, res_id, action_type, **kw):
#         """One-Click Email buttons handler"""
#         # sudo() use kar rahe hain Access Error se bachne ke liye
#         order = request.env['purchase.order'].sudo().browse(res_id)
#
#         if order.exists():
#             if action_type == 'verify':
#                 # 1. Status badlein
#                 order.write({'approval_status': 'verified'})
#                 order.message_post(body="Verified via Email button. Sending notification to Senior Manager...")
#                 # 2. Agli mail (Senior Manager) ko Controller se hi trigger karein
#                 order.action_notify_approver_by_label('Approval', 'email_template_po_final_approval')
#
#             elif action_type == 'approve':
#                 order.write({'approval_status': 'approved'})
#                 order.message_post(body="Approved via Email button.")
#
#             elif action_type == 'refuse':
#                 order.write({'approval_status': 'refused'})
#                 order.message_post(body="Refused via Email button.")
#
#         # Action ke baad redirect back to record
#         return request.redirect(f'/web#id={res_id}&model=purchase.order&view_type=form')


from odoo import http, fields
from odoo.http import request


class PurchaseOrderApprovalController(http.Controller):

    @http.route('/po/approval/<int:res_id>/<string:action_type>', type='http', auth='public', website=True)
    def po_approval_action(self, res_id, action_type, **kw):
        order = request.env['purchase.order'].sudo().browse(res_id)
        if not order.exists():
            return "Order Not Found"

        if action_type == 'verify':
            # UI button ke bagair jab email se click ho:
            line = order.approval_line_ids.filtered(lambda l: l.label == 'Verify' and l.status == 'waiting')
            if line:
                line.sudo().write({'status': 'done', 'approval_date': fields.Datetime.now()})

            order.sudo().write({'approval_status': 'verified'})
            # Agli mail trigger karein
            order.sudo().action_notify_waiting_approver()

        elif action_type == 'approve':
            line = order.approval_line_ids.filtered(lambda l: l.label == 'Approval' and l.status == 'waiting')
            if line:
                line.sudo().write({'status': 'done', 'approval_date': fields.Datetime.now()})
            order.sudo().write({'approval_status': 'approved'})

        elif action_type == 'refuse':
            order.sudo().write({'approval_status': 'refused'})

        return request.redirect(f'/web#id={res_id}&model=purchase.order&view_type=form')
