"""Seed role logins and worked demo deals onto an already-installed database.

post_init_hook only runs on a fresh install, so every database that already
had dealflow360 installed would never get demo/demo_runtime.py's users and
deals - the same class of gap DEC-020 recorded for the DF-008 upsell rules in
17.0.1.1.0. seed_runtime_demo() is idempotent, so running it here (and again
on any future upgrade) is safe.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.dealflow360.demo.demo_runtime import seed_runtime_demo


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_runtime_demo(env)
