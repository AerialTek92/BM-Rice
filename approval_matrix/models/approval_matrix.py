from odoo import models, fields


class ApprovalMatrix(models.Model):
    _name = 'approval.matrix'
    _description = 'Approval Matrix Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, tracking=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, tracking=True, ondelete='cascade')
    
    # NEW: Scoping field for Product Type / Plant
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
    
    # employee_id = fields.Many2one('hr.employee', string='Approver', required=True)



class ApprovalLine(models.Model):
    _name = 'approval.line'
    _description = 'Approval Line Instance'
    _order = 'sequence, id'

    res_model = fields.Char(string='Related Document Model', required=True)
    res_id = fields.Integer(string='Related Document ID', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    label = fields.Char(string='Label')
    
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