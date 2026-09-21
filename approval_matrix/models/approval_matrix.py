# -*- coding: utf-8 -*-

from typing import Any, Dict, Tuple

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Matrix-line fields whose changes must reach the waiting approval instances
# of already-created documents (live approver sync).
MATRIX_LINE_SYNC_FIELDS: Tuple[str, ...] = ('sequence', 'label', 'employee_id', 'group_id')


class ApprovalMatrix(models.Model):
    _name = 'approval.matrix'
    _description = 'Approval Matrix Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, tracking=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, tracking=True, ondelete='cascade')

    # Scoping field for Product Type / Plant
    rice_type = fields.Selection([
        ('irri', 'IRRI (BM-1)'),
        ('basmati', 'Basmati (BM-2)'),
        ('all', 'All Types')
    ], string='Applies To', default='all', required=True)

    line_ids = fields.One2many('approval.matrix.line', 'matrix_id', string='Approvers')


class ApprovalMatrixLine(models.Model):
    _name = 'approval.matrix.line'
    _description = 'Approval Matrix Line Template'
    _order = 'sequence, id'

    matrix_id = fields.Many2one('approval.matrix', string='Matrix', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    label = fields.Char(string='Label', required=True)

    # Option 1: Specific Employee
    employee_id = fields.Many2one('hr.employee', string='Specific Approver')

    # Option 2: Group Approval (CR-07)
    group_id = fields.Many2one('res.groups', string='Approval Group')

    # ----------------------------------------------------------
    # CONFIGURATION GUARD
    # ----------------------------------------------------------

    @api.constrains('employee_id', 'group_id')
    def _check_approver_configured(self) -> None:
        """A matrix line must name who approves - otherwise the instantiated
        approval line can never be satisfied by anyone (deadlock guard)."""
        for line in self:
            if not line.employee_id and not line.group_id:
                raise ValidationError(_(
                    "Approval line '%(label)s' needs either a Specific Approver "
                    "or an Approval Group.", label=line.label))

    # ----------------------------------------------------------
    # LIVE APPROVER SYNC (push side)
    # ----------------------------------------------------------

    def write(self, vals: Dict[str, Any]) -> bool:
        result = super().write(vals)
        if any(field in vals for field in MATRIX_LINE_SYNC_FIELDS):
            self._propagate_to_waiting_approval_lines()
        return result

    def _propagate_to_waiting_approval_lines(self) -> None:
        """The matrix is the source of truth for every approval that has NOT
        been acted on yet: editing a matrix line reassigns its waiting
        instances immediately. Done/refused lines are history and are never
        rewritten.

        Legacy instances (created before 'matrix_line_id' existed, so the
        link is empty) are matched by res_model + sequence and healed - the
        link is stamped so every later sync is exact."""
        approval_line = self.env['approval.line']
        for matrix_line in self:
            model_name = matrix_line.matrix_id.model_id.model
            if not model_name:
                continue

            exact_lines = approval_line.search([
                ('matrix_line_id', '=', matrix_line.id),
                ('status', '=', 'waiting'),
            ])
            legacy_lines = approval_line.search([
                ('matrix_line_id', '=', False),
                ('status', '=', 'waiting'),
                ('res_model', '=', model_name),
                ('sequence', '=', matrix_line.sequence),
            ])

            waiting_lines = exact_lines | legacy_lines
            if waiting_lines:
                waiting_lines.write({
                    'matrix_line_id': matrix_line.id,
                    'sequence': matrix_line.sequence,
                    'label': matrix_line.label,
                    'employee_id': matrix_line.employee_id.id,
                    'group_id': matrix_line.group_id.id,
                })


class ApprovalLine(models.Model):
    _name = 'approval.line'
    _description = 'Approval Line Instance'
    _order = 'sequence, id'

    res_model = fields.Char(string='Related Document Model', required=True)
    res_id = fields.Integer(string='Related Document ID', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    label = fields.Char(string='Label')

    # The matrix line this instance was created from. Waiting lines are kept
    # in sync with it (live approver follow); acted-on lines keep it for
    # traceability.
    matrix_line_id = fields.Many2one(
        'approval.matrix.line', string='Source Matrix Line',
        ondelete='set null', index=True)

    # Instance fields for both logic paths
    employee_id = fields.Many2one('hr.employee', string='Expected Approver')
    group_id = fields.Many2one('res.groups', string='Expected Group')

    # Tracking
    approved_by_id = fields.Many2one('hr.employee', string='Approved By')
    time_of_approval = fields.Datetime(string='Time of Approval')
    status = fields.Selection([
        ('waiting', 'Waiting'),
        ('refuse', 'Refused'),
        ('done', 'Done'),
    ], default='waiting', string='Status')