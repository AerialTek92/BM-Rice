{
    'name': 'Bop Charts',
    'version': '0.1',
    'category': 'Tools',
    'depends': ['base', 'purchase', 'stock', 'account', 'web', ],
    "data": [
        'views/purchase_menu.xml',
    ],
    "assets": {
        "web.assets_backend": [
            'bop_charts/static/src/js/purchase_dashboard.js',
            'bop_charts/static/src/xml/purchase_dashboard.xml',
        ],
    },
    "installable": True,
}
