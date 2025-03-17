# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Remove unlogged users cron",
    "version": "1.0",
    "category": "Technical",
    "summary": "Uses a planned action to remove the users that never logged.",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "depends": ["auth_signup_verify_email", "loyalty", "sale", "purchase", "account", "stock"],
    "data": ['data/ir_cron_data.xml'],
    "installable": True,
    "application": False,
    "license": "AGPL-3",
    "description": "This module creates a planned action that removes the users that never logged to the database. In combination with the module auth_signup_verify_email, it removes the users that didn't check their email after a delay defined in the code. Helps to deal with AI account creation."
}