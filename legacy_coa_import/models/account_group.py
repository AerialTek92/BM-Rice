from odoo import fields, models


class AccountGroup(models.Model):
    _inherit = 'account.group'

    level = fields.Integer(
        string='Level',
        required=True,
        default=1,
    )

    parent_group_id = fields.Many2one(
        'account.group',
        string='Parent Group',
        ondelete='restrict',
        index=True,
    )

    child_group_ids = fields.One2many(
        'account.group',
        'parent_group_id',
        string='Child Groups',
    )

    group_key = fields.Char(
        string='Group Key',
        index=True,
    )

