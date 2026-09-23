{
    'name': 'BOP Purchase Dashboard',
    'version': '19.0.2.0.0',
    'category': 'Tools',
    'summary': 'Interactive Purchase & Inventory dashboard (light/dark mode)',
    'author': 'Abdur Rehman Muhammad',
    'license': 'LGPL-3',
    'depends': ['base', 'purchase', 'stock', 'account', 'web'],
    'data': [
        'views/purchase_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'bop_charts/static/src/js/purchase_dashboard.js',
            'bop_charts/static/src/xml/purchase_dashboard.xml',
            'bop_charts/static/src/css/purchase_dashboard.css',
        ],
    },
    'installable': True,
}