from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def write(self, vals):

        res = super(PurchaseOrder, self).write(vals)

        if 'approval_status' in vals:
            status = vals.get('approval_status')

            if status == 'prepared':
                self._notify_approver_from_matrix(target_label='Verify', template_id='email_template_po_verification')

            elif status == 'verified':
                self._notify_approver_from_matrix(target_label='Approval',
                                                  template_id='email_template_po_final_approval')

        return res

    def _notify_approver_from_matrix(self, target_label, template_id):
        self.ensure_one()
        target_line = self.approval_line_ids.filtered(lambda l: l.label == target_label)

        if target_line and target_line.user_id:
            approver = target_line.user_id
            template = self.env.ref(f'approval_matrix.{template_id}', raise_if_not_found=False)

            if template and approver.email:
                template.with_context(approver_name=approver.name).send_mail(
                    self.id,
                    force_send=True,
                    email_values={'email_to': approver.email}
                )
                self.message_post(body=_(f"Notification sent to {approver.name} for {target_label} stage."))