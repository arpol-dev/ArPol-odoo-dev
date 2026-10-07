# maintenance_sw_odoo/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Odoo Databases",
    "version": "18.0.1.0.0",
    "summary": "Odoo databases of a container and their installed modules, linked to the code that provides them",
    "description": """
Maintenance - Odoo Databases
============================

Lists the Odoo databases served by a container and the modules installed in each, and links
every module to the docker component (git repository) that provides it.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_docker"],
    "data": [
        "security/ir.model.access.csv",
        "security/odoo_security.xml",
        "views/odoo_database_views.xml",
        "views/odoo_module_views.xml",
        "views/maintenance_equipment_views.xml",
        "views/menus.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
