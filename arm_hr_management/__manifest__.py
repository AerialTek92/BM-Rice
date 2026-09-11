# -*- coding: utf-8 -*-

{
    'name': 'ARM HR Management',
    'version': '19.0.1.0.0',
    'summary': 'Custom HR features including product issuances and salary deductions',
    'description': """
        ARM HR Management
        =================
        Handles custom Human Resources processes for BM Rice, including:
        - Employee Product Issuance and Payroll Deductions
        - (Future HR customizations will be added here)
    """,
    'author': 'Abdur Rehman Muhammad',
    'category': 'Human Resources',
    'depends': ['hr', 'product', 'account', 'hr_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/hr_product_issue_views.xml',
        'views/hr_product_issue_wizard_views.xml',
        'views/hr_exit_views.xml',
        'views/salary_advance_views.xml',
        'views/hr_loan_views.xml',
        'views/hr_final_settlement_views.xml',
    ],
    'installable': True,
    'application': True,
}
