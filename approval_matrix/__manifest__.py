{
    'name': 'Approval Matrix',
    'version': '19.0.1.0.0',
    'summary': 'Generic Approval Matrix System',
    'depends': ['base', 'mail', 'hr', 'purchase'],
    'category': 'Shariq Ali Mehdi',
    'data': [
        'security/ir.model.access.csv',
        'views/mail_templates_views.xml',
        'views/approval_matrix_views.xml',
        'views/purchase_order_views.xml',

    ],
    'installable': True,
    'application': True,
}
