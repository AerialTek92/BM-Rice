from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApprovalTrackerMixin(models.AbstractModel):
    _name = 'approval.tracker.mixin'
    _description = 'Approval Tracker Mixin'

    approval_line_ids = fields.One2many(
        'approval.line', 'res_id',
        string='Approvals',
        domain=lambda self: [('res_model', '=', self._name)]
    )

    approval_status = fields.Selection([
        ('prepared', 'Prepared'),
        ('verified', 'Verified'),
        ('approved', 'Approved'),
        ('refused', 'Refused')
    ], compute='_compute_approval_status', store=True)

    approval_label = fields.Char(compute='_compute_approval_label')
    can_user_approve = fields.Boolean(compute='_compute_can_user_approve')

    pending_line_label = fields.Char(compute='_compute_pending_line_label')
    is_admin = fields.Boolean(compute='_compute_is_admin')
    can_edit_rfq = fields.Boolean(compute='_compute_can_edit_rfq')

    @api.depends('approval_line_ids.status')
    def _compute_approval_status(self) -> None:
        for rec in self:
            if not rec.approval_line_ids:
                rec.approval_status = 'prepared'
            elif any(l.status == 'refuse' for l in rec.approval_line_ids):
                rec.approval_status = 'refused'
            elif all(l.status == 'done' for l in rec.approval_line_ids):
                rec.approval_status = 'approved'
            elif any(l.status == 'done' for l in rec.approval_line_ids):
                rec.approval_status = 'verified'
            else:
                rec.approval_status = 'prepared'

    @api.depends('approval_status', 'approval_line_ids.status')
    def _compute_approval_label(self) -> None:
        for rec in self:
            if not rec.approval_line_ids:
                rec.approval_label = "✅ No approvals required"
            elif rec.approval_status == 'approved':
                rec.approval_label = "✅ All Approvals Done"
            elif rec.approval_status == 'refused':
                rec.approval_label = "❌ Refused"
            elif rec.approval_status == 'verified':
                rec.approval_label = "🔄 Verified, waiting final approval"
            else:
                waiting = []
                for l in rec.approval_line_ids.filtered(lambda l: l.status == 'waiting'):
                    if l.employee_id:
                        waiting.append(l.employee_id.name)
                    elif l.group_id:
                        waiting.append(f"Group: {l.group_id.name}")
                rec.approval_label = "⏳ Waiting for: " + ", ".join(waiting)

    @api.depends('approval_line_ids.status', 'approval_line_ids.label')
    def _compute_pending_line_label(self) -> None:
        for rec in self:
            pending = rec.approval_line_ids.filtered(lambda l: l.status == 'waiting')
            rec.pending_line_label = pending[:1].label if pending else False

    @api.depends('approval_line_ids.status', 'approval_line_ids.employee_id', 'approval_line_ids.group_id')
    def _compute_can_user_approve(self) -> None:
        current_user = self.env.user
        current_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)
        
        for rec in self:
            rec.can_user_approve = False
            pending = rec.approval_line_ids.filtered(lambda l: l.status == 'waiting')
            if not pending:
                continue
            
            next_line = pending[0]
            
            # Group Approval Logic (CR-07)
            if next_line.group_id:
                if current_user.id in next_line.group_id.users.ids:
                    rec.can_user_approve = True
            # Individual Approval Logic
            elif next_line.employee_id and current_employee:
                if next_line.employee_id.id == current_employee.id:
                    rec.can_user_approve = True

    def _compute_is_admin(self) -> None:
        is_admin = self.env.user.has_group('base.group_system')
        for rec in self:
            rec.is_admin = is_admin

    @api.depends('approval_status')
    def _compute_can_edit_rfq(self) -> None:
        is_admin = self.env.user.has_group('base.group_system')
        for rec in self:
            is_creator = rec.create_uid.id == self.env.uid
            rec.can_edit_rfq = is_admin or (is_creator and rec.approval_status == 'prepared')

    def _apply_default_approval_matrix(self):
        self.ensure_one()
        return self.env['approval.matrix'].search([
            ('model_id.model', '=', self._name)
        ], limit=1)

    def action_approve(self) -> None:
        self.ensure_one()
        current_user = self.env.user
        current_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)
        
        pending = self.approval_line_ids.filtered(lambda l: l.status == 'waiting')
        if not pending:
            return

        next_line = pending[0]
        is_authorized = False

        if next_line.group_id:
            if current_user.id in next_line.group_id.users.ids:
                is_authorized = True
        elif next_line.employee_id and current_employee:
            if next_line.employee_id.id == current_employee.id:
                is_authorized = True

        if not is_authorized:
            if next_line.group_id:
                raise UserError(_("You are not authorized to approve this. Waiting for a member of group: %s") % next_line.group_id.name)
            else:
                raise UserError(_("You are not the next approver. Waiting for %s") % next_line.employee_id.name)

        # Mark as done and record who actually approved it
        next_line.write({
            'status': 'done', 
            'time_of_approval': fields.Datetime.now(),
            'approved_by_id': current_employee.id if current_employee else False
        })

        remaining_pending = self.approval_line_ids.filtered(lambda l: l.status == 'waiting')
        if not remaining_pending:
            self._execute_post_approval()

    def action_refuse(self) -> None:
        self.ensure_one()
        current_user = self.env.user
        current_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)
        
        pending = self.approval_line_ids.filtered(lambda l: l.status == 'waiting')
        if not pending:
            return

        next_line = pending[0]
        is_authorized = False

        if next_line.group_id:
            if current_user.id in next_line.group_id.users.ids:
                is_authorized = True
        elif next_line.employee_id and current_employee:
            if next_line.employee_id.id == current_employee.id:
                is_authorized = True

        if not is_authorized:
            raise UserError(_("You are not authorized to refuse this."))

        next_line.write({
            'status': 'refuse', 
            'time_of_approval': fields.Datetime.now(),
            'approved_by_id': current_employee.id if current_employee else False
        })
        self._execute_post_refusal()

    def _execute_post_approval(self):
        pass

    def _execute_post_refusal(self):
        pass