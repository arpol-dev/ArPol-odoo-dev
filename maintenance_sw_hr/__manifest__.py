# maintenance_sw_hr/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Software without HR assignment",
    "version": "18.0.1.0.0",
    "summary": "Hide the HR assignment of software equipment",
    "description": """
Maintenance - Software without HR assignment
============================================

Glue between maintenance_sw_base and hr_maintenance: a piece of software is not assigned to an
employee or a department, so these fields are hidden on software equipment.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_base", "hr_maintenance"],
    "data": [
        "views/maintenance_equipment_views.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "auto_install": True,
    "application": False,
}
