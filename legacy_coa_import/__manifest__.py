{
    'name': 'Legacy COA Customization',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Customize Account Groups for Legacy COA',
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_group_views.xml',
        'views/account_account_views.xml',
        'views/account_account_search_views.xml'
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}