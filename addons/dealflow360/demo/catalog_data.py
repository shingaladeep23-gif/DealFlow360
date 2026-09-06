"""A2's catalogue, as data.

A2 asks for "products with variants, categories, taxes, price lists, customer
tier based pricing, currency specific rules". Almost none of it existed:
4 products total, zero attributes, zero variants, zero product descriptions,
zero price lists (the menu opened an empty list), only USD active, and two
account.tax records that were assigned to nothing - so the Tax column on every
product and every order line was permanently blank.

Everything here is idempotent and additive. In particular it does NOT retrofit
attributes onto the four original products: adding an attribute to a template
that already has a variant archives that variant and mints new ones, which
would orphan every existing order line, upsell rule and stock quant pointing at
it. The variant demonstration is carried by new products instead, which costs
nothing and breaks nothing.
"""

from odoo import fields

# (name, category key, type, list price, cost, sales description)
EXTRA_PRODUCTS = [
    (
        "UltraWide Monitor",
        "hardware",
        "product",
        450.0,
        300.0,
        "34-inch curved ultrawide panel with a built-in KVM switch. Ships with "
        "a 3-year on-site exchange warranty.",
    ),
    (
        "Cable & Power Kit",
        "hardware",
        "product",
        45.0,
        22.0,
        "Everything needed to get a new desk running: USB-C power delivery "
        "cable, HDMI 2.1 cable and a surge-protected power strip.",
    ),
    (
        "Onboarding Workshop",
        "services",
        "service",
        1500.0,
        600.0,
        "A one-day facilitated session for up to twelve people, covering "
        "rollout planning, admin training and a written handover document.",
    ),
]

# Sales descriptions for the four products that shipped before this file. They
# had none at all, so the customer-facing quotation and portal both showed a
# bare product name with nothing explaining what was being bought.
ORIGINAL_PRODUCT_DESCRIPTIONS = {
    "ProBook Laptop": "14-inch business laptop, 16 GB RAM and a 512 GB NVMe "
    "drive, with a 3-year next-business-day warranty.",
    "Onsite Setup Service": "An engineer on site to unbox, image, join to the "
    "domain and hand over each device, charged per device.",
    "Core Plan": "Monthly support subscription: unlimited tickets, a "
    "four-hour response target during business hours, and quarterly health "
    "reporting.",
    "Docking Station": "Single-cable USB-C dock driving two 4K displays, with "
    "100 W passthrough charging and gigabit Ethernet.",
}

# attribute name -> value names. Kept small on purpose: two attributes with two
# values each is four real variants, which is enough to show the mechanism
# without burying the catalogue.
ATTRIBUTES = {
    "Storage": ["128 GB", "256 GB"],
    "Connectivity": ["Wi-Fi", "Wi-Fi + 5G"],
    "Finish": ["Black", "Graphite"],
}

# name -> (percentage off list, description). Tier pricelists are what make
# A2's "customer tier based pricing" real rather than a label on a partner.
TIER_PRICELISTS = [
    ("Gold Tier Pricing", "gold", 12.0),
    ("Silver Tier Pricing", "silver", 7.0),
    ("Bronze Tier Pricing", "bronze", 3.0),
]


def _get_or_create_attribute(env, name, value_names):
    Attribute = env["product.attribute"]
    attribute = Attribute.search([("name", "=", name)], limit=1)
    if not attribute:
        attribute = Attribute.create({"name": name, "create_variant": "always"})
    Value = env["product.attribute.value"]
    values = Value
    for value_name in value_names:
        value = Value.search(
            [("name", "=", value_name), ("attribute_id", "=", attribute.id)], limit=1
        ) or Value.create({"name": value_name, "attribute_id": attribute.id})
        values |= value
    return attribute, values


def _ensure_attributes(env):
    return {
        name: _get_or_create_attribute(env, name, value_names)
        for name, value_names in ATTRIBUTES.items()
    }


def _ensure_product(env, name, categ, ptype, price, cost, description, **extra):
    Product = env["product.template"]
    product = Product.search([("name", "=", name)], limit=1)
    values = {
        "categ_id": categ.id,
        "type": ptype,
        "list_price": price,
        "standard_price": cost,
        "description_sale": description,
    }
    values.update(extra)
    if product:
        # Never overwrite a price, cost or category somebody has since tuned by
        # hand - only fill in the description if it is genuinely still empty.
        if not product.description_sale:
            product.description_sale = description
        return product
    return Product.create(dict(values, name=name))


def _ensure_variant_products(env, categories, attributes):
    """Two products carrying real attribute lines, so A2's variants exist as
    variants rather than as separately-named products."""
    storage, storage_values = attributes["Storage"]
    connectivity, connectivity_values = attributes["Connectivity"]
    finish, finish_values = attributes["Finish"]

    tablet = _ensure_product(
        env,
        "FieldPad Tablet",
        categories["hardware"],
        "product",
        700.0,
        480.0,
        "Ruggedised 11-inch field tablet with a daylight-readable screen and "
        "a swappable battery. Configure storage and connectivity per unit.",
    )
    if not tablet.attribute_line_ids:
        env["product.template.attribute.line"].create(
            [
                {
                    "product_tmpl_id": tablet.id,
                    "attribute_id": storage.id,
                    "value_ids": [(6, 0, storage_values.ids)],
                },
                {
                    "product_tmpl_id": tablet.id,
                    "attribute_id": connectivity.id,
                    "value_ids": [(6, 0, connectivity_values.ids)],
                },
            ]
        )

    chair = _ensure_product(
        env,
        "Ergo Task Chair",
        categories["hardware"],
        "product",
        320.0,
        190.0,
        "Fully adjustable task chair with lumbar support and a 10-year frame "
        "warranty.",
    )
    if not chair.attribute_line_ids:
        env["product.template.attribute.line"].create(
            {
                "product_tmpl_id": chair.id,
                "attribute_id": finish.id,
                "value_ids": [(6, 0, finish_values.ids)],
            }
        )
    return {"tablet": tablet, "chair": chair}


def _ensure_recurring_extra(env, categories):
    """A second subscription product, on a different cadence to Core Plan, so
    the Subscriptions screen and the MRR normalisation have more than one
    interval to show."""
    plan = env.ref("dealflow360.recurring_plan_quarterly", raise_if_not_found=False)
    if not plan:
        plan = env["dealflow.recurring.plan"].search(
            [("interval", "=", "quarterly")], limit=1
        )
    product = _ensure_product(
        env,
        "Premium Support Plan",
        categories["services"],
        "service",
        2400.0,
        900.0,
        "Quarterly premium support: a named engineer, a one-hour response "
        "target around the clock, and an annual architecture review.",
        df_is_recurring=True,
    )
    if plan and not product.df_recurring_plan_id:
        product.df_recurring_plan_id = plan.id
    return product


def _ensure_taxes_on_products(env):
    """Two account.tax records existed and were on NOTHING, so the Tax column
    was blank on every product and every order line in the system."""
    sale_tax = env["account.tax"].search(
        [
            ("type_tax_use", "=", "sale"),
            ("company_id", "=", env.company.id),
        ],
        limit=1,
    )
    if not sale_tax:
        return env["account.tax"]
    untaxed = env["product.template"].search([("taxes_id", "=", False)])
    if untaxed:
        untaxed.write({"taxes_id": [(6, 0, sale_tax.ids)]})
    return sale_tax


def _ensure_second_currency(env):
    """A2 asks for "currency specific rules", which needs at least two live
    currencies. Only USD was active, so a second-currency price list could not
    even be expressed."""
    eur = env.ref("base.EUR", raise_if_not_found=False)
    if not eur:
        return env["res.currency"]
    if not eur.active:
        eur.active = True
    if not eur.rate_ids.filtered(lambda r: r.company_id == env.company):
        env["res.currency.rate"].create(
            {
                "currency_id": eur.id,
                "company_id": env.company.id,
                "name": fields.Date.context_today(env["res.currency"]),
                "rate": 0.92,
            }
        )
    return eur


def _ensure_pricelists(env, eur):
    """Tier pricing and a currency-specific list. The Price Lists menu opened
    an empty list before this, so neither half of A2's "customer tier based
    pricing, currency specific rules" was demonstrable."""
    Pricelist = env["product.pricelist"]
    Item = env["product.pricelist.item"]
    created = {}
    for name, tier_key, percent in TIER_PRICELISTS:
        pricelist = Pricelist.search([("name", "=", name)], limit=1)
        if not pricelist:
            pricelist = Pricelist.create(
                {"name": name, "currency_id": env.company.currency_id.id}
            )
        if not pricelist.item_ids:
            Item.create(
                {
                    "pricelist_id": pricelist.id,
                    "applied_on": "3_global",
                    "compute_price": "percentage",
                    "percent_price": percent,
                    "base": "list_price",
                }
            )
        created[tier_key] = pricelist

    if eur:
        name = "Europe (EUR)"
        eur_list = Pricelist.search([("name", "=", name)], limit=1)
        if not eur_list:
            eur_list = Pricelist.create({"name": name, "currency_id": eur.id})
        if not eur_list.item_ids:
            Item.create(
                {
                    "pricelist_id": eur_list.id,
                    "applied_on": "3_global",
                    "compute_price": "percentage",
                    "percent_price": 5.0,
                    "base": "list_price",
                }
            )
        created["eur"] = eur_list
    return created


def _assign_pricelists_to_customers(env, pricelists):
    """Put each demo customer on the price list its tier earns, so the tier on
    the partner and the price they actually get are the same fact."""
    tier_by_xmlid = {
        "gold": "dealflow360.discount_tier_gold",
        "silver": "dealflow360.discount_tier_silver",
        "bronze": "dealflow360.discount_tier_bronze",
    }
    for tier_key, xmlid in tier_by_xmlid.items():
        pricelist = pricelists.get(tier_key)
        tier = env.ref(xmlid, raise_if_not_found=False)
        if not pricelist or not tier:
            continue
        partners = env["res.partner"].search(
            [("df_tier_id", "=", tier.id), ("is_company", "=", True)]
        )
        for partner in partners:
            if partner.property_product_pricelist != pricelist:
                partner.property_product_pricelist = pricelist.id


def _describe_original_products(env):
    for name, description in ORIGINAL_PRODUCT_DESCRIPTIONS.items():
        product = env["product.template"].search([("name", "=", name)], limit=1)
        if product and not product.description_sale:
            product.description_sale = description


def seed_catalog(env):
    """Idempotent entry point, called from post_init_hook and from the
    17.0.1.6.0 migration."""
    categories = {
        "hardware": env.ref("dealflow360.product_category_hardware"),
        "services": env.ref("dealflow360.product_category_services"),
    }
    attributes = _ensure_attributes(env)
    _ensure_variant_products(env, categories, attributes)
    _ensure_recurring_extra(env, categories)
    for name, categ_key, ptype, price, cost, description in EXTRA_PRODUCTS:
        _ensure_product(
            env, name, categories[categ_key], ptype, price, cost, description
        )
    _describe_original_products(env)
    _ensure_taxes_on_products(env)
    eur = _ensure_second_currency(env)
    pricelists = _ensure_pricelists(env, eur)
    _assign_pricelists_to_customers(env, pricelists)
