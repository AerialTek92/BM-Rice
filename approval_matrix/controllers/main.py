# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PurchaseOrderApprovalController(http.Controller):

    @http.route('/po/approval/<int:res_id>/<string:action_type>', type='http',
                auth='user', website=True)
    def po_approval_action(self, res_id, action_type, **kw):
        """One-click email buttons: authenticated, and only the CURRENT
        pending approver may act. Delegates to the tracker mixin, which
        handles line status, authorization, notifications and post-approval."""
        order = request.env['purchase.order'].browse(res_id)
        if not order.exists():
            return request.not_found()

        if not order.can_user_approve:
            order.message_post(body=(
                f"⚠️ Approval link for stage '{action_type}' was clicked by an "
                f"unauthorized user: {request.env.user.name}"))
            return request.redirect(f'/web#id={res_id}&model=purchase.order&view_type=form')

        if action_type in ('verify', 'approve'):
            order.action_approve()
        elif action_type == 'refuse':
            order.action_refuse()
        else:
            return request.not_found()

        return request.redirect(f'/web#id={res_id}&model=purchase.order&view_type=form')