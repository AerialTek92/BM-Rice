# -*- coding: utf-8 -*-

{
    'name': 'ARM Sales Management',
    'version': '19.0.1.0.0',
    'summary': 'Custom Sales Memo fields and sequences',
    'description': """
        ARM Sales Management
        ====================
        Handles custom Sales Memo fields, SM sequence, and menu renaming.
    """,
    'author': 'Abdur Rehman Muhammad',
    'category': 'Sales',
    'depends': ['sale_management', 'am_broker_setup', 'arm_rice_mill'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'reports/delivery_order_report.xml',
        'views/sale_order_views.xml',
        'views/delivery_order_views.xml',
        'views/weighbridge_outbound_views.xml',
        'views/gate_pass_sales_views.xml',
        'views/delivery_report_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}