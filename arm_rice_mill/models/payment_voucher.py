# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# ==========================================================
# CONSTANTS
# ==========================================================

VENDOR_BILL_MOVE_TYPE = "in_invoice"
DRAFT_STATE = "draft"


# ==========================================================
# DEBUG LOGGER
# ==========================================================

def _pc_log(message, *args):
    """
    Payment Certificate accounting debug logger.

    Uses both:
        print()
        _logger.warning()

    so the logs are visible even when INFO logging
    is not enabled.
    """

    try:
        rendered = message % args if args else message
    except Exception:
        rendered = f"{message} {args}"

    print(f"[PC-ACCOUNTING] {rendered}")

    _logger.warning(
        "[PC-ACCOUNTING] %s",
        rendered,
    )


# ==========================================================
# ACCOUNT MOVE
# ==========================================================

class AccountMove(models.Model):
    _inherit = "account.move"

    # ======================================================
    # PAYMENT CERTIFICATE FIELDS
    # ======================================================

    broker_id = fields.Many2one(
        "res.partner",
        string="Broker",
        domain="[('partner_assign_type', '=', 'vendor')]",
        copy=False,
    )

    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        copy=False,
    )

    payment_certificate_id = fields.Many2one(
        "payment.certificate",
        string="Payment Certificate",
        domain="[('partner_id', '=', partner_id), "
               "('state', 'in', ['confirmed', 'paid'])]",
        copy=False,
    )

    rice_pc_amount = fields.Monetary(
        string="PC Amount",
        currency_field="currency_id",
        copy=False,
    )

    brokerage_charges = fields.Monetary(
        string="Brokerage Charges",
        currency_field="currency_id",
        copy=False,
    )

    withholding_tax_amount = fields.Monetary(
        string="Withholding Tax",
        currency_field="currency_id",
        copy=False,
    )

    pc_net_weight = fields.Float(
        string="PC Net Weight",
        copy=False,
    )

    pc_rate = fields.Monetary(
        string="PC Rate",
        currency_field="currency_id",
        copy=False,
    )

    pc_total_payable = fields.Monetary(
        string="PC Total Payable",
        currency_field="currency_id",
        compute="_compute_pc_total_payable",
        store=True,
        copy=False,
    )
    # ==========================================================
    # NORMAL VENDOR BILL TAX CONFIGURATION
    # ==========================================================

    withholding_tax_rate = fields.Float(
        string="Withholding Tax Rate (%)",
        digits=(16, 4),
        default=0.0,
    )

    income_tax_rate = fields.Float(
        string="Income Tax Rate (%)",
        digits=(16, 4),
        default=0.0,
    )

    income_tax_account = fields.Many2one(
        "account.account",
        string="Income Tax Account",
        check_company=True,
    )

    # ==========================================================
    # NORMAL VENDOR BILL TAX FIELDS
    # ==========================================================

    normal_withholding_tax_rate = fields.Float(
        string="Withholding Tax (%)",
        digits=(16, 4),
        copy=False,
    )

    normal_withholding_tax_amount = fields.Monetary(
        string="Withholding Tax Amount",
        currency_field="currency_id",
        compute="_compute_normal_vendor_tax_amounts",
        store=True,
        copy=False,
    )

    normal_income_tax_rate = fields.Float(
        string="Income Tax (%)",
        digits=(16, 4),
        copy=False,
    )

    normal_income_tax_amount = fields.Monetary(
        string="Income Tax Amount",
        currency_field="currency_id",
        compute="_compute_normal_vendor_tax_amounts",
        store=True,
        copy=False,
    )

    normal_tax_base_amount = fields.Monetary(
        string="Tax Base Amount",
        currency_field="currency_id",
        compute="_compute_normal_vendor_tax_amounts",
        store=True,
        copy=False,
    )

    # ==========================================================
    # NORMAL VENDOR TAX CALCULATION
    # ==========================================================

    @api.depends(
        "invoice_line_ids.price_subtotal",
        "normal_withholding_tax_rate",
        "normal_income_tax_rate",
        "payment_certificate_id",
        "move_type",
    )
    def _compute_normal_vendor_tax_amounts(self):

        for move in self:

            # --------------------------------------------------
            # PC BILL = NORMAL TAX CALCULATION DISABLED
            # --------------------------------------------------

            if (
                    move.move_type != VENDOR_BILL_MOVE_TYPE
                    or move.payment_certificate_id
            ):
                move.normal_tax_base_amount = 0.0
                move.normal_withholding_tax_amount = 0.0
                move.normal_income_tax_amount = 0.0

                continue

            # --------------------------------------------------
            # TAX BASE
            #
            # Only actual product/service invoice lines.
            # --------------------------------------------------

            tax_lines = move.invoice_line_ids.filtered(
                lambda line:
                line.display_type == "product"
            )

            tax_base = sum(
                tax_lines.mapped("price_subtotal")
            )

            # --------------------------------------------------
            # RATES
            # --------------------------------------------------

            withholding_rate = float(
                move.normal_withholding_tax_rate or 0.0
            )

            income_tax_rate = float(
                move.normal_income_tax_rate or 0.0
            )

            # --------------------------------------------------
            # CALCULATE
            # --------------------------------------------------

            withholding_amount = (
                    tax_base
                    * withholding_rate
                    / 100.0
            )

            income_tax_amount = (
                    tax_base
                    * income_tax_rate
                    / 100.0
            )

            # --------------------------------------------------
            # ASSIGN
            # --------------------------------------------------

            move.normal_tax_base_amount = tax_base

            move.normal_withholding_tax_amount = (
                withholding_amount
            )

            move.normal_income_tax_amount = (
                income_tax_amount
            )

            # --------------------------------------------------
            # DEBUG
            # --------------------------------------------------

            move._pc_log(
                "NORMAL TAX COMPUTATION | "
                "Move=%s | "
                "Tax Base=%s | "
                "WHT Rate=%s%% | "
                "WHT Amount=%s | "
                "Income Tax Rate=%s%% | "
                "Income Tax Amount=%s",
                move.display_name,
                tax_base,
                withholding_rate,
                withholding_amount,
                income_tax_rate,
                income_tax_amount,
            )

    # ==========================================================
    # NORMAL VENDOR TAX RATE ONCHANGE
    # ==========================================================

    @api.onchange("partner_id")
    def _onchange_normal_vendor_bill_partner_tax(self):

        for move in self:

            if move.move_type != VENDOR_BILL_MOVE_TYPE:
                continue

            # --------------------------------------------------
            # PAYMENT CERTIFICATE
            #
            # PC flow must remain completely separate.
            # --------------------------------------------------

            if move.payment_certificate_id:
                move.normal_withholding_tax_rate = 0.0
                move.normal_income_tax_rate = 0.0

                move._pc_log(
                    "NORMAL TAX ONCHANGE SKIPPED | "
                    "Move=%s | PC=%s",
                    move.display_name,
                    move.payment_certificate_id.display_name,
                )

                continue

            # --------------------------------------------------
            # NO VENDOR
            # --------------------------------------------------

            if not move.partner_id:
                move.normal_withholding_tax_rate = 0.0
                move.normal_income_tax_rate = 0.0

                continue

            # --------------------------------------------------
            # LOAD PARTNER CONFIGURATION
            # --------------------------------------------------

            partner = move.partner_id

            move.normal_withholding_tax_rate = float(
                partner.withholding_tax_rate or 0.0
            )

            move.normal_income_tax_rate = float(
                partner.income_tax_rate or 0.0
            )

            move._pc_log(
                "NORMAL TAX RATE LOADED | "
                "Move=%s | "
                "Partner=%s | Partner ID=%s | "
                "WHT Rate=%s%% | "
                "Income Tax Rate=%s%%",
                move.display_name,
                partner.display_name,
                partner.id,
                move.normal_withholding_tax_rate,
                move.normal_income_tax_rate,
            )

    # ======================================================
    # SQL CONSTRAINT
    # ======================================================

    _sql_constraints = [
        (
            "unique_payment_certificate",
            "unique(payment_certificate_id)",
            "A vendor bill already exists for this Payment Certificate.",
        ),
    ]

    # ======================================================
    # LOG HELPER
    # ======================================================

    def _pc_log(self, message, *args):
        _pc_log(message, *args)

    # ======================================================
    # COMPUTE TOTAL PAYABLE
    # ======================================================

    @api.depends(
        "rice_pc_amount",
        "brokerage_charges",
        "withholding_tax_amount",
    )
    def _compute_pc_total_payable(self):

        for move in self:

            amount = float(
                move.rice_pc_amount or 0.0
            )

            brokerage = float(
                move.brokerage_charges or 0.0
            )

            withholding = float(
                move.withholding_tax_amount or 0.0
            )

            move.pc_total_payable = (
                amount
                + brokerage
                - withholding
            )

            move._pc_log(
                "COMPUTE TOTAL PAYABLE | "
                "Move=%s | Amount=%s | Brokerage=%s | "
                "Withholding=%s | Total Payable=%s",
                move.display_name,
                amount,
                brokerage,
                withholding,
                move.pc_total_payable,
            )

    # ======================================================
    # PURCHASE ORDER FROM PAYMENT CERTIFICATE
    # ======================================================

    def _get_pc_purchase_order(self, pc):
        """
        Payment Certificate -> Purchase Order.

        IMPORTANT:
        Payment Certificate field is `purchase_id`.
        """

        purchase = pc.purchase_id

        self._pc_log(
            "PURCHASE LOOKUP | "
            "PC=%s | PC ID=%s | "
            "purchase_id=%s | PO=%s | PO ID=%s",
            pc.display_name,
            pc.id,
            purchase.id if purchase else False,
            purchase.name if purchase else False,
            purchase.id if purchase else False,
        )

        if not purchase:

            raise UserError(
                _(
                    "No Purchase Order is linked with "
                    "Payment Certificate %s."
                )
                % pc.display_name
            )

        return purchase

    # ======================================================
    # GET PRODUCT FROM PURCHASE ORDER
    # ======================================================

    def _get_pc_product(self, purchase):

        po_lines = purchase.order_line.filtered(
            lambda line:
                line.product_id
                and not line.display_type
        )

        product = po_lines[:1].product_id

        self._pc_log(
            "PRODUCT LOOKUP | "
            "PO=%s | PO ID=%s | "
            "Lines=%s | Product=%s | Product ID=%s",
            purchase.name,
            purchase.id,
            len(po_lines),
            product.display_name if product else False,
            product.id if product else False,
        )

        if not product:

            raise UserError(
                _(
                    "No product was found on "
                    "Purchase Order %s."
                )
                % purchase.name
            )

        return product

    # ======================================================
    # GET PRODUCT EXPENSE ACCOUNT
    # ======================================================

    def _get_pc_bill_line_account(
        self,
        product,
        company=None,
    ):
        """
        Get product expense account.

        IMPORTANT:
        No manual debit/credit is created here.
        """

        company = company or self.env.company

        product_company = product.with_company(
            company
        )

        accounts = product_company._get_product_accounts()

        account = accounts.get("expense")

        self._pc_log(
            "PRODUCT ACCOUNT | "
            "Product=%s | Product ID=%s | "
            "Company=%s | "
            "Expense Account=%s | Account ID=%s | "
            "Code=%s | Type=%s",
            product.display_name,
            product.id,
            company.display_name,
            account.display_name if account else False,
            account.id if account else False,
            account.code if account else False,
            account.account_type if account else False,
        )

        if not account:

            raise UserError(
                _(
                    "No expense account is configured "
                    "for product %s."
                )
                % product.display_name
            )

        return account

    # ======================================================
    # PREPARE HEADER VALUES
    # ======================================================

    def _prepare_pc_bill_header_vals(
            self,
            pc,
            company=None,
    ):
        """
        Prepare account.move header values.

        IMPORTANT:
        Do NOT set standard account.move.purchase_id here.

        This method is used by onchange as well.

        Setting purchase_id during onchange triggers Odoo Purchase's
        automatic PO invoice-line population, which causes duplicate
        product lines.

        Standard purchase_id is assigned ONLY inside create().
        """

        purchase = self._get_pc_purchase_order(pc)

        company = (
                company
                or purchase.company_id
                or self.env.company
        )

        partner = pc.partner_id

        if not partner:
            raise UserError(
                _(
                    "Payment Certificate %s "
                    "has no vendor/partner."
                )
                % pc.display_name
            )

        # ======================================================
        # PC VALUES
        # ======================================================

        amount = float(
            pc.amount or 0.0
        )

        net_weight = float(
            pc.net_weight or 0.0
        )

        rate = float(
            pc.rate or 0.0
        )

        brokerage = float(
            pc.add_brokerage or 0.0
        )

        withholding = float(
            pc.less_wh_tax_brokerage or 0.0
        )

        net_payable = (
                amount
                + brokerage
                - withholding
        )

        self._pc_log(
            "HEADER | "
            "PC=%s | ID=%s | "
            "Partner=%s | Partner ID=%s | "
            "PO=%s | PO ID=%s | "
            "Amount=%s | Weight=%s | Rate=%s | "
            "Brokerage=%s | Withholding=%s | "
            "Net Payable=%s",
            pc.display_name,
            pc.id,
            partner.display_name,
            partner.id,
            purchase.name,
            purchase.id,
            amount,
            net_weight,
            rate,
            brokerage,
            withholding,
            net_payable,
        )

        # ======================================================
        # BROKER
        # ======================================================

        broker = False

        if pc.broker_id:
            broker = pc.broker_id

        self._pc_log(
            "BROKER LOOKUP | "
            "PC=%s | Broker=%s | Broker ID=%s",
            pc.display_name,
            broker.display_name if broker else False,
            broker.id if broker else False,
        )

        # ======================================================
        # BASIC MOVE VALUES
        # ======================================================

        vals = {
            "partner_id": partner.id,

            # --------------------------------------------------
            # CUSTOM PO LINK
            #
            # This is YOUR custom field.
            # It does NOT trigger Purchase's purchase_id onchange.
            # --------------------------------------------------

            "purchase_order_id": purchase.id,

            "broker_id": (
                broker.id
                if broker
                else False
            ),

            "payment_certificate_id": pc.id,

            "rice_pc_amount": amount,

            "brokerage_charges": brokerage,

            "withholding_tax_amount": withholding,

            "pc_net_weight": net_weight,

            "pc_rate": rate,

            "pc_total_payable": net_payable,

            "ref": pc.display_name,

            "payment_reference": pc.display_name,

            "invoice_origin": purchase.name,

            "invoice_date": fields.Date.context_today(
                self
            ),
        }

        # ======================================================
        # IMPORTANT
        #
        # DO NOT PUT:
        #
        # vals["purchase_id"] = purchase.id
        #
        # HERE.
        #
        # Standard purchase_id is handled in create().
        # ======================================================

        # ======================================================
        # SUPPLIER PAYMENT TERM
        # ======================================================

        supplier_term = (
            partner
            .with_company(company)
            .property_supplier_payment_term_id
        )

        if supplier_term:
            vals[
                "invoice_payment_term_id"
            ] = supplier_term.id

            self._pc_log(
                "PAYMENT TERM | "
                "Partner=%s | Term=%s | Term ID=%s",
                partner.display_name,
                supplier_term.display_name,
                supplier_term.id,
            )

        self._pc_log(
            "HEADER VALUES PREPARED | "
            "purchase_id intentionally NOT included | "
            "%s",
            vals,
        )

        return vals

    # ======================================================
    # RICE INVOICE LINE
    # ======================================================

    def _prepare_pc_rice_line_vals(
        self,
        pc,
        purchase,
        product,
        expense_account,
    ):
        """
        Prepare rice expense invoice line.

        Expected:

            DR Rice Expense = PC Amount
        """

        amount = float(
            pc.amount or 0.0
        )

        weight = float(
            pc.net_weight or 0.0
        )

        rate = float(
            pc.rate or 0.0
        )

        if amount and weight <= 0:

            raise UserError(
                _(
                    "Payment Certificate %s has an "
                    "amount of %s but its net weight is zero."
                )
                % (
                    pc.display_name,
                    amount,
                )
            )

        # --------------------------------------------------
        # IMPORTANT
        #
        # Amount is authoritative.
        #
        # price_unit = amount / weight
        #
        # This avoids rounding differences.
        # --------------------------------------------------

        if weight:

            unit_price = (
                amount / weight
            )

        else:

            unit_price = rate

        calculated_amount = (
            weight * unit_price
        )

        self._pc_log(
            "RICE LINE | "
            "PC=%s | Product=%s | Product ID=%s | "
            "Weight=%s | Rate=%s | "
            "Unit Price Used=%s | "
            "Calculated=%s | PC Amount=%s | "
            "Account=%s | Account ID=%s",
            pc.display_name,
            product.display_name,
            product.id,
            weight,
            rate,
            unit_price,
            calculated_amount,
            amount,
            expense_account.display_name,
            expense_account.id,
        )

        return {
            "sequence": 10,

            "display_type": "product",

            "product_id": product.id,

            "name": product.display_name,

            "quantity": weight,

            "price_unit": unit_price,

            "account_id": expense_account.id,

            # No partner_id.
            # Odoo handles move line partner.

            # NO debit
            # NO credit
            # NO balance
            # NO date_maturity

            "tax_ids": [
                Command.clear()
            ],
        }

    # ======================================================
    # BROKERAGE LINE
    # ======================================================

    def _prepare_brokerage_line_vals(
        self,
        pc,
    ):
        """
        Prepare brokerage expense line.

        Expected:

            DR Brokerage Expense
        """

        brokerage = float(
            pc.add_brokerage or 0.0
        )

        # --------------------------------------------------
        # ZERO BROKERAGE
        # --------------------------------------------------

        if not brokerage:

            self._pc_log(
                "BROKERAGE LINE | "
                "PC=%s | Brokerage is zero. "
                "No brokerage line.",
                pc.display_name,
            )

            return False

        # --------------------------------------------------
        # BROKER
        # --------------------------------------------------

        broker = pc.broker_id

        if not broker:

            raise UserError(
                _(
                    "Payment Certificate %s has brokerage "
                    "amount %s but no Broker is selected."
                )
                % (
                    pc.display_name,
                    brokerage,
                )
            )

        # --------------------------------------------------
        # BROKER ACCOUNT
        # --------------------------------------------------

        account = broker.broker_account

        self._pc_log(
            "BROKERAGE LOOKUP | "
            "PC=%s | Broker=%s | Broker ID=%s | "
            "Account=%s | Account ID=%s | "
            "Type=%s | Amount=%s",
            pc.display_name,
            broker.display_name,
            broker.id,
            account.display_name if account else False,
            account.id if account else False,
            account.account_type if account else False,
            brokerage,
        )

        if not account:

            raise UserError(
                _(
                    "No Brokerage Expense Account is "
                    "configured for Broker %s."
                )
                % broker.display_name
            )

        return {
            "sequence": 20,

            "display_type": "product",

            "name": "Brokerage Expense",

            "quantity": 1.0,

            "price_unit": brokerage,

            "account_id": account.id,

            # IMPORTANT:
            # Do NOT put broker in partner_id.
            #
            # Vendor bill partner is the supplier.
            # Odoo controls account.move.line.partner_id.

            "tax_ids": [
                Command.clear()
            ],
        }

    # ======================================================
    # WITHHOLDING TAX LINE
    # ======================================================

    def _prepare_withholding_tax_line_vals(
        self,
        pc,
    ):
        """
        Prepare withholding tax invoice line.

        Expected:

            CR Withholding Tax
        """

        withholding = float(
            pc.less_wh_tax_brokerage or 0.0
        )

        # --------------------------------------------------
        # ZERO WITHHOLDING
        # --------------------------------------------------

        if not withholding:

            self._pc_log(
                "WITHHOLDING LINE | "
                "PC=%s | Withholding is zero. "
                "No withholding line.",
                pc.display_name,
            )

            return False

        partner = pc.partner_id

        if not partner:

            raise UserError(
                _(
                    "Payment Certificate %s has no partner "
                    "for withholding tax."
                )
                % pc.display_name
            )

        # --------------------------------------------------
        # WITHHOLDING ACCOUNT
        # --------------------------------------------------

        account = partner.withholding_tax_account

        self._pc_log(
            "WITHHOLDING LOOKUP | "
            "PC=%s | Partner=%s | Partner ID=%s | "
            "Account=%s | Account ID=%s | "
            "Type=%s | Amount=%s",
            pc.display_name,
            partner.display_name,
            partner.id,
            account.display_name if account else False,
            account.id if account else False,
            account.account_type if account else False,
            withholding,
        )

        if not account:

            raise UserError(
                _(
                    "No Withholding Tax Account is configured "
                    "for partner %s."
                )
                % partner.display_name
            )

        return {
            "sequence": 30,

            "display_type": "product",

            "name": "Withholding Tax",

            "quantity": 1.0,

            # Negative invoice line.
            #
            # This creates:
            #
            # CREDIT 4320
            #
            # We do NOT manually specify credit.
            "price_unit": -withholding,

            "account_id": account.id,

            "tax_ids": [
                Command.clear()
            ],
        }

    # ======================================================
    # COMPLETE PAYMENT CERTIFICATE BILL VALUES
    # ======================================================

    def _prepare_pc_bill_vals(
        self,
        pc,
        company=None,
    ):
        """
        Prepare complete vendor bill values.

        IMPORTANT:

        ONLY invoice_line_ids are prepared.

        We DO NOT prepare:

            line_ids
            debit
            credit
            balance
            date_maturity
            payable line
        """

        purchase = self._get_pc_purchase_order(
            pc
        )

        company = (
            company
            or purchase.company_id
            or self.env.company
        )

        # --------------------------------------------------
        # PRODUCT
        # --------------------------------------------------

        product = self._get_pc_product(
            purchase
        )

        # --------------------------------------------------
        # EXPENSE ACCOUNT
        # --------------------------------------------------

        expense_account = (
            self._get_pc_bill_line_account(
                product,
                company=company,
            )
        )

        # --------------------------------------------------
        # HEADER
        # --------------------------------------------------

        header_vals = (
            self._prepare_pc_bill_header_vals(
                pc,
                company=company,
            )
        )

        # --------------------------------------------------
        # RICE LINE
        # --------------------------------------------------

        rice_line = (
            self._prepare_pc_rice_line_vals(
                pc,
                purchase,
                product,
                expense_account,
            )
        )

        # --------------------------------------------------
        # BROKERAGE LINE
        # --------------------------------------------------

        brokerage_line = (
            self._prepare_brokerage_line_vals(
                pc
            )
        )

        # --------------------------------------------------
        # WITHHOLDING LINE
        # --------------------------------------------------

        withholding_line = (
            self._prepare_withholding_tax_line_vals(
                pc
            )
        )

        # --------------------------------------------------
        # INVOICE LINES
        #
        # ONLY THESE.
        #
        # NO line_ids.
        # --------------------------------------------------

        invoice_lines = [
            Command.clear(),

            Command.create(
                rice_line
            ),
        ]

        if brokerage_line:

            invoice_lines.append(
                Command.create(
                    brokerage_line
                )
            )

        if withholding_line:

            invoice_lines.append(
                Command.create(
                    withholding_line
                )
            )

        header_vals[
            "invoice_line_ids"
        ] = invoice_lines

        # --------------------------------------------------
        # EXPECTED ACCOUNTING LOG
        # --------------------------------------------------

        amount = float(
            pc.amount or 0.0
        )

        brokerage = float(
            pc.add_brokerage or 0.0
        )

        withholding = float(
            pc.less_wh_tax_brokerage or 0.0
        )

        payable = (
            amount
            + brokerage
            - withholding
        )

        total_debit = (
            amount
            + brokerage
        )

        total_credit = (
            withholding
            + payable
        )

        self._pc_log(
            "EXPECTED ACCOUNTING | "
            "PC=%s | "
            "Rice DR=%s | "
            "Brokerage DR=%s | "
            "Withholding CR=%s | "
            "Payable CR=%s | "
            "TOTAL DR=%s | TOTAL CR=%s",
            pc.display_name,
            amount,
            brokerage,
            withholding,
            payable,
            total_debit,
            total_credit,
        )

        self._pc_log(
            "PREPARED BILL VALUES | "
            "PC=%s | Invoice Lines=%s | "
            "NO MANUAL JOURNAL LINES",
            pc.display_name,
            len(invoice_lines) - 1,
        )

        return header_vals

    # ======================================================
    # REFRESH DYNAMIC LINES
    # ======================================================

    def _pc_refresh_dynamic_lines_for_onchange(self):
        """
        Refresh Odoo dynamic journal lines during onchange.

        We NEVER manually construct line_ids.
        """

        self.ensure_one()

        self._pc_log(
            "DYNAMIC REFRESH START | "
            "Move ID=%s | PC=%s",
            self.id or "New",
            (
                self.payment_certificate_id.display_name
                if self.payment_certificate_id
                else False
            ),
        )

        # --------------------------------------------------
        # METHOD 1
        # --------------------------------------------------

        onchange_invoice_lines = getattr(
            self,
            "_onchange_invoice_line_ids",
            None,
        )

        if onchange_invoice_lines:

            self._pc_log(
                "DYNAMIC REFRESH | "
                "Calling _onchange_invoice_line_ids()"
            )

            onchange_invoice_lines()

            self._pc_log(
                "DYNAMIC REFRESH | "
                "_onchange_invoice_line_ids() completed"
            )

            return

        # --------------------------------------------------
        # METHOD 2
        # --------------------------------------------------

        recompute_dynamic = getattr(
            self,
            "_onchange_recompute_dynamic_lines",
            None,
        )

        if recompute_dynamic:

            self._pc_log(
                "DYNAMIC REFRESH | "
                "Calling _onchange_recompute_dynamic_lines()"
            )

            recompute_dynamic()

            self._pc_log(
                "DYNAMIC REFRESH | "
                "_onchange_recompute_dynamic_lines() completed"
            )

            return

        # --------------------------------------------------
        # FALLBACK
        # --------------------------------------------------

        self._pc_log(
            "DYNAMIC REFRESH | "
            "No compatible onchange method found. "
            "Core create/write will generate journal lines."
        )

    # ======================================================
    # DEBUG ACCOUNTING
    # ======================================================

    def _pc_debug_accounting(self):

        for move in self:

            self._pc_log(
                "=================================================="
            )

            self._pc_log(
                "ACCOUNTING DEBUG START | "
                "Move=%s | ID=%s | State=%s | "
                "Move Type=%s | PC=%s",
                move.display_name,
                move.id,
                move.state,
                move.move_type,
                (
                    move.payment_certificate_id.display_name
                    if move.payment_certificate_id
                    else False
                ),
            )

            # --------------------------------------------------
            # HEADER
            # --------------------------------------------------

            self._pc_log(
                "MOVE HEADER | "
                "Partner=%s | Partner ID=%s | "
                "PO=%s | PO ID=%s | "
                "PC Amount=%s | Brokerage=%s | "
                "Withholding=%s | Net Payable=%s",
                (
                    move.partner_id.display_name
                    if move.partner_id
                    else False
                ),
                (
                    move.partner_id.id
                    if move.partner_id
                    else False
                ),
                (
                    move.purchase_order_id.name
                    if move.purchase_order_id
                    else False
                ),
                (
                    move.purchase_order_id.id
                    if move.purchase_order_id
                    else False
                ),
                move.rice_pc_amount,
                move.brokerage_charges,
                move.withholding_tax_amount,
                move.pc_total_payable,
            )

            # --------------------------------------------------
            # INVOICE LINES
            # --------------------------------------------------

            self._pc_log(
                "INVOICE LINES COUNT=%s",
                len(move.invoice_line_ids),
            )

            for index, line in enumerate(
                move.invoice_line_ids,
                start=1,
            ):

                self._pc_log(
                    "INVOICE LINE %s | "
                    "ID=%s | Product=%s | "
                    "Name=%s | Quantity=%s | "
                    "Price Unit=%s | "
                    "Subtotal=%s | "
                    "Account=%s | Account ID=%s | "
                    "Account Type=%s",
                    index,
                    line.id,
                    (
                        line.product_id.display_name
                        if line.product_id
                        else False
                    ),
                    line.name,
                    line.quantity,
                    line.price_unit,
                    line.price_subtotal,
                    (
                        line.account_id.display_name
                        if line.account_id
                        else False
                    ),
                    (
                        line.account_id.id
                        if line.account_id
                        else False
                    ),
                    (
                        line.account_id.account_type
                        if line.account_id
                        else False
                    ),
                )

            # --------------------------------------------------
            # JOURNAL LINES
            # --------------------------------------------------

            self._pc_log(
                "JOURNAL LINES COUNT=%s",
                len(move.line_ids),
            )

            total_debit = 0.0
            total_credit = 0.0

            for index, line in enumerate(
                move.line_ids,
                start=1,
            ):

                debit = float(
                    line.debit or 0.0
                )

                credit = float(
                    line.credit or 0.0
                )

                balance = float(
                    line.balance or 0.0
                )

                total_debit += debit
                total_credit += credit

                self._pc_log(
                    "JOURNAL LINE %s | "
                    "ID=%s | Name=%s | "
                    "Account=%s | Account ID=%s | "
                    "Type=%s | "
                    "Debit=%s | Credit=%s | "
                    "Balance=%s | "
                    "Partner=%s | Partner ID=%s | "
                    "Maturity=%s",
                    index,
                    line.id,
                    line.name,
                    (
                        line.account_id.display_name
                        if line.account_id
                        else False
                    ),
                    (
                        line.account_id.id
                        if line.account_id
                        else False
                    ),
                    (
                        line.account_id.account_type
                        if line.account_id
                        else False
                    ),
                    debit,
                    credit,
                    balance,
                    (
                        line.partner_id.display_name
                        if line.partner_id
                        else False
                    ),
                    (
                        line.partner_id.id
                        if line.partner_id
                        else False
                    ),
                    line.date_maturity,
                )

            # --------------------------------------------------
            # PAYABLE LINES
            # --------------------------------------------------

            payable_lines = move.line_ids.filtered(
                lambda line:
                    line.account_id
                    and line.account_id.account_type
                    == "liability_payable"
            )

            self._pc_log(
                "PAYABLE LINES COUNT=%s",
                len(payable_lines),
            )

            for line in payable_lines:

                self._pc_log(
                    "PAYABLE LINE | "
                    "ID=%s | Account=%s | "
                    "Account ID=%s | Debit=%s | "
                    "Credit=%s | Balance=%s | "
                    "Maturity=%s | Partner=%s",
                    line.id,
                    line.account_id.display_name,
                    line.account_id.id,
                    line.debit,
                    line.credit,
                    line.balance,
                    line.date_maturity,
                    (
                        line.partner_id.display_name
                        if line.partner_id
                        else False
                    ),
                )

            # --------------------------------------------------
            # TOTALS
            # --------------------------------------------------

            self._pc_log(
                "ACTUAL TOTALS | "
                "Move=%s | Debit=%s | Credit=%s | "
                "Difference=%s",
                move.display_name,
                total_debit,
                total_credit,
                total_debit - total_credit,
            )

            # --------------------------------------------------
            # EXPECTED TOTALS
            # --------------------------------------------------

            expected_rice = float(
                move.rice_pc_amount or 0.0
            )

            expected_brokerage = float(
                move.brokerage_charges or 0.0
            )

            expected_withholding = float(
                move.withholding_tax_amount or 0.0
            )

            expected_payable = (
                expected_rice
                + expected_brokerage
                - expected_withholding
            )

            expected_debit = (
                expected_rice
                + expected_brokerage
            )

            expected_credit = (
                expected_withholding
                + expected_payable
            )

            self._pc_log(
                "EXPECTED TOTALS | "
                "Rice DR=%s | Brokerage DR=%s | "
                "Withholding CR=%s | Payable CR=%s | "
                "Expected DR=%s | Expected CR=%s | "
                "Difference=%s",
                expected_rice,
                expected_brokerage,
                expected_withholding,
                expected_payable,
                expected_debit,
                expected_credit,
                expected_debit - expected_credit,
            )

            # --------------------------------------------------
            # FINAL STATUS
            # --------------------------------------------------

            if abs(
                total_debit - total_credit
            ) < 0.01:

                self._pc_log(
                    "ACCOUNTING STATUS | "
                    "BALANCED"
                )

            else:

                self._pc_log(
                    "ACCOUNTING STATUS | "
                    "NOT BALANCED"
                )

            self._pc_log(
                "ACCOUNTING DEBUG END"
            )

            self._pc_log(
                "=================================================="
            )

    @api.onchange("payment_certificate_id")
    def _onchange_payment_certificate_id(self):

        for move in self:

            if move.move_type != VENDOR_BILL_MOVE_TYPE:
                continue

            pc = move.payment_certificate_id

            move._pc_log(
                "ONCHANGE START | "
                "Move=%s | PC=%s | PC ID=%s",
                move.display_name,
                pc.display_name if pc else False,
                pc.id if pc else False,
            )

            # ==================================================
            # CLEAR
            # ==================================================

            if not pc:
                move.update({
                    "purchase_order_id": False,
                    "broker_id": False,

                    "rice_pc_amount": 0.0,
                    "brokerage_charges": 0.0,
                    "withholding_tax_amount": 0.0,
                    "pc_net_weight": 0.0,
                    "pc_rate": 0.0,
                    "pc_total_payable": 0.0,

                    "invoice_line_ids": [
                        Command.clear()
                    ],
                })

                move._pc_log(
                    "ONCHANGE CLEAR COMPLETE | "
                    "Invoice Lines=%s",
                    len(move.invoice_line_ids),
                )

                continue

            # ==================================================
            # PREPARE
            # ==================================================

            bill_vals = (
                move._prepare_pc_bill_vals(
                    pc,
                    company=(
                            move.company_id
                            or move.env.company
                    ),
                )
            )

            # ==================================================
            # CRITICAL PROTECTION
            #
            # Never allow standard purchase_id during
            # Payment Certificate onchange.
            # ==================================================

            bill_vals.pop(
                "purchase_id",
                None,
            )

            # ==================================================
            # Never manually manipulate journal lines.
            # ==================================================

            bill_vals.pop(
                "line_ids",
                None,
            )

            move._pc_log(
                "ONCHANGE BEFORE UPDATE | "
                "purchase_id=%s | "
                "purchase_order_id=%s | "
                "invoice_line_commands=%s",
                bill_vals.get(
                    "purchase_id"
                ),
                bill_vals.get(
                    "purchase_order_id"
                ),
                len(
                    bill_vals.get(
                        "invoice_line_ids",
                        []
                    )
                ),
            )

            # ==================================================
            # SINGLE UPDATE
            # ==================================================

            move.update(
                bill_vals
            )

            # ==================================================
            # RESULT
            # ==================================================

            move._pc_log(
                "ONCHANGE AFTER UPDATE | "
                "standard_purchase_id=%s | "
                "custom_purchase_order_id=%s | "
                "Invoice Lines=%s | "
                "Journal Lines=%s",
                (
                    move.purchase_id.display_name
                    if move.purchase_id
                    else False
                ),
                (
                    move.purchase_order_id.display_name
                    if move.purchase_order_id
                    else False
                ),
                len(
                    move.invoice_line_ids
                ),
                len(
                    move.line_ids
                ),
            )

            move._pc_debug_accounting()

    # ======================================================
    # CREATE
    # ======================================================

    # ======================================================
    # CREATE
    # ======================================================

    @api.model_create_multi
    def create(self, vals_list):

        prepared_vals_list = []

        for original_vals in vals_list:

            vals = dict(
                original_vals
            )

            move_type = (
                    vals.get("move_type")
                    or self.env.context.get(
                "default_move_type"
            )
            )

            payment_certificate_id = (
                vals.get(
                    "payment_certificate_id"
                )
            )

            self._pc_log(
                "CREATE START | "
                "Move Type=%s | PC ID=%s",
                move_type,
                payment_certificate_id,
            )

            # ==================================================
            # PAYMENT CERTIFICATE VENDOR BILL
            # ==================================================

            if (
                    move_type
                    == VENDOR_BILL_MOVE_TYPE
                    and payment_certificate_id
            ):

                pc = self.env[
                    "payment.certificate"
                ].browse(
                    payment_certificate_id
                ).exists()

                if not pc:
                    raise UserError(
                        _(
                            "Payment Certificate ID %s "
                            "could not be found."
                        )
                        % payment_certificate_id
                    )

                self._pc_log(
                    "CREATE | Preparing bill from PC | "
                    "PC=%s | ID=%s",
                    pc.display_name,
                    pc.id,
                )

                # --------------------------------------------------
                # COMPANY
                # --------------------------------------------------

                company = (
                    self.env.company
                )

                if vals.get(
                        "company_id"
                ):
                    company = self.env[
                        "res.company"
                    ].browse(
                        vals[
                            "company_id"
                        ]
                    )

                # --------------------------------------------------
                # PREPARE BILL FROM PAYMENT CERTIFICATE
                # --------------------------------------------------

                prepared = (
                    self._prepare_pc_bill_vals(
                        pc,
                        company=company,
                    )
                )

                # --------------------------------------------------
                # HEADER
                # --------------------------------------------------

                vals[
                    "partner_id"
                ] = prepared[
                    "partner_id"
                ]

                vals[
                    "purchase_order_id"
                ] = prepared[
                    "purchase_order_id"
                ]

                vals[
                    "broker_id"
                ] = prepared.get(
                    "broker_id"
                )

                vals[
                    "payment_certificate_id"
                ] = prepared[
                    "payment_certificate_id"
                ]

                vals[
                    "rice_pc_amount"
                ] = prepared[
                    "rice_pc_amount"
                ]

                vals[
                    "brokerage_charges"
                ] = prepared[
                    "brokerage_charges"
                ]

                vals[
                    "withholding_tax_amount"
                ] = prepared[
                    "withholding_tax_amount"
                ]

                vals[
                    "pc_net_weight"
                ] = prepared[
                    "pc_net_weight"
                ]

                vals[
                    "pc_rate"
                ] = prepared[
                    "pc_rate"
                ]

                vals[
                    "pc_total_payable"
                ] = prepared[
                    "pc_total_payable"
                ]

                vals[
                    "ref"
                ] = prepared[
                    "ref"
                ]

                vals[
                    "payment_reference"
                ] = prepared[
                    "payment_reference"
                ]

                vals[
                    "invoice_origin"
                ] = prepared[
                    "invoice_origin"
                ]

                vals[
                    "invoice_date"
                ] = prepared[
                    "invoice_date"
                ]

                # --------------------------------------------------
                # STANDARD PURCHASE LINK
                # --------------------------------------------------

                if (
                        "purchase_id"
                        in self.env[
                    "account.move"
                ]._fields
                ):
                    vals[
                        "purchase_id"
                    ] = pc.purchase_id.id

                # --------------------------------------------------
                # PAYMENT TERM
                # --------------------------------------------------

                if prepared.get(
                        "invoice_payment_term_id"
                ):
                    vals[
                        "invoice_payment_term_id"
                    ] = prepared[
                        "invoice_payment_term_id"
                    ]

                # --------------------------------------------------
                # IMPORTANT:
                #
                # ONLY invoice_line_ids.
                #
                # NEVER line_ids.
                # NEVER debit.
                # NEVER credit.
                # NEVER balance.
                # NEVER date_maturity.
                # --------------------------------------------------

                vals[
                    "invoice_line_ids"
                ] = prepared[
                    "invoice_line_ids"
                ]

                # --------------------------------------------------
                # REMOVE OLD MANUAL JOURNAL LINES
                # --------------------------------------------------

                vals.pop(
                    "line_ids",
                    None,
                )

                self._pc_log(
                    "CREATE | FINAL VALUES | "
                    "PC=%s | "
                    "Invoice Lines=%s | "
                    "Manual line_ids removed",
                    pc.display_name,
                    len(
                        prepared[
                            "invoice_line_ids"
                        ]
                    ) - 1,
                )

            prepared_vals_list.append(
                vals
            )

        # ======================================================
        # CORE ODOO CREATE
        # ======================================================

        moves = super().create(
            prepared_vals_list
        )

        # ======================================================
        # AFTER CREATE
        #
        # IMPORTANT:
        # PC FLOW IS NOT TOUCHED HERE.
        #
        # Normal vendor bills only:
        #   - No Payment Certificate
        #   - Vendor Bill
        #   - Draft
        #
        # These will get normal WHT / Income Tax lines.
        # ======================================================

        for move in moves:

            # ==================================================
            # PAYMENT CERTIFICATE BILL
            #
            # EXISTING FLOW - UNTOUCHED
            # ==================================================

            if (
                    move.payment_certificate_id
            ):
                move._pc_log(
                    "CREATE COMPLETE | "
                    "PC BILL | "
                    "Move=%s | ID=%s | "
                    "PC=%s | "
                    "Invoice Lines=%s | "
                    "Journal Lines=%s",
                    move.name,
                    move.id,
                    move.payment_certificate_id.display_name,
                    len(
                        move.invoice_line_ids
                    ),
                    len(
                        move.line_ids
                    ),
                )

                move._pc_debug_accounting()

                # IMPORTANT:
                # Do NOT run normal tax sync on PC bills.
                continue

            # ==================================================
            # NORMAL VENDOR BILL
            # ==================================================

            if (
                    move.move_type
                    == VENDOR_BILL_MOVE_TYPE
                    and not move.payment_certificate_id
            ):

                move._pc_log(
                    "NORMAL BILL CREATE COMPLETE | "
                    "Move=%s | ID=%s | "
                    "Partner=%s | "
                    "Invoice Lines=%s | "
                    "Journal Lines=%s",
                    move.name,
                    move.id,
                    move.partner_id.display_name
                    if move.partner_id
                    else False,
                    len(
                        move.invoice_line_ids
                    ),
                    len(
                        move.line_ids
                    ),
                )

                # --------------------------------------------------
                # SHOW CALCULATED VALUES BEFORE LINE CREATION
                # --------------------------------------------------

                move._pc_log(
                    "NORMAL TAX BEFORE SYNC | "
                    "Move=%s | "
                    "Tax Base=%s | "
                    "WHT Rate=%s%% | "
                    "WHT Amount=%s | "
                    "Income Rate=%s%% | "
                    "Income Amount=%s",
                    move.display_name,
                    move.normal_tax_base_amount,
                    move.normal_withholding_tax_rate,
                    move.normal_withholding_tax_amount,
                    move.normal_income_tax_rate,
                    move.normal_income_tax_amount,
                )

                # --------------------------------------------------
                # CREATE NORMAL TAX LINES
                # --------------------------------------------------

                if not self.env.context.get(
                        "skip_normal_vendor_tax_sync"
                ):

                    move._pc_log(
                        "NORMAL TAX SYNC CALL | "
                        "Move=%s | "
                        "ID=%s",
                        move.display_name,
                        move.id,
                    )

                    move._sync_normal_vendor_tax_lines()

                    move._pc_log(
                        "NORMAL TAX SYNC RETURNED | "
                        "Move=%s | "
                        "Invoice Lines=%s | "
                        "Journal Lines=%s",
                        move.display_name,
                        len(
                            move.invoice_line_ids
                        ),
                        len(
                            move.line_ids
                        ),
                    )

                else:

                    move._pc_log(
                        "NORMAL TAX SYNC SKIPPED BY CONTEXT | "
                        "Move=%s",
                        move.display_name,
                    )

        # ======================================================
        # FINAL RETURN
        # ======================================================

        return moves

    # ======================================================
    # PREPARE WRITE VALUES
    # ======================================================

    def _pc_prepare_write_vals(
        self,
        vals,
    ):
        """
        Prepare write values when Payment Certificate
        changes on an existing draft vendor bill.
        """

        self.ensure_one()

        new_vals = dict(
            vals
        )

        # --------------------------------------------------
        # NOT VENDOR BILL
        # --------------------------------------------------

        if (
            self.move_type
            != VENDOR_BILL_MOVE_TYPE
        ):

            return new_vals

        # --------------------------------------------------
        # ONLY DRAFT
        # --------------------------------------------------

        if (
            self.state
            != DRAFT_STATE
        ):

            return new_vals

        # --------------------------------------------------
        # PC NOT CHANGED
        # --------------------------------------------------

        if (
            "payment_certificate_id"
            not in vals
        ):

            return new_vals

        payment_certificate_id = (
            vals.get(
                "payment_certificate_id"
            )
        )

        # ==================================================
        # CLEAR PC
        # ==================================================

        if not payment_certificate_id:

            new_vals.update({
                "purchase_order_id": False,

                "broker_id": False,

                "rice_pc_amount": 0.0,

                "brokerage_charges": 0.0,

                "withholding_tax_amount": 0.0,

                "pc_net_weight": 0.0,

                "pc_rate": 0.0,

                "invoice_line_ids": [
                    Command.clear()
                ],
            })

            # IMPORTANT:
            #
            # Never write line_ids.
            new_vals.pop(
                "line_ids",
                None,
            )

            return new_vals

        # ==================================================
        # GET NEW PC
        # ==================================================

        pc = self.env[
            "payment.certificate"
        ].browse(
            payment_certificate_id
        ).exists()

        if not pc:

            raise UserError(
                _(
                    "Payment Certificate ID %s "
                    "could not be found."
                )
                % payment_certificate_id
            )

        self._pc_log(
            "WRITE | Changing PC | "
            "Move=%s | Move ID=%s | "
            "PC=%s | PC ID=%s",
            self.display_name,
            self.id,
            pc.display_name,
            pc.id,
        )

        # ==================================================
        # PREPARE
        # ==================================================

        prepared = (
            self._prepare_pc_bill_vals(
                pc,
                company=(
                    self.company_id
                    or self.env.company
                ),
            )
        )

        # ==================================================
        # HEADER
        # ==================================================

        new_vals[
            "partner_id"
        ] = prepared[
            "partner_id"
        ]

        new_vals[
            "purchase_order_id"
        ] = prepared[
            "purchase_order_id"
        ]

        new_vals[
            "broker_id"
        ] = prepared.get(
            "broker_id"
        )

        new_vals[
            "rice_pc_amount"
        ] = prepared[
            "rice_pc_amount"
        ]

        new_vals[
            "brokerage_charges"
        ] = prepared[
            "brokerage_charges"
        ]

        new_vals[
            "withholding_tax_amount"
        ] = prepared[
            "withholding_tax_amount"
        ]

        new_vals[
            "pc_net_weight"
        ] = prepared[
            "pc_net_weight"
        ]

        new_vals[
            "pc_rate"
        ] = prepared[
            "pc_rate"
        ]

        new_vals[
            "pc_total_payable"
        ] = prepared[
            "pc_total_payable"
        ]

        new_vals[
            "ref"
        ] = prepared[
            "ref"
        ]

        new_vals[
            "payment_reference"
        ] = prepared[
            "payment_reference"
        ]

        new_vals[
            "invoice_origin"
        ] = prepared[
            "invoice_origin"
        ]

        # ==================================================
        # INVOICE LINES ONLY
        # ==================================================

        new_vals[
            "invoice_line_ids"
        ] = prepared[
            "invoice_line_ids"
        ]

        # ==================================================
        # PAYMENT TERM
        # ==================================================

        if prepared.get(
            "invoice_payment_term_id"
        ):

            new_vals[
                "invoice_payment_term_id"
            ] = prepared[
                "invoice_payment_term_id"
            ]

        # ==================================================
        # REMOVE MANUAL JOURNAL LINES
        # ==================================================

        new_vals.pop(
            "line_ids",
            None,
        )

        return new_vals

    # ======================================================
    # WRITE
    # ======================================================

    # ======================================================
    # WRITE
    # ======================================================

    def write(
            self,
            vals,
    ):

        # ==================================================
        # EMPTY WRITE
        # ==================================================

        if not vals:
            return super().write(vals)

        # ==================================================
        # NORMAL WRITE
        #
        # If this is an internal tax-line sync, do not
        # trigger the tax sync again.
        # ==================================================

        if self.env.context.get(
                "skip_normal_vendor_tax_sync"
        ):
            return super().write(vals)

        # ==================================================
        # HANDLE EACH MOVE SEPARATELY
        # ==================================================

        result = True

        for move in self:

            # ==================================================
            # SAVE WHETHER THIS WAS A PC BILL BEFORE WRITE
            # ==================================================

            old_payment_certificate = (
                move.payment_certificate_id
            )

            old_is_pc_bill = bool(
                old_payment_certificate
                and move.move_type
                == VENDOR_BILL_MOVE_TYPE
            )

            # ==================================================
            # PAYMENT CERTIFICATE CHANGE
            #
            # EXISTING PC FLOW
            # ==================================================

            if (
                    "payment_certificate_id"
                    in vals
            ):

                move_vals = (
                    move._pc_prepare_write_vals(
                        vals
                    )
                )

                result = (
                        super(
                            AccountMove,
                            move,
                        ).write(
                            move_vals
                        )
                        and result
                )

                # --------------------------------------------------
                # PC BILL AFTER WRITE
                # --------------------------------------------------

                if (
                        move.payment_certificate_id
                        and move.move_type
                        == VENDOR_BILL_MOVE_TYPE
                ):
                    move._pc_log(
                        "WRITE COMPLETE | "
                        "PC BILL | "
                        "Move=%s | ID=%s | "
                        "PC=%s | "
                        "Invoice Lines=%s | "
                        "Journal Lines=%s",
                        move.name,
                        move.id,
                        move.payment_certificate_id.display_name,
                        len(
                            move.invoice_line_ids
                        ),
                        len(
                            move.line_ids
                        ),
                    )

                    move._pc_debug_accounting()

                    # IMPORTANT:
                    # Never run normal tax sync on PC bills.
                    continue

                # --------------------------------------------------
                # PC WAS CLEARED
                #
                # Now this is a normal vendor bill.
                # --------------------------------------------------

                if (
                        move.move_type
                        == VENDOR_BILL_MOVE_TYPE
                        and not move.payment_certificate_id
                        and move.state == DRAFT_STATE
                ):
                    move._pc_log(
                        "PC CLEARED | "
                        "NORMAL TAX SYNC REQUIRED | "
                        "Move=%s | ID=%s",
                        move.display_name,
                        move.id,
                    )

                    move._sync_normal_vendor_tax_lines()

                continue

            # ==================================================
            # NORMAL WRITE
            #
            # This handles:
            #
            # - partner change
            # - invoice line change
            # - tax rate change
            # - amount change
            # - account change
            # - etc.
            #
            # PC BILL IS NOT TOUCHED BY NORMAL TAX SYNC.
            # ==================================================

            result = (
                    super(
                        AccountMove,
                        move,
                    ).write(vals)
                    and result
            )

            # ==================================================
            # NORMAL VENDOR BILL
            # ==================================================

            if (
                    move.move_type
                    == VENDOR_BILL_MOVE_TYPE
                    and not move.payment_certificate_id
                    and move.state == DRAFT_STATE
            ):

                # --------------------------------------------------
                # ONLY SYNC WHEN RELEVANT VALUES CHANGED
                # --------------------------------------------------

                tax_sync_fields = {
                    "partner_id",
                    "invoice_line_ids",
                    "normal_withholding_tax_rate",
                    "normal_income_tax_rate",
                    "currency_id",
                    "move_type",
                }

                should_sync_tax = bool(
                    tax_sync_fields.intersection(
                        vals.keys()
                    )
                )

                # --------------------------------------------------
                # If any relevant field changed, sync tax lines.
                # --------------------------------------------------

                if should_sync_tax:

                    move._pc_log(
                        "NORMAL BILL WRITE | "
                        "TAX SYNC REQUIRED | "
                        "Move=%s | ID=%s | "
                        "Changed Fields=%s",
                        move.display_name,
                        move.id,
                        list(
                            vals.keys()
                        ),
                    )

                    move._pc_log(
                        "NORMAL TAX BEFORE WRITE SYNC | "
                        "Move=%s | "
                        "Tax Base=%s | "
                        "WHT Rate=%s%% | "
                        "WHT Amount=%s | "
                        "Income Rate=%s%% | "
                        "Income Amount=%s",
                        move.display_name,
                        move.normal_tax_base_amount,
                        move.normal_withholding_tax_rate,
                        move.normal_withholding_tax_amount,
                        move.normal_income_tax_rate,
                        move.normal_income_tax_amount,
                    )

                    move._sync_normal_vendor_tax_lines()

                    move._pc_log(
                        "NORMAL BILL WRITE | "
                        "TAX SYNC COMPLETE | "
                        "Move=%s | "
                        "Invoice Lines=%s | "
                        "Journal Lines=%s",
                        move.display_name,
                        len(
                            move.invoice_line_ids
                        ),
                        len(
                            move.line_ids
                        ),
                    )

                else:

                    move._pc_log(
                        "NORMAL BILL WRITE | "
                        "TAX SYNC NOT REQUIRED | "
                        "Move=%s | "
                        "Changed Fields=%s",
                        move.display_name,
                        list(
                            vals.keys()
                        ),
                    )

            # ==================================================
            # PC BILL SAFETY CHECK
            # ==================================================

            elif old_is_pc_bill:

                move._pc_log(
                    "PC BILL WRITE | "
                    "NORMAL TAX SYNC NOT RUN | "
                    "Move=%s | "
                    "PC=%s",
                    move.display_name,
                    old_payment_certificate.display_name,
                )

        return result

    # ==========================================================
    # NORMAL WITHHOLDING TAX LINE
    # ==========================================================

    def _prepare_normal_withholding_tax_line_vals(self):

        self.ensure_one()

        # --------------------------------------------------
        # ONLY NORMAL VENDOR BILL
        # --------------------------------------------------

        if self.move_type != VENDOR_BILL_MOVE_TYPE:
            return False

        # --------------------------------------------------
        # PC BILL MUST NOT USE THIS
        # --------------------------------------------------

        if self.payment_certificate_id:
            return False

        amount = float(
            self.normal_withholding_tax_amount or 0.0
        )

        if not amount:
            self._pc_log(
                "NORMAL WHT LINE | "
                "Move=%s | Amount is zero",
                self.display_name,
            )
            return False

        partner = self.partner_id

        if not partner:
            raise UserError(
                _("Vendor is required for Withholding Tax.")
            )

        account = partner.withholding_tax_account

        self._pc_log(
            "NORMAL WHT ACCOUNT | "
            "Move=%s | "
            "Partner=%s | Partner ID=%s | "
            "Account=%s | Account ID=%s | "
            "Type=%s | Amount=%s",
            self.display_name,
            partner.display_name,
            partner.id,
            account.display_name if account else False,
            account.id if account else False,
            account.account_type if account else False,
            amount,
        )

        if not account:
            raise UserError(
                _(
                    "No Withholding Tax Account is configured "
                    "for vendor %s."
                )
                % partner.display_name
            )

        return {
            "name": "Withholding Tax",
            "quantity": 1.0,

            # Negative invoice line
            # Odoo will convert this into CREDIT.
            "price_unit": -amount,

            "account_id": account.id,

            "tax_ids": [
                Command.clear()
            ],

            "is_normal_withholding_tax_line": True,
        }

    # ==========================================================
    # NORMAL WITHHOLDING TAX LINE
    # ==========================================================

    def _prepare_normal_withholding_tax_line_vals(self):

        self.ensure_one()

        # --------------------------------------------------
        # ONLY NORMAL VENDOR BILL
        # --------------------------------------------------

        if self.move_type != VENDOR_BILL_MOVE_TYPE:
            return False

        # --------------------------------------------------
        # PC BILL MUST NOT USE THIS
        # --------------------------------------------------

        if self.payment_certificate_id:
            return False

        amount = float(
            self.normal_withholding_tax_amount or 0.0
        )

        if not amount:
            self._pc_log(
                "NORMAL WHT LINE | "
                "Move=%s | Amount is zero",
                self.display_name,
            )
            return False

        partner = self.partner_id

        if not partner:
            raise UserError(
                _("Vendor is required for Withholding Tax.")
            )

        account = partner.withholding_tax_account

        self._pc_log(
            "NORMAL WHT ACCOUNT | "
            "Move=%s | "
            "Partner=%s | Partner ID=%s | "
            "Account=%s | Account ID=%s | "
            "Type=%s | Amount=%s",
            self.display_name,
            partner.display_name,
            partner.id,
            account.display_name if account else False,
            account.id if account else False,
            account.account_type if account else False,
            amount,
        )

        if not account:
            raise UserError(
                _(
                    "No Withholding Tax Account is configured "
                    "for vendor %s."
                )
                % partner.display_name
            )

        return {
            "name": "Withholding Tax",
            "quantity": 1.0,

            # Negative invoice line
            # Odoo will convert this into CREDIT.
            "price_unit": -amount,

            "account_id": account.id,

            "tax_ids": [
                Command.clear()
            ],

            "is_normal_withholding_tax_line": True,
        }

    # ==========================================================
    # NORMAL WITHHOLDING TAX LINE
    # ==========================================================

    def _prepare_normal_withholding_tax_line_vals(self):

        self.ensure_one()

        # --------------------------------------------------
        # ONLY NORMAL VENDOR BILL
        # --------------------------------------------------

        if self.move_type != VENDOR_BILL_MOVE_TYPE:
            return False

        # --------------------------------------------------
        # PC BILL MUST NOT USE THIS
        # --------------------------------------------------

        if self.payment_certificate_id:
            return False

        amount = float(
            self.normal_withholding_tax_amount or 0.0
        )

        if not amount:
            self._pc_log(
                "NORMAL WHT LINE | "
                "Move=%s | Amount is zero",
                self.display_name,
            )
            return False

        partner = self.partner_id

        if not partner:
            raise UserError(
                _("Vendor is required for Withholding Tax.")
            )

        account = partner.withholding_tax_account

        self._pc_log(
            "NORMAL WHT ACCOUNT | "
            "Move=%s | "
            "Partner=%s | Partner ID=%s | "
            "Account=%s | Account ID=%s | "
            "Type=%s | Amount=%s",
            self.display_name,
            partner.display_name,
            partner.id,
            account.display_name if account else False,
            account.id if account else False,
            account.account_type if account else False,
            amount,
        )

        if not account:
            raise UserError(
                _(
                    "No Withholding Tax Account is configured "
                    "for vendor %s."
                )
                % partner.display_name
            )

        return {
            "name": "Withholding Tax",
            "quantity": 1.0,

            # Negative invoice line
            # Odoo will convert this into CREDIT.
            "price_unit": -amount,

            "account_id": account.id,

            "tax_ids": [
                Command.clear()
            ],

            "is_normal_withholding_tax_line": True,
        }

    # ==========================================================
    # SYNC NORMAL VENDOR TAX LINES
    # ==========================================================
    # ======================================================
    # PREPARE NORMAL WITHHOLDING TAX LINE
    # ======================================================

    def _prepare_normal_withholding_tax_line_vals(self):

        self.ensure_one()

        # --------------------------------------------------
        # SAFETY
        # --------------------------------------------------

        if self.move_type != VENDOR_BILL_MOVE_TYPE:
            return False

        if self.payment_certificate_id:
            return False

        amount = float(
            self.normal_withholding_tax_amount
            or 0.0
        )

        if not amount:
            self._pc_log(
                "NORMAL WHT LINE SKIPPED | "
                "Move=%s | Amount=%s",
                self.display_name,
                amount,
            )
            return False

        partner = self.partner_id

        if not partner:
            raise UserError(
                _(
                    "Vendor is required for "
                    "Withholding Tax."
                )
            )

        account = (
            partner.withholding_tax_account
        )

        if not account:
            raise UserError(
                _(
                    "No Withholding Tax Account "
                    "is configured for vendor %s."
                )
                % partner.display_name
            )

        self._pc_log(
            "PREPARE NORMAL WHT LINE | "
            "Move=%s | "
            "Partner=%s | "
            "Account=%s | "
            "Account ID=%s | "
            "Amount=%s",
            self.display_name,
            partner.display_name,
            account.display_name,
            account.id,
            amount,
        )

        return {
            "name": "Withholding Tax",
            "quantity": 1.0,
            "price_unit": -amount,
            "account_id": account.id,
            "tax_ids": [
                Command.clear()
            ],
            "is_normal_withholding_tax_line": True,
        }

    # ======================================================
    # PREPARE NORMAL INCOME TAX LINE
    # ======================================================

    def _prepare_normal_income_tax_line_vals(self):

        self.ensure_one()

        # --------------------------------------------------
        # SAFETY
        # --------------------------------------------------

        if self.move_type != VENDOR_BILL_MOVE_TYPE:
            return False

        if self.payment_certificate_id:
            return False

        amount = float(
            self.normal_income_tax_amount
            or 0.0
        )

        if not amount:
            self._pc_log(
                "NORMAL INCOME TAX LINE SKIPPED | "
                "Move=%s | Amount=%s",
                self.display_name,
                amount,
            )
            return False

        partner = self.partner_id

        if not partner:
            raise UserError(
                _(
                    "Vendor is required for "
                    "Income Tax."
                )
            )

        account = (
            partner.income_tax_account
        )

        if not account:
            raise UserError(
                _(
                    "No Income Tax Account "
                    "is configured for vendor %s."
                )
                % partner.display_name
            )

        self._pc_log(
            "PREPARE NORMAL INCOME TAX LINE | "
            "Move=%s | "
            "Partner=%s | "
            "Account=%s | "
            "Account ID=%s | "
            "Amount=%s",
            self.display_name,
            partner.display_name,
            account.display_name,
            account.id,
            amount,
        )

        return {
            "name": "Income Tax",
            "quantity": 1.0,
            "price_unit": -amount,
            "account_id": account.id,
            "tax_ids": [
                Command.clear()
            ],
            "is_normal_income_tax_line": True,
        }

    def _sync_normal_vendor_tax_lines(self):

        for move in self:

            move._pc_log(
                "NORMAL TAX SYNC START | "
                "Move=%s | ID=%s | "
                "Type=%s | State=%s | PC=%s",
                move.display_name,
                move.id,
                move.move_type,
                move.state,
                (
                    move.payment_certificate_id.display_name
                    if move.payment_certificate_id
                    else False
                ),
            )

            # --------------------------------------------------
            # ONLY VENDOR BILL
            # --------------------------------------------------

            if move.move_type != VENDOR_BILL_MOVE_TYPE:
                move._pc_log(
                    "NORMAL TAX SYNC SKIP | "
                    "Move=%s | Not vendor bill",
                    move.display_name,
                )

                continue

            # --------------------------------------------------
            # PC BILL
            #
            # NEVER TOUCH PC ACCOUNTING.
            # --------------------------------------------------

            if move.payment_certificate_id:
                move._pc_log(
                    "NORMAL TAX SYNC SKIP | "
                    "Move=%s | Payment Certificate exists",
                    move.display_name,
                )

                continue

            # --------------------------------------------------
            # ONLY DRAFT
            # --------------------------------------------------

            if move.state != DRAFT_STATE:
                move._pc_log(
                    "NORMAL TAX SYNC SKIP | "
                    "Move=%s | State=%s",
                    move.display_name,
                    move.state,
                )

                continue

            # --------------------------------------------------
            # REMOVE OLD CUSTOM TAX LINES
            # --------------------------------------------------

            old_tax_lines = move.line_ids.filtered(
                lambda line:
                line.is_normal_withholding_tax_line
                or line.is_normal_income_tax_line
            )

            move._pc_log(
                "NORMAL TAX OLD LINES | "
                "Move=%s | Count=%s",
                move.display_name,
                len(old_tax_lines),
            )

            if old_tax_lines:
                old_tax_lines.unlink()

            # --------------------------------------------------
            # RECOMPUTE TAX AMOUNTS
            # --------------------------------------------------

            move._compute_normal_vendor_tax_amounts()

            # --------------------------------------------------
            # WHT
            # --------------------------------------------------

            withholding_vals = (
                move._prepare_normal_withholding_tax_line_vals()
            )

            # --------------------------------------------------
            # INCOME TAX
            # --------------------------------------------------

            income_tax_vals = (
                move._prepare_normal_income_tax_line_vals()
            )

            # --------------------------------------------------
            # CREATE ACCOUNT MOVE LINES
            # --------------------------------------------------

            line_vals = []

            if withholding_vals:
                line_vals.append(
                    withholding_vals
                )

            if income_tax_vals:
                line_vals.append(
                    income_tax_vals
                )

            if not line_vals:
                move._pc_log(
                    "NORMAL TAX SYNC | "
                    "Move=%s | No tax lines required",
                    move.display_name,
                )

                continue

            # --------------------------------------------------
            # IMPORTANT
            #
            # We are NOT manually setting:
            #
            # debit
            # credit
            # balance
            # date_maturity
            #
            # Odoo will calculate accounting values.
            # --------------------------------------------------

            move.line_ids = [
                Command.create(vals)
                for vals in line_vals
            ]

            move._pc_log(
                "NORMAL TAX SYNC COMPLETE | "
                "Move=%s | Created Lines=%s",
                move.display_name,
                len(line_vals),
            )

# ==========================================================
# ACCOUNT MOVE LINE
# ==========================================================

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_normal_withholding_tax_line = fields.Boolean(
        string="Normal Withholding Tax Line",
        default=False,
        copy=False,
    )

    is_normal_income_tax_line = fields.Boolean(
        string="Normal Income Tax Line",
        default=False,
        copy=False,
    )