{
    'name': "am_broker_setup",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'contacts', 'mail'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',  # Load sequences here
        'views/res_partner_view.xml',
        'views/product_temp_view.xml',
        'views/transporter_setup_view.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

