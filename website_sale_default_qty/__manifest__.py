# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Website Sale Default Quantity",
    "version": "18.0.1.0.0",
    "category": "Website",
    "summary": "Configure a default cart quantity per product in eCommerce",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "depends": ["website_sale"],
    "data": [
        "views/product_views.xml",
        "views/templates.xml",
    ],
    "installable": True,
    "application": False,
    "license": "AGPL-3",
    "description": "Adds a company-dependent integer field on product.template to configure the default quantity pre-filled in the eCommerce quantity selector.",
}
