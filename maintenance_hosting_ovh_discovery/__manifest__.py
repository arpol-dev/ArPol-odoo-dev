# maintenance_hosting_ovh_discovery/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - OVHcloud Discovery",
    "version": "18.0.1.0.0",
    "summary": "Recognize the OVHcloud physical host of a discovered server by its IP address",
    "description": """
Maintenance - OVHcloud Discovery
================================

Glue between maintenance_hosting_ovh and maintenance_sw_discovery: when a discovered server is
not attached to a physical host yet, its IP addresses are looked up among the OVH VPS (addresses
listed by the OVH API) and dedicated servers (main address of the server) to propose the linked
physical host.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_hosting_ovh", "maintenance_sw_discovery"],
    "data": [],
    "license": "AGPL-3",
    "installable": True,
    "auto_install": True,
    "application": False,
}
