# -*- coding: utf-8 -*-
from odoo import models, fields, api

PERCENTAGE_DIVISOR: float = 100.0


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Header level custom fields
    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'broker')]")
    delivery_date = fields.Date(string='Delivery Date')
    delivery_remarks = fields.Text(string='Delivery Remarks')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Line level custom fields
    pcs = fields.Float(string='Pcs')
    ctn = fields.Float(string='Ctn')
    discount_amount = fields.Monetary(string='Disct Amt', compute='_compute_net_amount', store=True)
    discount_special = fields.Monetary(string='Disct Sp.')
    net_amount = fields.Monetary(string='Net Amt', compute='_compute_net_amount', store=True)

    # --- Net Amount Calculation Logic (Converted to Compute for reliability) ---
    @api.depends('product_uom_qty', 'price_unit', 'discount', 'discount_special')
    def _compute_net_amount(self) -> None:
        """Protocol 2.1 (SRP): Calculate Net Amount based on Qty, Price, and Discounts."""
        for line in self:
            base_amount = line.product_uom_qty * line.price_unit

            if line.discount:
                line.discount_amount = base_amount * (line.discount / PERCENTAGE_DIVISOR)
            else:
                line.discount_amount = 0.0

            line.net_amount = base_amount - (line.discount_amount or 0.0) - (line.discount_special or 0.0)