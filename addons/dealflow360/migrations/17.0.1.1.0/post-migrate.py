"""DF-008 fix: post_init_hook never runs on `-u` upgrade, so every database
that already had dealflow360 installed silently got 0 dealflow.upsell.rule
rows (see docs/decisions.md DEC-020). A post-migration script DOES run on
upgrade, exactly once per version transition - this ports
demo_data._create_upsell_rules()'s three pairings onto an already-seeded
database, matched by product name (the demo products have no stable xmlid)
and guarded against duplicates so re-running (or running on a database that
was already manually patched) is a no-op, never an IntegrityError against
dealflow.upsell.rule's unique_pairing constraint.
"""

from odoo import SUPERUSER_ID, api

PAIRINGS = [
    ("ProBook Laptop", "Docking Station", 70.0, "Frequently paired with laptops"),
    (
        "ProBook Laptop",
        "Onsite Setup Service",
        60.0,
        "Recommended onsite setup for new hardware",
    ),
    (
        "Docking Station",
        "Core Plan",
        40.0,
        "Customers on a support plan keep hardware covered",
    ),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    Rule = env["dealflow.upsell.rule"]

    for trigger_name, suggested_name, score, reason in PAIRINGS:
        trigger = Product.search([("name", "=", trigger_name)], limit=1)
        suggested = Product.search([("name", "=", suggested_name)], limit=1)
        if not trigger or not suggested:
            # Demo seed data not present on this database (e.g. installed
            # with --without-demo before the seed pipeline existed) -
            # nothing to migrate here, not an error.
            continue

        trigger_variant = trigger.product_variant_id
        suggested_variant = suggested.product_variant_id
        already_exists = Rule.search(
            [
                ("product_id", "=", trigger_variant.id),
                ("suggested_product_id", "=", suggested_variant.id),
            ],
            limit=1,
        )
        if already_exists:
            continue

        Rule.create(
            {
                "product_id": trigger_variant.id,
                "suggested_product_id": suggested_variant.id,
                "score": score,
                "reason": reason,
            }
        )
