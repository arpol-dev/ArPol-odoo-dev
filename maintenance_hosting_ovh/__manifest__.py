# maintenance_hosting_ovh/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - OVHcloud Hosting",
    "version": "18.0.1.0.0",
    "summary": "Physical hosts and domain names from the OVHcloud services synchronized by ovh_api",
    "description": """
Maintenance - OVHcloud Hosting
==============================

Bridges ovh_api and the maintenance software inventory: each synchronized OVH VPS, dedicated
server or web hosting becomes a physical host, each OVH domain a domain name (expiration and
renewal kept up to date). Services that disappear from OVH archive their host or domain.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_base", "ovh_api"],
    "data": [
        "data/res_partner_data.xml",
        "views/maintenance_host_views.xml",
        "views/maintenance_domain_views.xml",
        "views/ovh_service_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
