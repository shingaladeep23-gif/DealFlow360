{
    "name": "DealFlow360",
    "version": "17.0.1.6.0",
    "summary": "Intelligent, self-governing B2B sales operations platform",
    "description": """
DealFlow360
===========
Configurable discount governance, blended discount risk scoring, automatic
approval routing, upsell/cross-sell recommendations, multi-warehouse
fulfillment, hybrid one-time/recurring billing, customer portal negotiation
and deal health monitoring — built on native Odoo 17 Community models.
""",
    "category": "Sales",
    "author": "DealFlow360",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "product",
        "sale_management",
        "sale_stock",
        "stock",
        "account",
        "portal",
        # A1: "Internal users can sign up and log in with standard
        # credentials", and customers reach their quotation through a portal
        # login. auth_signup is what provides /web/signup and the portal
        # invitation/reset flow; without it neither was reachable at all.
        "auth_signup",
    ],
    "data": [
        "security/dealflow_security.xml",
        "security/ir.model.access.csv",
        "data/discount_tier_data.xml",
        "data/category_limit_data.xml",
        "data/recurring_plan_data.xml",
        "data/billing_cron_data.xml",
        "data/health_flag_data.xml",
        "data/health_cron_data.xml",
        "views/discount_tier_views.xml",
        "views/res_partner_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/dealflow_menus.xml",
        "views/dealflow_dashboard_views.xml",
        "views/approval_views.xml",
        "views/negotiation_views.xml",
        "views/audit_log_views.xml",
        "views/config_views.xml",
        "views/subscription_views.xml",
        "views/warehouse_split_views.xml",
        "views/deal_health_views.xml",
        "views/sale_order_kanban_views.xml",
        "views/portal_templates.xml",
        "views/invoice_views.xml",
        "views/report_views.xml",
        "report/deal_summary_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dealflow360/static/src/fields/risk_gauge/risk_gauge.js",
            "dealflow360/static/src/fields/risk_gauge/risk_gauge.xml",
            "dealflow360/static/src/fields/invoice_stepper/invoice_stepper.js",
            "dealflow360/static/src/fields/invoice_stepper/invoice_stepper.xml",
            "dealflow360/static/src/workspace/workspace.js",
            "dealflow360/static/src/workspace/workspace.xml",
            "dealflow360/static/src/dashboard/dashboard.js",
            "dealflow360/static/src/dashboard/dashboard.xml",
            "dealflow360/static/src/fields/approval_stepper/approval_stepper.js",
            "dealflow360/static/src/fields/approval_stepper/approval_stepper.xml",
            "dealflow360/static/src/fields/approval_step_actions/approval_step_actions.js",
            "dealflow360/static/src/fields/approval_step_actions/approval_step_actions.xml",
            "dealflow360/static/src/fields/upsell_panel/upsell_panel.js",
            "dealflow360/static/src/fields/upsell_panel/upsell_panel.xml",
            "dealflow360/static/src/fulfillment/fulfillment.js",
            "dealflow360/static/src/fulfillment/fulfillment.xml",
            "dealflow360/static/src/subscriptions/subscriptions.js",
            "dealflow360/static/src/subscriptions/subscriptions.xml",
            "dealflow360/static/src/scss/dealflow.scss",
        ],
    },
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
