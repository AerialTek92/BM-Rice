{
    'name': 'BM Security',
    'version': '19.0.1.0.0',
    'category': 'Security',
    'summary': 'BM Security Groups and Access Controls',
    'description': """
        BM Security
        ===========
        Custom security groups and access controls.
    """,
    'author': 'BM',
    'depends': [
        'purchase',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}