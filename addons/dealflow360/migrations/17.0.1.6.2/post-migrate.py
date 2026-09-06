"""Take the two reference customers back off the tier price lists.

17.0.1.6.0 seeded A2's tier price lists and put every customer on the one its
tier earns. That is a defensible reading of "customer tier based pricing" and a
bad idea here: a tier list knocks a percentage off every list price, so it
silently re-priced every quotation Acme Corp and Beta Industries appear in -
including the problem statement's own section 10 worked example, whose numbers
are verified against the spec and have to keep matching it. Ten tests caught it.

Tier pricing is demonstrated on Cascadia Systems instead, a customer whose
arithmetic nothing else depends on (see catalog_data._ensure_tier_priced_
customer). The price lists themselves stay: they are real, configurable, and
either reference customer can be put on one from the partner form.
"""

from odoo import SUPERUSER_ID, api

REFERENCE_CUSTOMERS = ("Acme Corp", "Beta Industries")
TIER_PRICELIST_NAMES = (
    "Gold Tier Pricing",
    "Silver Tier Pricing",
    "Bronze Tier Pricing",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    tier_lists = env["product.pricelist"].search(
        [("name", "in", list(TIER_PRICELIST_NAMES))]
    )
    if not tier_lists:
        return
    partners = env["res.partner"].search(
        [("name", "in", list(REFERENCE_CUSTOMERS)), ("is_company", "=", True)]
    )
    if not partners:
        return
    # The ir.property row has to be removed, not overwritten. Assigning False
    # to property_product_pricelist does nothing durable: it is a compute/
    # inverse pair over a company-dependent field, and res.partner._inverse_
    # product_pricelist only rewrites the property when the new value differs
    # from the country default - so an empty value leaves the existing row
    # exactly where it was. Verified against the database: after assigning
    # False the ir.property row still read 'product.pricelist,8'.
    #
    # With the row gone, _compute_product_pricelist falls back the way it did
    # before A2's lists existed - to the neutral, item-less default pricelist -
    # so list prices apply and section 10's worked example still matches.
    tier_values = ["product.pricelist,%d" % pricelist.id for pricelist in tier_lists]
    properties = env["ir.property"].search(
        [
            ("name", "=", "property_product_pricelist"),
            ("res_id", "in", ["res.partner,%d" % partner.id for partner in partners]),
        ]
    )
    # Only ours - never drop a price list somebody chose deliberately.
    properties.filtered(lambda p: p.value_reference in tier_values).unlink()
