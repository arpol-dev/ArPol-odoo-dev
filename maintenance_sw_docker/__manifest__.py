# maintenance_sw_docker/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Docker Inventory",
    "version": "18.0.1.0.0",
    "summary": "Docker images, mounts and the code repositories they bring, per container",
    "description": """
Maintenance - Docker Inventory
==============================

Describes what really runs in a container: its image (and the images it is built FROM), the
git repositories each image contains, and the mounts that add or override repositories at run
time. The container's effective components are computed from all of them.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_base"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
