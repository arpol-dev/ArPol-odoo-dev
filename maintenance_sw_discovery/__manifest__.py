# maintenance_sw_discovery/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Server Discovery",
    "version": "18.0.1.0.0",
    "summary": "Describe a server with a read-only script and import it into the software inventory",
    "description": """
Maintenance - Server Discovery
==============================

A read-only bash script (static/discover.sh) describes a server as JSON: machine, operating
system, platforms (Proxmox VE, 0k, Cloudron, Docker), containers and Odoo instances.

The importer turns such a file into a plan (what is created, updated, unchanged or missing),
then applies it: operating system, Proxmox VE and its guests, 0k stack, Cloudron instance and
applications, containers with their image, mounts and git components, Odoo databases and
installed modules linked to the component that provides them. Every discovered object keeps a
discovery key, so that a new discovery of the same server updates the tree instead of
duplicating it; manual entries (name, notes, forced host or customer) are kept.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_odoo"],
    "data": [
        "security/ir.model.access.csv",
        "views/discovery_import_wizard_views.xml",
        "views/maintenance_equipment_views.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
