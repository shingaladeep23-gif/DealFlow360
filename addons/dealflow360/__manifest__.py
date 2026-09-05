{
    "name": "DealFlow360",
    "version": "17.0.1.0.0",
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
    ],
    "data": [
        "security/dealflow_security.xml",
        "security/ir.model.access.csv",
        "data/discount_tier_data.xml",
        "data/category_limit_data.xml",
        "views/discount_tier_views.xml",
        "views/res_partner_views.xml",
        "views/product_views.xml",
        "views/dealflow_menus.xml",
    ],
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
