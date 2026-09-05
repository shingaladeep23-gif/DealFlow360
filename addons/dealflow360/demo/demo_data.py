"""Reproducible seed data for DealFlow360.

Runs once as a post_init_hook (not gated behind Odoo's --without-demo flag)
so the demo dataset described in docs/demo_script.md always exists after a
fresh install. Values here are real records the later governance, risk,
fulfillment and billing engines will read — never hardcoded results.
"""


def _create_partners(env, tiers):
    Partner = env["res.partner"]
    acme = Partner.create(
        {
            "name": "Acme Corp",
            "is_company": True,
            "customer_rank": 1,
            "email": "purchasing@acme-corp.example",
            "df_tier_id": tiers["gold"].id,
        }
    )
    beta = Partner.create(
        {
            "name": "Beta Industries",
            "is_company": True,
            "customer_rank": 1,
            "email": "purchasing@beta-industries.example",
            "df_tier_id": tiers["silver"].id,
        }
    )
    return {"acme": acme, "beta": beta}


def _create_products(env, categories):
    Product = env["product.template"]
    probook = Product.create(
        {
            "name": "ProBook Laptop",
            "categ_id": categories["hardware"].id,
            "type": "product",
            "list_price": 1200.0,
            "standard_price": 850.0,
        }
    )
    setup_service = Product.create(
        {
            "name": "Onsite Setup Service",
            "categ_id": categories["services"].id,
            "type": "service",
            "list_price": 300.0,
            "standard_price": 120.0,
        }
    )
    core_plan = Product.create(
        {
            "name": "Core Plan",
            "categ_id": categories["services"].id,
            "type": "service",
            "df_is_recurring": True,
            "list_price": 999.0,
            "standard_price": 400.0,
        }
    )
    docking_station = Product.create(
        {
            "name": "Docking Station",
            "categ_id": categories["hardware"].id,
            "type": "product",
            "df_is_promoted": True,
            "df_min_margin": 20.0,
            "list_price": 150.0,
            "standard_price": 90.0,
        }
    )
    return {
        "probook": probook,
        "setup_service": setup_service,
        "core_plan": core_plan,
        "docking_station": docking_station,
    }


def _create_upsell_rules(env, products):
    """DF-008 curated pairings, so the demo shows both signals the
    recommendation engine blends - not just the co-purchase history that
    accumulates from confirmed orders. Real product references from the
    seed data above, no invented data."""
    Rule = env["dealflow.upsell.rule"]
    Rule.create(
        {
            "product_id": products["probook"].product_variant_id.id,
            "suggested_product_id": products["docking_station"].product_variant_id.id,
            "score": 70.0,
            "reason": "Frequently paired with laptops",
        }
    )
    Rule.create(
        {
            "product_id": products["probook"].product_variant_id.id,
            "suggested_product_id": products["setup_service"].product_variant_id.id,
            "score": 60.0,
            "reason": "Recommended onsite setup for new hardware",
        }
    )
    Rule.create(
        {
            "product_id": products["docking_station"].product_variant_id.id,
            "suggested_product_id": products["core_plan"].product_variant_id.id,
            "score": 40.0,
            "reason": "Customers on a support plan keep hardware covered",
        }
    )


def _create_warehouses(env):
    Warehouse = env["stock.warehouse"]
    company = env.ref("base.main_company")
    main_wh = Warehouse.create(
        {"name": "Main Warehouse", "code": "MAIN", "company_id": company.id}
    )
    east_wh = Warehouse.create(
        {"name": "East Depot", "code": "EAST", "company_id": company.id}
    )
    return {"main": main_wh, "east": east_wh}


def _seed_stock(env, products, warehouses):
    """Deliberately fragment ProBook stock across two warehouses.

    6 at Main + 4 at East Depot = 10 units on hand, but no single warehouse
    can fill a 10-unit order — this is load-bearing for the DF-010
    fulfillment/split demo and must never be hardcoded downstream.
    """
    Quant = env["stock.quant"]
    probook = products["probook"].product_variant_id
    docking = products["docking_station"].product_variant_id

    Quant.create(
        {
            "product_id": probook.id,
            "location_id": warehouses["main"].lot_stock_id.id,
            "quantity": 6.0,
        }
    )
    Quant.create(
        {
            "product_id": probook.id,
            "location_id": warehouses["east"].lot_stock_id.id,
            "quantity": 4.0,
        }
    )
    Quant.create(
        {
            "product_id": docking.id,
            "location_id": warehouses["main"].lot_stock_id.id,
            "quantity": 25.0,
        }
    )
    Quant.create(
        {
            "product_id": docking.id,
            "location_id": warehouses["east"].lot_stock_id.id,
            "quantity": 15.0,
        }
    )


def post_init_hook(env):
    tiers = {
        "bronze": env.ref("dealflow360.discount_tier_bronze"),
        "silver": env.ref("dealflow360.discount_tier_silver"),
        "gold": env.ref("dealflow360.discount_tier_gold"),
    }
    categories = {
        "hardware": env.ref("dealflow360.product_category_hardware"),
        "services": env.ref("dealflow360.product_category_services"),
    }

    _create_partners(env, tiers)
    products = _create_products(env, categories)
    _create_upsell_rules(env, products)
    warehouses = _create_warehouses(env)
    _seed_stock(env, products, warehouses)
