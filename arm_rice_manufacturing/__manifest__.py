{
    'name': 'ARM Rice Manufacturing',
    'version': '19.0.1.0.0',
    'summary': 'Process Rice Spec, Job Orders, and MRP Bridging',
    'description': """
        ARM Rice Manufacturing
        ======================
        Handles the custom Process Rice Specification, Brand Job Orders, 
        and bridges them flawlessly into native Odoo Manufacturing (MRP).
    """,
    'author': 'Abdur Rehman Muhammad',
    'category': 'Manufacturing',
    'depends': ['arm_rice_mill', 'mrp', 'stock'],
    'data': [
            'security/manufacturing_security.xml',
            'security/ir.model.access.csv',
            'data/sequence_data.xml',
            'reports/manufacturing_reports.xml',
            'reports/production_log_report.xml',
            'reports/production_quality_control_report.xml',
            'reports/final_inspection_report.xml',
            'reports/brand_job_order_report.xml',  # <-- MUST BE HERE
            'views/arm_manufacturing_menus.xml',
            'views/process_rice_spec_views.xml',
            'views/brand_job_order_views.xml',     # <-- VIEWS COME AFTER REPORTS
            'views/production_planning_views.xml',
            'views/planning_schedule_views.xml',
            'views/issue_material_views.xml',
            'views/production_record_views.xml',
            'views/final_inspection_report_views.xml',
            'views/production_print_wizard_views.xml',
            'views/production_log_sheet_views.xml',
            'views/production_quality_control_views.xml',
            'views/weighbridge_manufacturing_views.xml',
        ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}
