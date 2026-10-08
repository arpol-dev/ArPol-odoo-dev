"""Shared fixtures of the importer tests.

tests/data/reference_0k_odoo.json is the output of static/discover.sh on the zerok_odoo scenario
(tests/script/zerok_odoo: a 0k server with an Odoo 18 container, its Postgres and a frontend; a
git checkout mounted over the dev addons, overriding the ArPol-odoo-dev repository of the image;
two Odoo databases), frozen so that the importer tests do not depend on bash. Regenerate it after
a change of the script or of the scenario, from an Odoo shell (`odoo shell -d <db>`, the module
being in the addons path):

    import json
    from odoo.addons.maintenance_sw_discovery.tests.common import REFERENCE_PATH
    from odoo.addons.maintenance_sw_discovery.tests.test_script import run_scenario
    with open(REFERENCE_PATH, "w") as handle:
        json.dump(run_scenario("zerok_odoo"), handle, indent=1, ensure_ascii=False)
        handle.write("\\n")

then review the diff: the importer tests assert values of this file.
"""

import copy
import json
import os

from odoo.tests import TransactionCase

REFERENCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                              "reference_0k_odoo.json")
with open(REFERENCE_PATH, "rb") as _handle:
    REFERENCE_RAW = _handle.read()
REFERENCE = json.loads(REFERENCE_RAW)
MID = REFERENCE["sections"]["machine"]["data"]["machine_id"]


class DiscoveryCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Importer = cls.env["maintenance.discovery.importer"]
        cls.Equipment = cls.env["maintenance.equipment"].with_context(active_test=False)
        cls.Image = cls.env["docker.image"]
        cls.Component = cls.env["docker.component"]
        cls.Database = cls.env["maintenance.odoo.database"].with_context(active_test=False)
        cls.Module = cls.env["maintenance.odoo.module"].with_context(active_test=False)

    @staticmethod
    def reference():
        """A fresh copy of the reference discovery (tests change it freely)."""
        return copy.deepcopy(REFERENCE)

    def by_key(self, key):
        return self.Equipment.search([("discovery_key", "=", key)])

    def container(self, name, mid=MID):
        return self.by_key(f"container:{mid}:{name}")

    def odoo_instance(self, data):
        return data["sections"]["odoo"]["data"]["instances"][0]

    def docker_container(self, data, name):
        containers = data["sections"]["docker"]["data"]["containers"]
        return next(c for c in containers if c["name"] == name)
