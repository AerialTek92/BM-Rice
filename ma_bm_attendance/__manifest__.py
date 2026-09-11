{
    'name': 'BM Attendance Uploader',
    'version': '19.0.1.0.6',
    'summary': 'Upload biometric XLS - Client Sheet Format',
    'author': 'Muhammad Adil',
    'category': 'Human Resources',
    'depends': ['hr_attendance', 'hr', 'base'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
        # 'views/hr_attendance_biometric_views.xml',
        'views/attendance_upload_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}