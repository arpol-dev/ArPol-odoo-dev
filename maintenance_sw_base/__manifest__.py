# maintenance_sw_base/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Software Inventory",
    "version": "18.0.1.0.0",
    "summary": "Track installed software (OS, platforms, applications) as maintenance equipment",
    "description": """
Maintenance - Software Inventory
================================

A piece of software is a maintenance equipment (kind "Software"), attached to the hardware or
software that hosts it through the equipment hierarchy. A shared catalog of software products,
versions and deployment methods (0k, Cloudron, Odoo Online...) describes what is installed and
how it is updated.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance", "maintenance_equipment_hierarchy"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
