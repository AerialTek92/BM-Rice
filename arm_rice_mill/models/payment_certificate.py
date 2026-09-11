# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Dict, Any, List, Tuple
from datetime import date
from dataclasses import dataclass

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0
PERCENTAGE_DIVISOR: float = 100.0

# --- Searchable Constants (Protocol 1.3) ---
ALLOWANCE_MOISTURE: str = 'moisture'
ALLOWANCE_BROKEN: str = 'broken'
ALLOWANCE_FILL_BAGS: str = 'fill bags'
PICKING_INCOMING: str = 'incoming'
PICKING_DONE: str = 'done'


@dataclass
class AllowanceQuery:
    """Encapsulates parameters for allowance rate calculation (Protocol 2.2)."""
    product: 'product.product'
    allowance_name: str
    percentage: float
    check_date: date


class PaymentCertificate(models.Model):
    _name = 'payment.certificate'
    _description = 'Payment Certificate'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'approval.tracker.mixin']
    _order = 'id desc'

    name = fields.Char(string='PC No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='PC Date', default=fields.Date.today(), required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id,
                                  required=True)

    # FIX: Updated domain to use has_payment_cert to exclude GRNs that already have any PC (even draft)
    grn_id = fields.Many2one(
        'stock.picking', string='GRN No.', required=True,
        domain=f"[('picking_type_code', '=', '{PICKING_INCOMING}'), ('state', '=', '{PICKING_DONE}'), ('has_payment_cert', '=', False)]"
    )

    grn_date = fields.Date(related='grn_id.grn_date', string='GRN Date', store=True, readonly=True)
    purchase_id = fields.Many2one(related='grn_id.purchase_id', string='Purchase Order', store=True, readonly=True)
    purchase_order_date = fields.Datetime(related='purchase_id.date_order', string='PO Date', store=True, readonly=True)
    po_due_date = fields.Date(related='purchase_id.delivery_date_to', string='PO Due Date', store=True, readonly=True)
    rice_sales_contract_id = fields.Many2one(related='grn_id.rice_sales_contract_id', string='Sales Contract',
                                             store=True, readonly=True)
    partner_id = fields.Many2one(related='grn_id.partner_id', string='Supplier', store=True, readonly=True)

    product_id = fields.Many2one(related='grn_id.product_id', string='Product', store=True, readonly=True)
    bags = fields.Integer(related='grn_id.bags', string='Bags', store=True, readonly=True)
    rate = fields.Float(related='grn_id.price_unit', string='Rate', store=True, readonly=True)

    amount = fields.Monetary(string='Amount', compute='_compute_amount', store=True, currency_field='currency_id')

    net_weight = fields.Float(related='grn_id.net_weight', string='Net Weight', store=True, readonly=True)
    vehicle_number = fields.Char(related='grn_id.vehicle_number', string='Vehicle No.', store=True, readonly=True)
    transporter_id = fields.Many2one(related='grn_id.transporter_id', string='Transporter', store=True, readonly=True)

    gross_amount = fields.Monetary(
        string='Gross Amount',
        compute='_compute_gross_amount',
        store=True,
        currency_field='currency_id'
    )

    broker_id = fields.Many2one('res.partner', string='Broker', domain="[('partner_assign_type', '=', 'broker')]")
    buyer_id = fields.Many2one('hr.employee', string='Buyer')
    broker_brokerage_rate = fields.Float(related='broker_id.brokerage_rate', string='Broker Rate/Bag', readonly=True,
                                         store=True)
    broker_wh_tax_rate = fields.Float(related='broker_id.wh_tax_rate', string='Broker WHT Rate (%)', readonly=True,
                                      store=True)

    filling_bags = fields.Integer(related='grn_id.filling_bags', string='Filling Bags', store=True, readonly=False)
    moisture_actual = fields.Float(related='grn_id.actual_moisture', string='Moisture %', store=True, readonly=False)
    broken_actual = fields.Float(related='grn_id.actual_broken', string='Broken %', store=True, readonly=False)

    moisture_allowance_rate = fields.Float(string='Rate/Kg', readonly=True, digits=(16, 4))
    broken_allowance_rate = fields.Float(string='Rate/Kg', readonly=True, digits=(16, 4))
    filling_bags_allowance_rate = fields.Float(string='Rate/Kg', readonly=True, digits=(16, 4))

    moisture_deduction = fields.Integer(
        string='Moisture Deduction',
        compute='_compute_moisture_deduction',
        store=True,
        readonly=False
    )
    broken_deduction = fields.Integer(
        string='Broken Deduction',
        compute='_compute_broken_deduction',
        store=True,
        readonly=False
    )
    filling_bags_deduction = fields.Integer(
        string='Filling Bags Deduction',
        compute='_compute_filling_bags_deduction',
        store=True,
        readonly=False
    )

    total_deductions = fields.Integer(
        string='Total Deductions',
        compute='_compute_total_deductions',
        store=True,
        readonly=False
    )

    add_brokerage = fields.Monetary(string='|Add| Brokerage', currency_field='currency_id')
    less_wh_tax_brokerage = fields.Monetary(string='|Less| WHT Brokerage', currency_field='currency_id')
    add_transportation = fields.Monetary(string='|Add| Transportation', currency_field='currency_id')
    add_bardana = fields.Monetary(string='|Add| Bardana', currency_field='currency_id')
    add_labour = fields.Monetary(string='|Add| Labour', currency_field='currency_id')
    add_commission = fields.Monetary(string='|Add| Commission', currency_field='currency_id')
    add_other = fields.Monetary(string='|Add| Other', currency_field='currency_id')

    less_damage = fields.Monetary(string='|Less| Damage', currency_field='currency_id')
    less_weighing_charges = fields.Monetary(string='|Less| Weighing Charges', currency_field='currency_id')
    less_other_deductions = fields.Monetary(string='|Less| Other Deductions', currency_field='currency_id')

    total_charges = fields.Monetary(string='Total Charges (Deducted)', compute='_compute_totals', store=True,
                                    currency_field='currency_id')

    net_payable = fields.Integer(
        string='Net Payable',
        compute='_compute_totals',
        store=True
    )

    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('paid', 'Paid')], string='Status',
                             default='draft', tracking=True)

    # NEW: Link to Payment Vouchers (Vendor Bills)
    payment_voucher_ids = fields.One2many('account.move', 'payment_certificate_id', string='Payment Vouchers')
    payment_voucher_count = fields.Integer(string='Vouchers', compute='_compute_payment_voucher_count')

    remarks = fields.Html(string='Remarks')

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'PaymentCertificate':
        # FIX: Generate sequence number on creation
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('payment.certificate') or _('New')

        records = super().create(vals_list)
        for rec in records:
            matrix = rec._apply_default_approval_matrix()
            if matrix:
                line_vals = []
                for m_line in matrix.line_ids:
                    line_vals.append((COMMAND_CREATE_NEW, 0, {
                        'res_model': rec._name,
                        'res_id': rec.id,
                        'sequence': m_line.sequence,
                        'label': m_line.label,
                        'employee_id': m_line.employee_id.id,
                        'status': 'waiting',
                    }))
                if line_vals:
                    rec.approval_line_ids = line_vals
        return records

    def _compute_payment_voucher_count(self) -> None:
        for rec in self:
            rec.payment_voucher_count = len(rec.payment_voucher_ids)

    def action_view_payment_vouchers(self) -> Dict[str, Any]:
        """Protocol 2.1 (SRP): Smart button to view linked Payment Vouchers."""
        self.ensure_one()
        return self._open_related_records('account.move', 'payment_certificate_id', 'Payment Voucher')

    @api.depends('rate', 'net_weight')
    def _compute_amount(self) -> None:
        for rec in self:
            rec.amount = rec.rate * rec.net_weight

    @api.depends('rate', 'net_weight')
    def _compute_gross_amount(self) -> None:
        for rec in self:
            rec.gross_amount = rec.rate * rec.net_weight

    @api.depends('moisture_allowance_rate', 'net_weight')
    def _compute_moisture_deduction(self) -> None:
        for rec in self:
            rec.moisture_deduction = round(rec.net_weight * rec.moisture_allowance_rate)

    @api.depends('broken_allowance_rate', 'net_weight')
    def _compute_broken_deduction(self) -> None:
        for rec in self:
            rec.broken_deduction = round(rec.net_weight * rec.broken_allowance_rate)

    @api.depends('filling_bags_allowance_rate', 'filling_bags')
    def _compute_filling_bags_deduction(self) -> None:
        for rec in self:
            rec.filling_bags_deduction = round(rec.filling_bags * rec.filling_bags_allowance_rate)

    @api.depends('moisture_deduction', 'broken_deduction', 'filling_bags_deduction')
    def _compute_total_deductions(self) -> None:
        for rec in self:
            rec.total_deductions = rec.moisture_deduction + rec.broken_deduction + rec.filling_bags_deduction

    @api.depends(
        'total_deductions',
        'add_brokerage', 'add_transportation', 'add_bardana',
        'add_labour', 'add_commission', 'add_other',
        'less_wh_tax_brokerage', 'less_damage', 'less_weighing_charges', 'less_other_deductions',
        'gross_amount'
    )
    def _compute_totals(self) -> None:
        for rec in self:
            total_additions = (
                    rec.add_brokerage + rec.add_transportation + rec.add_bardana +
                    rec.add_labour + rec.add_commission + rec.add_other
            )
            total_subtractions = (
                    rec.less_wh_tax_brokerage + rec.less_damage +
                    rec.less_weighing_charges + rec.less_other_deductions
            )

            rec.net_payable = round(rec.gross_amount - rec.total_deductions + total_additions - total_subtractions)
            rec.total_charges = total_additions - total_subtractions

    def _get_allowance_rate(self, query: AllowanceQuery) -> float:
        if not query.product or not query.percentage:
            return 0.0

        product_tmpl = query.product.product_tmpl_id
        if not product_tmpl.allowance_type_ids:
            return 0.0

        matching_type = product_tmpl.allowance_type_ids.filtered(
            lambda t: (t.name and t.name.lower() == query.allowance_name) or
                      (t.code and t.code.lower() == query.allowance_name)
        )
        if not matching_type:
            return 0.0

        matching_lines = matching_type[0].template_line_ids.filtered(
            lambda l: l.from_pct <= query.percentage <= l.to_pct
                      and (not l.from_date or l.from_date <= query.check_date)
                      and (not l.to_date or l.to_date >= query.check_date)
        )
        return matching_lines[:1].rate_per_kg

    @api.onchange('grn_id')
    def _onchange_grn_id(self) -> None:
        if not self.grn_id:
            return
        self._sync_broker_from_purchase()
        self._sync_buyer_from_purchase()
        self._calculate_quality_allowances()
        self._calculate_brokerage()

    def _sync_broker_from_purchase(self) -> None:
        if not self.broker_id and self.grn_id.purchase_id.broker_id:
            self.broker_id = self.grn_id.purchase_id.broker_id

    def _sync_buyer_from_purchase(self) -> None:
        if not self.buyer_id and self.grn_id.purchase_id.buyer_id:
            self.buyer_id = self.grn_id.purchase_id.buyer_id

    def _calculate_quality_allowances(self) -> None:
        check_date = self.date or fields.Date.today()

        moisture_query = AllowanceQuery(
            product=self.grn_id.product_id,
            allowance_name=ALLOWANCE_MOISTURE,
            percentage=self.grn_id.actual_moisture,
            check_date=check_date
        )
        self.moisture_allowance_rate = self._get_allowance_rate(moisture_query)

        broken_query = AllowanceQuery(
            product=self.grn_id.product_id,
            allowance_name=ALLOWANCE_BROKEN,
            percentage=self.grn_id.actual_broken,
            check_date=check_date
        )
        self.broken_allowance_rate = self._get_allowance_rate(broken_query)

        filling_bags_query = AllowanceQuery(
            product=self.grn_id.product_id,
            allowance_name=ALLOWANCE_FILL_BAGS,
            percentage=self.filling_bags,
            check_date=check_date
        )
        self.filling_bags_allowance_rate = self._get_allowance_rate(filling_bags_query)

    def _calculate_brokerage(self) -> None:
        if not self.broker_id:
            self.add_brokerage = 0.0
            self.less_wh_tax_brokerage = 0.0
            return

        net_weight = self.grn_id.net_weight if self.grn_id else 0.0
        self.add_brokerage = (net_weight * self.broker_id.brokerage_rate) / PERCENTAGE_DIVISOR
        self.less_wh_tax_brokerage = self.add_brokerage * (self.broker_id.wh_tax_rate / PERCENTAGE_DIVISOR)

    @api.onchange('broker_id')
    def _onchange_broker_id(self) -> None:
        self._calculate_brokerage()

    def action_confirm(self) -> None:
        for rec in self:
            is_admin = self.env.user.has_group('base.group_system')
            if rec.approval_line_ids and rec.approval_status != 'approved' and not is_admin:
                raise UserError(_("You cannot confirm this Payment Certificate until all approvals are completed."))
            rec.state = 'confirmed'

    def action_mark_paid(self) -> None:
        for rec in self: rec.state = 'paid'

    def action_reset_to_draft(self) -> None:
        for rec in self: rec.state = 'draft'

    def unlink(self) -> bool:
        return super().unlink()

    def _execute_post_approval(self):
        """Automatically confirm the Payment Certificate when the final approval is done."""
        self.ensure_one()
        if self.state == 'draft':
            self.state = 'confirmed'


class PaymentCertificateLine(models.Model):
    _name = 'payment.certificate.line'
    _description = 'Payment Certificate Line'

    certificate_id = fields.Many2one('payment.certificate', string='Certificate', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item')
    bags = fields.Integer(string='Bags')
    rate = fields.Monetary(string='Rate', currency_field='currency_id')
    chart_amount = fields.Monetary(string='As Per Chart Amount', currency_field='currency_id')
    amount = fields.Monetary(string='Amount', compute='_compute_amount', store=True, currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', related='certificate_id.currency_id', readonly=True)

    @api.depends('bags', 'rate')
    def _compute_amount(self) -> None:
        for line in self:
            line.amount = line.bags * line.rate