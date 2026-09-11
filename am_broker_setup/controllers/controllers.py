# from odoo import http


# class AmBrokerSetup(http.Controller):
#     @http.route('/am_broker_setup/am_broker_setup', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/am_broker_setup/am_broker_setup/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('am_broker_setup.listing', {
#             'root': '/am_broker_setup/am_broker_setup',
#             'objects': http.request.env['am_broker_setup.am_broker_setup'].search([]),
#         })

#     @http.route('/am_broker_setup/am_broker_setup/objects/<model("am_broker_setup.am_broker_setup"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('am_broker_setup.object', {
#             'object': obj
#         })

