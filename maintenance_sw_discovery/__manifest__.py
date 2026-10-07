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
system, platforms (Proxmox VE, 0k, Cloudron, Docker), containers and Odoo instances. The
result is meant to be imported into the software inventory.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_odoo"],
    "data": [],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
