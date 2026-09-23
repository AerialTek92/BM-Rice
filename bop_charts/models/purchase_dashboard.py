# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Tuple

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

# --- Dashboard constants (Protocol 1.3: one place to tune the dashboard) ---
CHART_ITEM_LIMIT: int = 10
DOUGHNUT_ITEM_LIMIT: int = 8
KPI_WINDOW_MONTHS: int = 6
MONTHLY_CHART_MONTHS: int = 6
PURCHASED_STATES: Tuple[str, ...] = ("purchase", "done")
RFQ_STATES: Tuple[str, ...] = ("draft", "sent")
ORDER_STATUS_SEQUENCE: Tuple[str, ...] = ("draft", "sent", "purchase", "done", "cancel")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.model
    def get_purchase_dashboard_data(self) -> Dict[str, Any]:
        """Single entry point for the Purchase Dashboard client action.
        Payload is presentation-free: labels, ids and raw numbers only -
        formatting and colors live in the JS layer (Protocol 3.1)."""
        return {
            "currency_symbol": self.env.company.currency_id.symbol or "",
            "kpis": self._get_purchase_kpis(),
            "monthly_amount": self._get_monthly_purchase_amount(),
            "product_stock": self._get_product_closing_balance(),
            "vendor_outstanding": self._get_vendor_outstanding_payment(),
            "top_purchased": self._get_top_purchased_products(),
            "vendor_distribution": self._get_vendor_purchase_distribution(),
            "order_status": self._get_order_status_breakdown(),
        }

    # ==========================================================
    # KPI CARDS (raw numbers; the view formats them)
    # ==========================================================

    @api.model
    def _get_purchase_kpis(self) -> List[Dict[str, Any]]:
        """Protocol 2.1 (SRP): the headline KPI cards, each carrying its
        click-through target (list domain or record id)."""
        today = fields.Date.context_today(self)
        window_start = today - relativedelta(months=KPI_WINDOW_MONTHS)
        previous_start = window_start - relativedelta(months=KPI_WINDOW_MONTHS)

        current_amount = sum(self.search([
            ("date_approve", ">=", window_start),
            ("state", "in", list(PURCHASED_STATES)),
        ]).mapped("amount_total"))
        previous_amount = sum(self.search([
            ("date_approve", ">=", previous_start),
            ("date_approve", "<", window_start),
            ("state", "in", list(PURCHASED_STATES)),
        ]).mapped("amount_total"))

        trend_percent = None
        if previous_amount > 0:
            trend_percent = round((current_amount - previous_amount) / previous_amount * 100)

        top_vendor = self._get_top_vendor(window_start)
        open_order_count = self.search_count([("state", "=", "purchase")])
        rfq_count = self.search_count([("state", "in", list(RFQ_STATES))])

        return [
            {
                "id": "purchase_total",
                "label": _("Purchases (Last %s Months)", KPI_WINDOW_MONTHS),
                "value": current_amount,
                "kind": "money",
                "name": _("Purchases"),
                "icon": "fa-shopping-cart",
                "res_model": "purchase.order",
                "domain": [("date_approve", ">=", window_start), ("state", "in", list(PURCHASED_STATES))],
                "trend": trend_percent,
            },
            {
                "id": "open_orders",
                "label": _("Open Purchase Orders"),
                "value": open_order_count,
                "kind": "count",
                "name": _("Open Purchase Orders"),
                "icon": "fa-truck",
                "res_model": "purchase.order",
                "domain": [("state", "=", "purchase")],
                "trend": None,
            },
            {
                "id": "rfq",
                "label": _("Requests for Quotation"),
                "value": rfq_count,
                "kind": "count",
                "name": _("RFQs"),
                "icon": "fa-file-text-o",
                "res_model": "purchase.order",
                "domain": [("state", "in", list(RFQ_STATES))],
                "trend": None,
            },
            {
                "id": "top_vendor",
                "label": _("Top Vendor: %s", top_vendor["name"] or "-"),
                "value": top_vendor["amount"],
                "kind": "money",
                "name": top_vendor["name"] or _("Vendors"),
                "icon": "fa-trophy",
                "res_model": "res.partner",
                "domain": [],
                "res_id": top_vendor["id"],
                "trend": None,
            },
        ]

    @api.model
    def _get_top_vendor(self, window_start) -> Dict[str, Any]:
        """Protocol 2.1 (SRP): highest-spending vendor in the KPI window."""
        top_vendor_group = self.read_group(
            [("state", "in", list(PURCHASED_STATES)),
             ("date_approve", ">=", window_start),
             ("partner_id", "!=", False)],
            ["partner_id", "amount_total"],
            ["partner_id"],
            limit=1,
            orderby="amount_total desc",
        )
        if not top_vendor_group:
            return {"name": "", "amount": 0.0, "id": False}
        group = top_vendor_group[0]
        return {"name": group["partner_id"][1], "amount": group["amount_total"], "id": group["partner_id"][0]}

    # ==========================================================
    # CHART DATA
    # ==========================================================

    @api.model
    def _get_monthly_purchase_amount(self) -> Dict[str, Any]:
        """FIX (kept): exclusive upper bound - the old inclusive '<= last day'
        compared a Datetime field to a Date at midnight and silently dropped
        every order placed during the final day of each month."""
        month_labels: List[str] = []
        month_totals: List[float] = []
        today = fields.Date.context_today(self)

        for months_back in range(MONTHLY_CHART_MONTHS - 1, -1, -1):
            month_start = (today - relativedelta(months=months_back)).replace(day=1)
            next_month_start = month_start + relativedelta(months=1)

            month_orders = self.search([
                ("date_approve", ">=", month_start),
                ("date_approve", "<", next_month_start),
                ("state", "in", list(PURCHASED_STATES)),
            ])
            month_labels.append(month_start.strftime("%b %Y"))
            month_totals.append(sum(month_orders.mapped("amount_total")))

        return {"labels": month_labels, "totals": month_totals}

    @api.model
    def _get_product_closing_balance(self) -> Dict[str, Any]:
        """read_group over stock.quant (no per-record computes)."""
        stock_groups = self.env["stock.quant"].read_group(
            [("location_id.usage", "=", "internal"), ("quantity", ">", 0)],
            ["product_id", "quantity"],
            ["product_id"],
            limit=CHART_ITEM_LIMIT,
            orderby="quantity desc",
        )
        return {
            "labels": [group["product_id"][1] for group in stock_groups],
            "ids": [group["product_id"][0] for group in stock_groups],
            "totals": [group["quantity"] for group in stock_groups],
        }

    @api.model
    def _get_vendor_outstanding_payment(self) -> Dict[str, Any]:
        """Payable residuals via account.move.line read_group."""
        outstanding_groups = self.env["account.move.line"].read_group(
            [
                ("account_id.account_type", "=", "liability_payable"),
                ("parent_state", "=", "posted"),
                ("partner_id", "!=", False),
                ("company_id", "in", self.env.companies.ids),
            ],
            ["partner_id", "amount_residual"],
            ["partner_id"],
        )
        vendor_residuals = sorted(
            (
                {"id": group["partner_id"][0],
                 "name": group["partner_id"][1],
                 "residual": group["amount_residual"]}
                for group in outstanding_groups
                if group["amount_residual"] > 0
            ),
            key=lambda vendor: vendor["residual"],
            reverse=True,
        )[:CHART_ITEM_LIMIT]
        return {
            "labels": [vendor["name"] for vendor in vendor_residuals],
            "ids": [vendor["id"] for vendor in vendor_residuals],
            "totals": [vendor["residual"] for vendor in vendor_residuals],
        }

    @api.model
    def _get_top_purchased_products(self) -> Dict[str, Any]:
        purchased_groups = self.env["purchase.order.line"].read_group(
            [("state", "in", list(PURCHASED_STATES)), ("product_qty", ">", 0)],
            ["product_id", "product_qty"],
            ["product_id"],
            limit=CHART_ITEM_LIMIT,
            orderby="product_qty desc",
        )
        return {
            "labels": [group["product_id"][1] for group in purchased_groups],
            "ids": [group["product_id"][0] for group in purchased_groups],
            "totals": [group["product_qty"] for group in purchased_groups],
        }

    @api.model
    def _get_vendor_purchase_distribution(self) -> Dict[str, Any]:
        """Doughnut: purchase amount share per vendor, top N + 'Others'."""
        vendor_groups = self.read_group(
            [("state", "in", list(PURCHASED_STATES)), ("partner_id", "!=", False)],
            ["partner_id", "amount_total"],
            ["partner_id"],
            orderby="amount_total desc",
        )
        top_groups = vendor_groups[:DOUGHNUT_ITEM_LIMIT]
        others_total = sum(group["amount_total"] for group in vendor_groups[DOUGHNUT_ITEM_LIMIT:])

        labels = [group["partner_id"][1] for group in top_groups]
        record_ids = [group["partner_id"][0] for group in top_groups]
        totals = [group["amount_total"] for group in top_groups]
        if others_total > 0:
            labels.append(_("Others"))
            record_ids.append(False)
            totals.append(others_total)
        return {"labels": labels, "ids": record_ids, "totals": totals}

    @api.model
    def _get_order_status_breakdown(self) -> Dict[str, Any]:
        """Doughnut: PO count per state; 'states' carried for click-through."""
        state_labels = dict(self._fields["state"]._description_selection(self.env))
        labels: List[str] = []
        states: List[str] = []
        counts: List[int] = []
        for state in ORDER_STATUS_SEQUENCE:
            state_count = self.search_count([("state", "=", state)])
            if state_count:
                labels.append(state_labels.get(state, state))
                states.append(state)
                counts.append(state_count)
        return {"labels": labels, "states": states, "counts": counts}