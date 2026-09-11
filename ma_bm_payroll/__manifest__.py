{
    'name': 'MA BM Payroll',
    'version': '19.0.1.0.0',
    'summary': 'Custom Payroll Extensions (Leave Types)',
    'author': 'Abdur Rehman Muhammad',
    'category': 'Human Resources/Payroll',
    'depends': ['hr_payroll','hr_holidays'],  # Payroll app is required for its menus
    'data': [
        'security/ir.model.access.csv',
        'views/leave_type_views.xml',
        'views/shift_schedule_views.xml',
        'views/overtime_setup_views.xml',
        'views/hr_work_location_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
        # 'views/hr_attendance_biometric_views.xml',
        'views/attendance_upload_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}