from odoo import api, fields, models


class BLApproval(models.Model):
    _name = 'bl.approval'
    _description = 'BL Approval'
    _order = 'approval_date desc, id desc'

    name = fields.Char(
        string='Approval Ref',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    bl_draft_ref = fields.Char(
        string='BL Draft Ref',
        required=True,
    )

    booking_no = fields.Char(
        string='Booking No.',
        required=True,
    )

    approval_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval Status',
        required=True,
        default='pending',
    )

    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
    )

    approval_date = fields.Date(
        string='Approval Date',
        readonly=True,
    )

    remarks = fields.Text(
        string='Remarks/Corrections',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'bl.approval'
                ) or 'New'

        return super().create(vals_list)

    def action_approve(self):
        for record in self:
            record.write({
                'approval_status': 'approved',
                'approved_by': self.env.user.id,
                'approval_date': fields.Date.context_today(self),
            })

    def action_reject(self):
        for record in self:
            record.write({
                'approval_status': 'rejected',
                'approved_by': self.env.user.id,
                'approval_date': fields.Date.context_today(self),
            })

    def action_reset_to_pending(self):
        for record in self:
            record.write({
                'approval_status': 'pending',
                'approved_by': False,
                'approval_date': False,
            })