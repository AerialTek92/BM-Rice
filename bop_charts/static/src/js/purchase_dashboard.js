/** @odoo-module **/

import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";

// --- Chart palettes (one place to re-theme; presentation lives here, not in Python) ---
const LIGHT_PALETTE = [
    "#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
    "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#64748b",
];
const DARK_PALETTE = [
    "#60a5fa", "#fbbf24", "#34d399", "#f87171", "#a78bfa",
    "#22d3ee", "#f472b6", "#a3e635", "#fb923c", "#94a3b8",
];
const STATUS_COLORS_LIGHT = { draft: "#94a3b8", sent: "#0ea5e9", purchase: "#3b82f6", done: "#10b981", cancel: "#ef4444" };
const STATUS_COLORS_DARK = { draft: "#a8b3c5", sent: "#38bdf8", purchase: "#60a5fa", done: "#34d399", cancel: "#f87171" };

const compactNumber = (value) =>
    new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
const fullNumber = (value) =>
    new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value || 0);

// Inline plugin: doughnut depth treatment.
// 1. Shadow layer: a soft drop-shadow ring that lifts the chart off the card.
// 2. Center typography (with a subtle halo) after draw.
const doughnutDepth = {
    id: "bopDoughnutDepth",
    beforeDatasetsDraw(chart) {
        const { ctx } = chart;
        ctx.save();
        ctx.shadowColor = "rgba(9, 14, 25, 0.28)";
        ctx.shadowBlur = 26;
        ctx.shadowOffsetY = 10;
    },
    afterDatasetsDraw(chart) {
        chart.ctx.restore();
    },
    afterDraw(chart) {
        const options = chart.options.plugins && chart.options.plugins.bopCenterText;
        if (!options || !options.text || !chart.chartArea) return;
        const { ctx, chartArea } = chart;
        const centerX = (chartArea.left + chartArea.right) / 2;
        const centerY = (chartArea.top + chartArea.bottom) / 2;
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        // A soft inner halo behind the center text - subtle depth.
        const radius = Math.min(chartArea.right - chartArea.left, chartArea.bottom - chartArea.top) / 6.2;
        const halo = ctx.createRadialGradient(centerX, centerY, 2, centerX, centerY, radius);
        halo.addColorStop(0, options.haloColor);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = options.textColor;
        ctx.font = `700 ${options.textSize}px Inter, system-ui, -apple-system, sans-serif`;
        ctx.fillText(options.text, centerX, centerY - 7);
        ctx.fillStyle = options.subTextColor;
        ctx.font = `500 10.5px Inter, system-ui, -apple-system, sans-serif`;
        ctx.fillText(options.subText, centerX, centerY + 14);
        ctx.restore();
    },
};

class PurchaseDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({ loading: true, error: false, kpis: [], currencySymbol: "", updatedAt: "" });
        this.dashboardData = null;
        this.chartInstances = {};
        this.themeObserver = null;
        this.themeWatchdog = null;
        this.themeDebounce = null;
        this.isDark = null;

        this.monthlyAmountRef = useRef("monthly_amount");
        this.orderStatusRef = useRef("order_status");
        this.productStockRef = useRef("product_stock");
        this.vendorOutstandingRef = useRef("vendor_outstanding");
        this.topPurchasedRef = useRef("top_purchased");
        this.vendorDistributionRef = useRef("vendor_distribution");

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });

        onMounted(() => {
            this.applyTheme(); // immediate: correct theme before data arrives
            this.startThemeWatch();
            this.loadDashboard();
        });

        onWillUnmount(() => {
            this.stopThemeWatch();
            this.destroyCharts();
        });
    }

    // ==========================================================
    // DATA LIFECYCLE
    // ==========================================================

    async loadDashboard() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.dashboardData = await this.orm.call("purchase.order", "get_purchase_dashboard_data", []);
            this.state.currencySymbol = this.dashboardData.currency_symbol || "";
            this.state.kpis = this.prepareKpis(this.dashboardData.kpis, this.state.currencySymbol);
            this.state.updatedAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            this.state.loading = false;
            this.applyTheme();
        } catch {
            this.state.loading = false;
            this.state.error = true;
        }
    }

    prepareKpis(kpis, currencySymbol) {
        return kpis.map((kpi) => {
            const display = kpi.kind === "money"
                ? `${currencySymbol}${compactNumber(kpi.value)}`
                : `${fullNumber(kpi.value)}`;
            const full = kpi.kind === "money"
                ? `${currencySymbol}${fullNumber(kpi.value)}`
                : `${fullNumber(kpi.value)}`;
            return { ...kpi, display, full };
        });
    }

    refresh() {
        return this.loadDashboard();
    }

    // ==========================================================
    // THEME - layered, mechanism-agnostic detection
    // ==========================================================

    detectDarkMode() {
        // Layer 1: explicit theme attributes on <html>.
        const html = document.documentElement;
        if (html.getAttribute("data-bs-theme") === "dark") return true;
        if (html.getAttribute("data-bs-theme") === "light") return false;
        if (html.getAttribute("data-theme") === "dark") return true;
        // Layer 2: any class containing 'dark' on <html> or <body>.
        if (this.hasClassContainingDark(html)) return true;
        if (this.hasClassContainingDark(document.body)) return true;
        // Layer 3: luminance sampling of Odoo's chrome - works no matter
        // WHICH mechanism the build uses, because the rendered color is truth.
        const sampledBg = this.sampleBackgroundColor();
        const sampledText = this.sampleTextColor();
        if (sampledBg) {
            const bgDark = this.isColorDark(sampledBg);
            if (sampledText) {
                const textDark = this.isColorDark(sampledText);
                if (bgDark !== textDark) return bgDark; // bg and text disagree = clear signal
            }
            return bgDark;
        }
        // Layer 4: OS preference as last resort.
        return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    hasClassContainingDark(node) {
        return Boolean(node) && [...node.classList].some((cls) => cls.toLowerCase().includes("dark"));
    }

    sampleBackgroundColor() {
        const candidates = [
            document.querySelector(".o_main_navbar"),
            document.querySelector(".o_content"),
            document.querySelector("main"),
            document.body,
            document.documentElement,
        ];
        for (const node of candidates) {
            if (!node) continue;
            const color = this.parseColor(node);
            if (color) return color;
        }
        return null;
    }

    sampleTextColor() {
        const node = document.querySelector(".o_main_navbar") || document.body;
        return this.parseColor(node, "color");
    }

    parseColor(node, property = "backgroundColor") {
        if (!node) return null;
        const match = getComputedStyle(node)[property]
            .match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
        if (!match) return null;
        const alpha = match[4] === undefined ? 1 : parseFloat(match[4]);
        if (alpha < 0.5) return null; // transparent - not informative
        return [parseInt(match[1], 10), parseInt(match[2], 10), parseInt(match[3], 10)];
    }

    isColorDark([red, green, blue]) {
        return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255 < 0.45;
    }

    applyTheme() {
        const dark = this.detectDarkMode();
        if (dark === this.isDark && this.el && this.el.classList.contains(dark ? "bop-dark" : "bop-light")) {
            return; // no change, no re-render
        }
        this.isDark = dark;
        if (this.el) {
            this.el.classList.remove("bop-dark", "bop-light");
            this.el.classList.add(dark ? "bop-dark" : "bop-light");
        }
        this.renderCharts();
    }

    startThemeWatch() {
        // MutationObserver: catch attribute/class/style changes on html+body.
        if (typeof MutationObserver !== "undefined") {
            this.themeObserver = new MutationObserver(() => this.scheduleThemeCheck());
            this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-bs-theme", "data-theme"] });
            this.themeObserver.observe(document.body, { attributes: true, attributeFilter: ["class", "style"] });
        }
        // Watchdog: CSS-only or unobservable theme mechanisms get caught
        // within a second of flipping.
        this.themeWatchdog = setInterval(() => this.scheduleThemeCheck(), 1000);
    }

    stopThemeWatch() {
        clearInterval(this.themeWatchdog);
        clearTimeout(this.themeDebounce);
        if (this.themeObserver) this.themeObserver.disconnect();
    }

    scheduleThemeCheck() {
        clearTimeout(this.themeDebounce);
        this.themeDebounce = setTimeout(() => {
            if (this.detectDarkMode() !== this.isDark) this.applyTheme();
        }, 120);
    }

    // ==========================================================
    // CHART RENDERING
    // ==========================================================

    getChartTheme() {
        const dark = this.isDark;
        return {
            dark,
            palette: dark ? DARK_PALETTE : LIGHT_PALETTE,
            statusColors: dark ? STATUS_COLORS_DARK : STATUS_COLORS_LIGHT,
            textColor: dark ? "#cbd5e1" : "#475569",
            subtleColor: dark ? "#94a3b8" : "#64748b",
            gridColor: dark ? "rgba(148,163,184,0.16)" : "rgba(100,116,139,0.16)",
            tooltipBg: "rgba(15,23,42,0.94)",
            tooltipBorder: dark ? "rgba(148,163,184,0.3)" : "rgba(15,23,42,0.15)",
            tooltipText: "#f8fafc",
            accent: dark ? "#60a5fa" : "#2563eb",
            success: dark ? "#34d399" : "#10b981",
            danger: dark ? "#f87171" : "#ef4444",
            warning: dark ? "#fbbf24" : "#f59e0b",
        };
    }

    destroyCharts() {
        for (const chart of Object.values(this.chartInstances)) chart.destroy();
        this.chartInstances = {};
    }

    renderCharts() {
        if (!this.dashboardData || this.state.loading || this.state.error) return;
        this.destroyCharts();
        this.renderMonthlyAmountChart();
        this.renderOrderStatusChart();
        this.renderStockChart();
        this.renderVendorOutstandingChart();
        this.renderTopPurchasedChart();
        this.renderVendorDistributionChart();
    }

    hexToRgb(hex) {
        const value = hex.replace("#", "");
        return [
            parseInt(value.slice(0, 2), 16),
            parseInt(value.slice(2, 4), 16),
            parseInt(value.slice(4, 6), 16),
        ];
    }

    hexToRgba(hex, alpha) {
        const [red, green, blue] = this.hexToRgb(hex);
        return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }

    // ==========================================================
    // DOUGHNUT SLICE COLORS - computed EAGERLY as plain values.
    // (FIX: the previous version handed Chart.js arrays of FUNCTIONS for
    // backgroundColor; this build does not call them per-slice and painted
    // black. A radial gradient object is a plain, always-paintable value.)
    // ==========================================================

    doughnutSliceGradient(canvas, hex) {
        const context = canvas.getContext("2d");
        const width = canvas.width || canvas.clientWidth || 300;
        const height = canvas.height || canvas.clientHeight || 300;
        const centerX = width / 2;
        const centerY = height / 2;
        const outerRadius = Math.min(width, height) / 2;

        const dark = this.isDark;
        const inner = this.lightenHex(hex, dark ? 0.32 : 0.26);
        const outer = this.shadeHex(hex, dark ? 0.10 : 0.16);

        const gradient = context.createRadialGradient(
            centerX, centerY, Math.max(outerRadius * 0.18, 4),
            centerX, centerY, Math.max(outerRadius * 1.12, 8),
        );
        gradient.addColorStop(0, inner);
        gradient.addColorStop(1, outer);
        return gradient;
    }

    lightenHex(hex, amount) {
        const [r, g, b] = this.hexToRgb(hex);
        const mix = (channel) => Math.round(channel + (255 - channel) * amount);
        return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
    }

    shadeHex(hex, amount) {
        const [r, g, b] = this.hexToRgb(hex);
        const mix = (channel) => Math.round(channel * (1 - amount));
        return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
    }

    // Scriptable gradients for bars (verified working in your build):
    // single function per dataset, called with the dataset context.
    verticalGradient(hex, alphaTop, alphaBottom) {
        return (context) => {
            const { ctx, chartArea } = context.chart;
            if (!chartArea) return this.hexToRgba(hex, alphaTop);
            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            gradient.addColorStop(0, this.hexToRgba(hex, alphaTop));
            gradient.addColorStop(1, this.hexToRgba(hex, alphaBottom));
            return gradient;
        };
    }

    horizontalGradient(hex, alphaLeft, alphaRight) {
        return (context) => {
            const { ctx, chartArea } = context.chart;
            if (!chartArea) return this.hexToRgba(hex, alphaRight);
            const gradient = ctx.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
            gradient.addColorStop(0, this.hexToRgba(hex, alphaLeft));
            gradient.addColorStop(1, this.hexToRgba(hex, alphaRight));
            return gradient;
        };
    }

    cartesianOptions(theme, { valueAxis = "y", money = false, onElement = null }) {
        const currency = this.state.currencySymbol;
        const formatTick = (value) => (money ? `${currency}${compactNumber(value)}` : compactNumber(value));
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 450, easing: "easeOutQuart" },
            interaction: { intersect: false, mode: "index" },
            onClick: (event, elements) => {
                if (onElement && elements.length) onElement(elements[0].index);
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: theme.tooltipBg,
                    titleColor: theme.tooltipText,
                    bodyColor: theme.tooltipText,
                    borderColor: theme.tooltipBorder,
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                    titleFont: { family: "Inter, system-ui, sans-serif", weight: "600" },
                    bodyFont: { family: "Inter, system-ui, sans-serif", weight: "500" },
                    callbacks: {
                        label: (ctx) => (money
                            ? ` ${currency}${fullNumber(ctx.parsed.y ?? ctx.parsed.x ?? ctx.parsed)}`
                            : ` ${fullNumber(ctx.parsed.y ?? ctx.parsed.x ?? ctx.parsed)}`),
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: theme.textColor,
                        maxRotation: 0,
                        autoSkip: true,
                        font: { family: "Inter, system-ui, sans-serif", size: 11 },
                        callback: valueAxis === "x" ? formatTick : undefined,
                    },
                    grid: { display: false },
                    border: { color: theme.gridColor },
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: theme.textColor,
                        font: { family: "Inter, system-ui, sans-serif", size: 11 },
                        callback: valueAxis === "y" ? formatTick : undefined,
                    },
                    grid: { color: theme.gridColor },
                    border: { display: false },
                },
            },
        };
    }

    doughnutOptions(theme, { onSlice = null, labelFormatter = null, center = null }) {
        const currency = this.state.currencySymbol;
        return {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "64%",
            animation: { duration: 550, easing: "easeOutQuart" },
            onClick: (event, elements) => {
                if (onSlice && elements.length) onSlice(elements[0].index);
            },
            plugins: {
                legend: {
                    display: true,
                    position: "bottom",
                    labels: {
                        color: theme.textColor,
                        usePointStyle: true,
                        pointStyle: "circle",
                        boxWidth: 7,
                        boxHeight: 7,
                        padding: 14,
                        font: { family: "Inter, system-ui, sans-serif", size: 11 },
                    },
                },
                tooltip: {
                    backgroundColor: theme.tooltipBg,
                    titleColor: theme.tooltipText,
                    bodyColor: theme.tooltipText,
                    borderColor: theme.tooltipBorder,
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                    titleFont: { family: "Inter, system-ui, sans-serif", weight: "600" },
                    bodyFont: { family: "Inter, system-ui, sans-serif", weight: "500" },
                    callbacks: {
                        label: labelFormatter || ((ctx) => ` ${ctx.label}: ${currency}${compactNumber(ctx.parsed)}`),
                    },
                },
                bopCenterText: center ? {
                    text: center.text,
                    subText: center.subText,
                    textColor: theme.dark ? "#eef2f7" : "#0f172a",
                    subTextColor: theme.subtleColor,
                    haloColor: theme.dark ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.05)",
                    textSize: 19,
                } : undefined,
            },
        };
    }

    renderMonthlyAmountChart() {
        const canvas = this.monthlyAmountRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const monthly = this.dashboardData.monthly_amount;

        this.chartInstances.monthly = new window.Chart(canvas, {
            type: "line",
            data: {
                labels: monthly.labels,
                datasets: [{
                    label: "Purchase Amount",
                    data: monthly.totals,
                    borderColor: theme.success,
                    backgroundColor: (context) => {
                        const { ctx, chartArea } = context.chart;
                        if (!chartArea) return "transparent";
                        const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        gradient.addColorStop(0, this.hexToRgba(theme.success, 0.35));
                        gradient.addColorStop(1, this.hexToRgba(theme.success, 0.02));
                        return gradient;
                    },
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: theme.success,
                    pointBorderColor: theme.dark ? "#22252c" : "#ffffff",
                    pointBorderWidth: 2,
                }],
            },
            options: this.cartesianOptions(theme, { money: true }),
        });
    }

    renderStockChart() {
        const canvas = this.productStockRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const stock = this.dashboardData.product_stock;

        this.chartInstances.stock = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: stock.labels,
                datasets: [{
                    label: "Stock Balance",
                    data: stock.totals,
                    backgroundColor: this.verticalGradient(theme.accent, 0.95, 0.35),
                    hoverBackgroundColor: theme.accent,
                    borderRadius: 7,
                    borderSkipped: false,
                    maxBarThickness: 42,
                }],
            },
            options: this.cartesianOptions(theme, {
                onElement: (index) => this.openRecord("product.product", stock.ids[index]),
            }),
        });
    }

    renderVendorOutstandingChart() {
        const canvas = this.vendorOutstandingRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const outstanding = this.dashboardData.vendor_outstanding;

        this.chartInstances.outstanding = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: outstanding.labels,
                datasets: [{
                    label: "Outstanding Amount",
                    data: outstanding.totals,
                    backgroundColor: this.verticalGradient(theme.danger, 0.95, 0.35),
                    hoverBackgroundColor: theme.danger,
                    borderRadius: 7,
                    borderSkipped: false,
                    maxBarThickness: 42,
                }],
            },
            options: this.cartesianOptions(theme, {
                money: true,
                onElement: (index) => this.openRecord("res.partner", outstanding.ids[index]),
            }),
        });
    }

    renderTopPurchasedChart() {
        const canvas = this.topPurchasedRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const topPurchased = this.dashboardData.top_purchased;

        this.chartInstances.topPurchased = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: topPurchased.labels,
                datasets: [{
                    label: "Qty Purchased",
                    data: topPurchased.totals,
                    backgroundColor: this.horizontalGradient(theme.warning, 0.30, 0.95),
                    hoverBackgroundColor: theme.warning,
                    borderRadius: 7,
                    borderSkipped: false,
                    maxBarThickness: 26,
                }],
            },
            options: {
                ...this.cartesianOptions(theme, {
                    valueAxis: "x",
                    onElement: (index) => this.openRecord("product.product", topPurchased.ids[index]),
                }),
                indexAxis: "y",
            },
        });
    }

    renderVendorDistributionChart() {
        const canvas = this.vendorDistributionRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const distribution = this.dashboardData.vendor_distribution;
        const currency = this.state.currencySymbol;
        const total = (distribution.totals || []).reduce((sum, value) => sum + value, 0);

        // FIX: EAGER plain-value colors. Each entry is a gradient OBJECT (or
        // plain string for 'Others') - always paintable, no scriptable calls.
        const sliceColors = distribution.ids.map((id, sliceIndex) => {
            if (id === false) {
                return theme.dark ? "#5b6572" : "#94a3b8"; // 'Others' - neutral
            }
            return this.doughnutSliceGradient(canvas, theme.palette[sliceIndex % theme.palette.length]);
        });

        this.chartInstances.distribution = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: distribution.labels,
                datasets: [{
                    data: distribution.totals,
                    backgroundColor: sliceColors,
                    borderColor: theme.dark ? "#22252c" : "#ffffff",
                    borderWidth: 2.5,
                    hoverOffset: 10,
                    hoverBorderWidth: 3,
                }],
            },
            options: this.doughnutOptions(theme, {
                onSlice: (index) => this.openRecord("res.partner", distribution.ids[index]),
                center: { text: `${currency}${compactNumber(total)}`, subText: "Total purchases" },
            }),
            plugins: [doughnutDepth],
        });
    }

    renderOrderStatusChart() {
        const canvas = this.orderStatusRef.el;
        if (!canvas) return;
        const theme = this.getChartTheme();
        const statusData = this.dashboardData.order_status;
        const totalOrders = (statusData.counts || []).reduce((sum, value) => sum + value, 0);

        // FIX: EAGER plain-value gradient objects per status color.
        const sliceColors = statusData.states.map(
            (state) => this.doughnutSliceGradient(canvas, theme.statusColors[state] || theme.accent),
        );

        this.chartInstances.status = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: statusData.labels,
                datasets: [{
                    data: statusData.counts,
                    backgroundColor: sliceColors,
                    borderColor: theme.dark ? "#22252c" : "#ffffff",
                    borderWidth: 2.5,
                    hoverOffset: 10,
                    hoverBorderWidth: 3,
                }],
            },
            options: this.doughnutOptions(theme, {
                labelFormatter: (ctx) => ` ${ctx.label}: ${fullNumber(ctx.parsed)}`,
                onSlice: (index) => this.openList(
                    "purchase.order",
                    statusData.labels[index],
                    [["state", "=", statusData.states[index]]],
                ),
                center: { text: `${fullNumber(totalOrders)}`, subText: "Orders" },
            }),
            plugins: [doughnutDepth],
        });
    }

    // ==========================================================
    // NAVIGATION
    // ==========================================================

    openRecord(resModel, resId) {
        if (!resId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            views: [[false, "form"]],
            res_id: resId,
            target: "current",
        });
    }

    openList(resModel, name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            domain,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openKpi(kpi) {
        if (kpi.res_id) {
            this.openRecord(kpi.res_model, kpi.res_id);
            return;
        }
        this.openList(kpi.res_model, kpi.name, kpi.domain);
    }
}

PurchaseDashboard.template = "bop_charts.PurchaseDashboardMain";
registry.category("actions").add("purchase_dashboard_tag", PurchaseDashboard);