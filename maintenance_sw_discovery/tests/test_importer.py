import json
from datetime import datetime

from odoo.exceptions import UserError

from .common import MID, REFERENCE_RAW, DiscoveryCase
from .test_script import run_scenario

ODOO = "myc_odoo-v18_1"
ROOT_KEY = f"machine:{MID}"
STACK_KEY = f"stack:{MID}:/opt/apps/myc-deploy"
ODOO_DIGEST = "sha256:f46e1a70b686d85611004e4da6456e71680ab0f22f4ba801de95b54fbd90757e"
NEW_DIGEST = "sha256:" + "9" * 64


class TestImporter(DiscoveryCase):
    # ------------------------------------------------------------------ parse
    def test_parse_refuses_invalid_files(self):
        with self.assertRaisesRegex(UserError, "JSON"):
            self.Importer._parse(b"not a json file")
        with self.assertRaisesRegex(UserError, "schema"):
            self.Importer._parse('{"schema_version": 2, "sections": {}}')
        with self.assertRaisesRegex(UserError, "schema"):
            self.Importer._parse(b"[1, 2]")
        with self.assertRaisesRegex(UserError, "machine"):
            self.Importer._parse('{"schema_version": 1, "sections": {}}')
        self.assertEqual(self.Importer._parse(REFERENCE_RAW)["schema_version"], 1)

    # ------------------------------------------------------------------ first import
    def test_first_import_tree(self):
        root = self.Importer._apply(REFERENCE_RAW)
        self.assertEqual(root.discovery_key, ROOT_KEY)
        self.assertEqual(root.name, "Debian (arpol)")
        self.assertEqual(root.equipment_kind, "software")
        self.assertEqual(root.install_type, "os")
        self.assertEqual(root.deployment_method_id,
                         self.env.ref("maintenance_sw_base.deployment_method_manual"))
        self.assertEqual(root.software_product_id.name, "Debian")
        self.assertEqual(root.software_version_id.name, "10")
        self.assertEqual(root.software_version_id.sequence, 1000)
        self.assertFalse(root.parent_id)
        self.assertTrue(root.last_discovery)
        self.assertFalse(root.missing_since_discovery)

        stack = self.by_key(STACK_KEY)
        self.assertEqual(stack.parent_id, root)
        self.assertEqual(stack.install_type, "compose_stack")
        self.assertEqual(stack.install_path, "/opt/apps/myc-deploy")
        myc = self.env.ref("maintenance_sw_base.deployment_method_myc")
        self.assertEqual(stack.deployment_method_id, myc)

        containers = self.Equipment.search([("discovery_key", "=like", f"container:{MID}:%")])
        self.assertEqual(sorted(containers.mapped("name")),
                         ["myc_frontend_1", ODOO, "myc_postgres_1"])
        for container in containers:
            self.assertEqual(container.parent_id, stack)
            self.assertEqual(container.install_type, "docker_container")
            self.assertEqual(container.deployment_method_id, myc)
            self.assertEqual(container.container_name, container.name)
            self.assertTrue(container.last_discovery)

    def test_first_import_image_mounts_components(self):
        self.Importer._apply(REFERENCE_RAW)
        odoo = self.container(ODOO)
        image = odoo.docker_image_id
        self.assertEqual(image.registry, "docker.0k.io")
        self.assertEqual(image.repository, "mirror/odoo")
        self.assertEqual(image.tag, "rc_18.0-ARPOL-ODOO-DEV-18.0")
        self.assertEqual(image.digest, ODOO_DIGEST)
        self.assertEqual(image.build_date, datetime(2026, 9, 29, 21, 0, 0))
        self.assertEqual(image.version_id.display_name, "Odoo 18.0")
        self.assertEqual(image.version_id.sequence, 1800)
        self.assertEqual(odoo.software_version_id, image.version_id)
        # A locally built image has no registry digest: its image id stands for it.
        postgres = self.container("myc_postgres_1")
        self.assertEqual(postgres.docker_image_id.digest, "sha256:" + "2" * 64)
        self.assertEqual(postgres.docker_image_id.repository, "postgres")
        self.assertEqual(postgres.docker_image_id.version_id.display_name, "PostgreSQL 16")

        # image components, from repos.yaml (structured by the script)
        components = {c.path: c for c in image.component_ids}
        self.assertEqual(sorted(components), [
            "/opt/odoo/custom/src/ArPol-odoo-dev", "/opt/odoo/custom/src/odoo",
            "/opt/odoo/custom/src/private-addons",
        ])
        core = components["/opt/odoo/custom/src/odoo"]
        self.assertEqual(core.repository_id.url, "https://github.com/OCA/OCB.git")
        self.assertEqual(core.repository_id.name, "OCA/OCB")
        self.assertEqual(core.ref, "18.0")
        self.assertEqual(core.merges, "origin 18.0")
        self.assertEqual(core.role, "core")
        dev = components["/opt/odoo/custom/src/ArPol-odoo-dev"]
        self.assertEqual(dev.repository_id.url,
                         "https://git.0k.io/mirror/arpol/ArPol-odoo-dev.git")
        self.assertEqual(dev.repository_id.upstream_id.url,
                         "https://github.com/arpol/ArPol-odoo-dev.git")
        private = components["/opt/odoo/custom/src/private-addons"]
        # no target: the remote of the first merge; the commit is the one found by git
        self.assertEqual(private.repository_id.url,
                         "https://git.example.com/arpol/private.git")
        self.assertEqual(private.commit, "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(private.ref, "18.0")

        # mounts
        mounts = {m.destination: m for m in odoo.mount_ids}
        self.assertEqual(sorted(mounts), ["/opt/odoo/auto/dev", "/var/lib/odoo"])
        dev_mount = mounts["/opt/odoo/auto/dev"]
        self.assertEqual(dev_mount.source, "/srv/datastore/data/odoo-v18/addons")
        self.assertEqual((dev_mount.mount_type, dev_mount.mode, dev_mount.usage),
                         ("bind", "rw", "repos"))
        data = mounts["/var/lib/odoo"]
        self.assertEqual((data.mount_type, data.source, data.usage),
                         ("volume", "myc_odoo-v18-data", "data"))
        # the mounted checkout overrides the image's ArPol-odoo-dev
        self.assertEqual(len(dev_mount.component_ids), 1)
        mounted = dev_mount.component_ids
        self.assertEqual(mounted.path, "/opt/odoo/auto/dev/ArPol-odoo-dev")
        self.assertEqual(mounted.ref, "18.0-maintenance-sw")
        self.assertEqual(mounted.commit, "4444dddd4444dddd4444dddd4444dddd4444dddd")
        self.assertEqual(mounted.overrides_id, dev)
        # the same repository as the upstream of the mirror
        self.assertEqual(mounted.repository_id, dev.repository_id.upstream_id)
        self.assertNotIn(dev, odoo.effective_component_ids)
        self.assertIn(mounted, odoo.effective_component_ids)
        # links outside the image are recorded as runtime changes
        self.assertIn("/opt/odoo/auto/addons/ovh_api -> /opt/odoo/auto/dev/ovh_connector/ovh_api",
                      odoo.runtime_changes)

    def test_first_import_odoo_databases(self):
        root = self.Importer._apply(REFERENCE_RAW)
        odoo = self.container(ODOO)
        components = {c.path: c for c in odoo.docker_image_id.component_ids}
        mounted = odoo.mount_ids.component_ids
        databases = {d.name: d for d in odoo.odoo_database_ids}
        self.assertEqual(sorted(databases), ["arpol", "arpol_test"])
        self.assertTrue(databases["arpol"].last_discovery)
        modules = {m.name: m for m in databases["arpol"].module_ids}
        self.assertEqual(sorted(modules), ["base", "maintenance_sw_base", "old_module", "sale"])
        self.assertEqual(modules["base"].installed_version, "18.0.1.3")
        self.assertEqual(modules["maintenance_sw_base"].state, "to_upgrade")
        self.assertEqual(modules["old_module"].state, "to_remove")
        self.assertFalse(modules["old_module"].installed_version)
        # /opt/odoo/auto/addons/base -> /opt/odoo/custom/src/odoo/odoo/addons/base
        self.assertEqual(modules["base"].component_id, components["/opt/odoo/custom/src/odoo"])
        self.assertEqual(modules["sale"].component_id, components["/opt/odoo/custom/src/odoo"])
        # first addons_path directory holding it: the mounted checkout
        self.assertEqual(modules["maintenance_sw_base"].component_id, mounted)
        self.assertFalse(modules["old_module"].component_id)
        test_modules = {m.name: m for m in databases["arpol_test"].module_ids}
        # linked to a directory that is no git checkout
        self.assertFalse(test_modules["ovh_api"].component_id)

        # the discovery file is attached to the root
        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", "maintenance.equipment"), ("res_id", "=", root.id),
        ])
        self.assertEqual(len(attachment), 1)
        self.assertEqual(attachment.name, "discovery-arpol-2026-10-08.json")
        self.assertEqual(json.loads(attachment.raw)["schema_version"], 1)

    def test_base_module_from_the_server_directory(self):
        """base is in the server's own odoo/addons, never in the addons_path: core component."""
        data = self.reference()
        instance = self.odoo_instance(data)
        for directory in instance["addons"].values():
            if "base" in directory:
                directory.remove("base")
        instance["addons_links"] = [link for link in instance["addons_links"]
                                    if not link["link"].endswith("/base")]
        self.Importer._apply(data)
        odoo = self.container(ODOO)
        core = odoo.docker_image_id.component_ids.filtered(lambda c: c.role == "core")
        modules = odoo.odoo_database_ids.module_ids
        self.assertEqual(modules.filtered(lambda m: m.name == "base").component_id, core)
        # a module found nowhere (removed from the disk) has no component
        self.assertFalse(modules.filtered(lambda m: m.name == "old_module").component_id)

    # ------------------------------------------------------------------ re-import
    def _all_records(self, root):
        tree = self.Equipment.search([("id", "child_of", root.id)])
        images = tree.docker_image_id
        mounts = tree.mount_ids
        components = images.component_ids | mounts.component_ids
        databases = self.Database.search([("equipment_id", "in", tree.ids)])
        modules = self.Module.search([("database_id", "in", databases.ids)])
        return [tree, images, mounts, components, databases, modules,
                components.repository_id, tree.software_version_id]

    def test_second_identical_import_changes_nothing(self):
        root = self.Importer._apply(REFERENCE_RAW)
        records = self._all_records(root)
        old = datetime(2000, 1, 1)
        for recordset in records:
            recordset.flush_recordset()
            self.env.cr.execute(
                f"UPDATE {recordset._table} SET write_date = %s WHERE id IN %s",
                (old, tuple(recordset.ids)),
            )
        self.env.invalidate_all()

        plan = self.Importer._plan(self.reference())
        self.assertTrue(plan)
        self.assertEqual({op["action"] for op in plan}, {"unchanged"},
                         [op for op in plan if op["action"] != "unchanged"])
        self.assertEqual(self.Importer._apply(REFERENCE_RAW), root)
        self.env.flush_all()
        self.env.invalidate_all()
        for recordset in records:
            self.assertEqual(set(recordset.mapped("write_date")), {old}, recordset)
        # one attachment per import
        self.assertEqual(self.env["ir.attachment"].search_count([
            ("res_model", "=", "maintenance.equipment"), ("res_id", "=", root.id),
        ]), 2)

    def test_modified_import(self):
        root = self.Importer._apply(REFERENCE_RAW)
        odoo = self.container(ODOO)
        old_image = odoo.docker_image_id
        frontend = self.container("myc_frontend_1")

        data = self.reference()
        containers = data["sections"]["docker"]["data"]["containers"]
        containers[:] = [c for c in containers if c["name"] != "myc_frontend_1"]
        odoo_image = self.docker_container(data, ODOO)["image_inspect"]
        odoo_image["RepoDigests"] = [f"docker.0k.io/mirror/odoo@{NEW_DIGEST}"]
        instance = self.odoo_instance(data)
        arpol = instance["databases"]["items"][0]
        arpol["modules"] = [m for m in arpol["modules"] if m["name"] != "sale"]
        instance["databases"]["items"] = [arpol]

        plan = {op["key"]: op for op in self.Importer._plan(data)}
        self.assertEqual(plan[f"container:{MID}:myc_frontend_1"]["action"], "missing")
        self.assertEqual(plan[f"container:{MID}:{ODOO}"]["action"], "update")
        self.assertEqual(plan[f"container:{MID}:{ODOO}"]["changes"], [
            "Docker Image: mirror/odoo:rc_18.0-ARPOL-ODOO-DEV-18.0 (f46e1a70b686) → "
            "mirror/odoo:rc_18.0-ARPOL-ODOO-DEV-18.0",
        ])
        self.assertEqual(plan[ROOT_KEY]["action"], "unchanged")

        self.assertEqual(self.Importer._apply(data), root)
        self.assertFalse(frontend.active)
        self.assertTrue(frontend.missing_since_discovery)
        # new digest: a new image, the old one kept
        new_image = odoo.docker_image_id
        self.assertNotEqual(new_image, old_image)
        self.assertEqual(new_image.digest, NEW_DIGEST)
        self.assertTrue(old_image.exists())
        self.assertEqual(len(new_image.component_ids), 3)
        new_dev = new_image.component_ids.filtered(lambda c: c.path.endswith("ArPol-odoo-dev"))
        self.assertEqual(odoo.mount_ids.component_ids.overrides_id, new_dev)
        new_core = new_image.component_ids.filtered(lambda c: c.path.endswith("/odoo"))
        database = odoo.odoo_database_ids.filtered(lambda d: d.name == "arpol")
        modules = {m.name: m for m in database.with_context(active_test=False).module_ids}
        self.assertEqual(modules["base"].component_id, new_core)
        self.assertFalse(modules["sale"].active)
        archived = self.Database.search([("equipment_id", "=", odoo.id), ("name", "=", "arpol_test")])
        self.assertFalse(archived.active)

        # an archived container is still known by its key: no name match proposed for it
        self.Equipment.create({"name": "myc_frontend_1", "equipment_kind": "software",
                               "parent_id": root.id})
        self.assertEqual(self.Importer._suggest(REFERENCE_RAW)["matches"], {})

        # back again: unarchived
        self.Importer._apply(REFERENCE_RAW)
        self.assertTrue(frontend.active)
        self.assertFalse(frontend.missing_since_discovery)
        self.assertTrue(archived.active)
        self.assertTrue(modules["sale"].active)

    def test_failed_section_marks_nothing_missing(self):
        self.Importer._apply(REFERENCE_RAW)
        data = self.reference()
        data["sections"]["docker"] = {"status": "error", "message": "boom"}
        data["sections"]["odoo"] = {"status": "skipped", "reason": "no docker"}
        plan = self.Importer._plan(data)
        self.assertFalse([op for op in plan if op["action"] == "missing"])
        self.Importer._apply(data)
        self.assertTrue(self.container(ODOO).active)

    # ------------------------------------------------------------------ manual tree
    def test_manual_tree_is_attached(self):
        host = self.env["maintenance.host"].create({"name": "VPS arpol.fr", "host_type": "vps"})
        system = self.Equipment.create({
            "name": "Debian (arpol.fr)", "equipment_kind": "software", "install_type": "os",
            "physical_host_id": host.id,
        })
        container = self.Equipment.create({
            "name": ODOO, "equipment_kind": "software", "install_type": "docker_container",
            "parent_id": system.id, "note": "<p>Hand-written note</p>",
            "runtime_changes": "Link /opt/odoo/auto/addons/ovh_api added by hand.",
        })
        # same container name on another server: never proposed
        self.Equipment.create({"name": ODOO, "equipment_kind": "software"})

        suggestion = self.Importer._suggest(self.reference())
        self.assertEqual(suggestion["host_id"], host.id)
        self.assertEqual(suggestion["matches"], {
            ROOT_KEY: system.id, f"container:{MID}:{ODOO}": container.id,
        })

        plan = {op["key"]: op for op in self.Importer._plan(REFERENCE_RAW,
                                                            matches=suggestion["matches"])}
        self.assertEqual(plan[f"container:{MID}:{ODOO}"]["action"], "update")
        changes = plan[f"container:{MID}:{ODOO}"]["changes"]
        self.assertIn(f"Container Name: ∅ → {ODOO}", changes)
        self.assertFalse([change for change in changes if change.startswith("Install Type")])
        self.assertNotIn("name", plan[ROOT_KEY]["values"])
        self.assertIn("Deployment Method: ∅ → Manual", plan[ROOT_KEY]["changes"])
        root = self.Importer._apply(REFERENCE_RAW, matches=suggestion["matches"])
        self.assertEqual(root, system)
        self.assertEqual(system.name, "Debian (arpol.fr)")
        self.assertEqual(system.discovery_key, ROOT_KEY)
        self.assertEqual(system.physical_host_id, host)
        self.assertTrue(system.physical_host_forced)
        self.assertEqual(self.container(ODOO), container)
        self.assertEqual(container.note, "<p>Hand-written note</p>")
        self.assertTrue(container.docker_image_id)
        # the link is already mentioned: no discovery block added
        self.assertEqual(container.runtime_changes,
                         "Link /opt/odoo/auto/addons/ovh_api added by hand.")
        self.assertEqual(self.Equipment.search_count([
            ("container_name", "=", ODOO), ("discovery_key", "!=", False),
        ]), 1)
        self.assertEqual(self.Equipment.search_count([("install_type", "=", "os"),
                                                      ("name", "ilike", "arpol")]), 1)
        # the support of the attached tree is now found by key
        self.assertEqual(self.Importer._suggest(self.reference()),
                         {"host_id": host.id, "matches": {}})

    def test_runtime_changes_appended(self):
        container = self.Equipment.create({
            "name": ODOO, "equipment_kind": "software", "runtime_changes": "Patched by hand.",
        })
        self.Importer._apply(REFERENCE_RAW, matches={f"container:{MID}:{ODOO}": container.id})
        self.assertTrue(container.runtime_changes.startswith("Patched by hand.\n\nDiscovery of "))
        self.assertIn("/opt/odoo/auto/addons/ovh_api", container.runtime_changes)

    def test_host_and_customer_forced_on_root(self):
        host = self.env["maintenance.host"].create({"name": "VPS", "host_type": "vps"})
        customer = self.env["res.partner"].create({"name": "Customer"})
        root = self.Importer._apply(REFERENCE_RAW, host=host, customer=customer)
        self.assertEqual(root.physical_host_id, host)
        self.assertTrue(root.physical_host_forced)
        self.assertEqual(root.customer_id, customer)
        self.assertTrue(root.customer_forced)
        odoo = self.container(ODOO)
        self.assertEqual(odoo.physical_host_id, host)
        self.assertFalse(odoo.physical_host_forced)
        self.assertEqual(odoo.customer_id, customer)
        self.assertEqual(self.Importer._suggest(self.reference())["host_id"], host.id)

    def test_suggest_without_anything_known(self):
        self.assertEqual(self.Importer._suggest(REFERENCE_RAW), {"host_id": False, "matches": {}})


class TestImporterFixes(DiscoveryCase):
    def test_vanished_mount_deleted(self):
        self.Importer._apply(REFERENCE_RAW)
        odoo = self.container(ODOO)
        dev_mount = odoo.mount_ids.filtered(lambda m: m.destination == "/opt/odoo/auto/dev")
        mounted = dev_mount.component_ids
        image_dev = mounted.overrides_id
        self.assertNotIn(image_dev, odoo.effective_component_ids)

        data = self.reference()
        inspect = self.docker_container(data, ODOO)["inspect"]
        inspect["Mounts"] = [m for m in inspect["Mounts"] if m["Destination"] != "/opt/odoo/auto/dev"]
        self.odoo_instance(data)["mount_repos"] = []
        plan = {op["key"]: op for op in self.Importer._plan(data)}
        mount_key = f"mount:container:{MID}:{ODOO}:/opt/odoo/auto/dev"
        self.assertEqual(plan[mount_key]["action"], "missing")
        self.assertEqual(plan[mount_key]["record_id"], dev_mount.id)
        self.Importer._apply(data)
        self.assertFalse(dev_mount.exists())
        self.assertFalse(mounted.exists())
        self.assertIn(image_dev, odoo.effective_component_ids)
        self.assertEqual(odoo.mount_ids.mapped("destination"), ["/var/lib/odoo"])

    def test_vanished_mount_component_deleted(self):
        self.Importer._apply(REFERENCE_RAW)
        odoo = self.container(ODOO)
        mounted = odoo.mount_ids.component_ids
        data = self.reference()
        self.odoo_instance(data)["mount_repos"] = []
        plan = {op["key"]: op for op in self.Importer._plan(data)}
        mount_key = f"mount:container:{MID}:{ODOO}:/opt/odoo/auto/dev"
        self.assertEqual(plan[f"component:{mount_key}:/opt/odoo/auto/dev/ArPol-odoo-dev"]["action"],
                         "missing")
        self.assertEqual(plan[mount_key]["action"], "unchanged")
        self.Importer._apply(data)
        self.assertFalse(mounted.exists())
        self.assertEqual(len(odoo.mount_ids), 2)

    def test_key_of_another_company(self):
        company_a = self.env.company
        company_b = self.env["res.company"].create({"name": "Company B"})
        user = self.env["res.users"].create({
            "name": "Manager", "login": "discovery_manager",
            "company_id": company_a.id, "company_ids": [(6, 0, (company_a | company_b).ids)],
            "groups_id": [(6, 0, [self.env.ref("maintenance.group_equipment_manager").id,
                                  self.env.ref("base.group_user").id])],
        })
        importer = self.Importer.with_user(user)
        root = importer.with_company(company_b)._apply(REFERENCE_RAW)
        self.assertEqual(root.company_id, company_b)
        with self.assertRaisesRegex(UserError, "Debian \\(arpol\\)"):
            importer.with_company(company_a)._plan(REFERENCE_RAW)

    def test_inherited_host_not_forced(self):
        host = self.env["maintenance.host"].create({"name": "VPS", "host_type": "vps"})
        customer = self.env["res.partner"].create({"name": "Customer"})
        vps = self.Equipment.create({"name": "VPS arpol.fr", "physical_host_id": host.id,
                                     "customer_id": customer.id})
        system = self.Equipment.create({
            "name": "Debian (arpol.fr)", "equipment_kind": "software", "install_type": "os",
            "parent_id": vps.id,
        })
        self.assertEqual(system.physical_host_id, host)
        self.assertFalse(system.physical_host_forced)
        plan = self.Importer._plan(REFERENCE_RAW, host=host, customer=customer,
                                   matches={ROOT_KEY: system.id})
        root_op = next(op for op in plan if op["key"] == ROOT_KEY)
        for fname in ("physical_host_id", "physical_host_forced", "customer_id",
                      "customer_forced"):
            self.assertNotIn(fname, root_op["values"])
        self.Importer._apply(REFERENCE_RAW, host=host, customer=customer,
                             matches={ROOT_KEY: system.id})
        self.assertFalse(system.physical_host_forced)
        self.assertFalse(system.customer_forced)
        # another host than the inherited one is forced
        other = self.env["maintenance.host"].create({"name": "Other", "host_type": "vps"})
        self.Importer._apply(REFERENCE_RAW, host=other)
        self.assertEqual(system.physical_host_id, other)
        self.assertTrue(system.physical_host_forced)

    def test_duplicate_match_targets(self):
        system = self.Equipment.create({"name": "Debian (arpol.fr)", "equipment_kind": "software"})
        with self.assertRaisesRegex(UserError, "Debian \\(arpol.fr\\)"):
            self.Importer._plan(REFERENCE_RAW, matches={
                ROOT_KEY: system.id, f"container:{MID}:{ODOO}": system.id,
            })

    def test_runtime_changes_link_boundaries(self):
        """A link is mentioned only as a whole word: /ovh is not mentioned by /ovh_api."""
        container = self.Equipment.create({
            "name": ODOO, "equipment_kind": "software",
            "runtime_changes": "Link /opt/odoo/auto/addons/ovh_api added by hand.",
        })
        data = self.reference()
        self.odoo_instance(data)["runtime_links"] = [
            {"link": "/opt/odoo/auto/addons/ovh", "target": "/opt/odoo/auto/dev/ovh"},
            {"link": "/opt/odoo/auto/addons/ovh_api", "target": "/opt/odoo/auto/dev/x"},
        ]
        self.Importer._apply(data, matches={f"container:{MID}:{ODOO}": container.id})
        self.assertTrue(container.runtime_changes.endswith(
            ":\n/opt/odoo/auto/addons/ovh -> /opt/odoo/auto/dev/ovh"), container.runtime_changes)

    def test_repository_identity(self):
        from odoo.addons.maintenance_sw_discovery.models.discovery_importer import PlanState
        state = PlanState(self.reference(), self.env["maintenance.host"],
                          self.env["res.partner"], {})
        url = "https://***@git.example.com/arpol/mirror.git"
        key = self.Importer._plan_repository(state, url)
        self.assertEqual(key, "repo:https://git.example.com/arpol/mirror.git")
        upstream = "https://github.com/arpol/upstream.git"
        self.assertEqual(self.Importer._plan_repository(state, url, upstream), key)
        keys = [op["key"] for op in state.ops]
        self.assertLess(keys.index(f"repo:{upstream}"), keys.index(key))
        self.assertEqual(state.by_key[key]["values"]["upstream_id"], {"ref": f"repo:{upstream}"})
        # an existing repository gets the upstream as an update
        self.env["git.repository"].create({"name": "x", "url": "https://h/x.git"})
        state = PlanState(self.reference(), self.env["maintenance.host"],
                          self.env["res.partner"], {})
        self.Importer._plan_repository(state, "https://h/x.git")
        self.Importer._plan_repository(state, "https://h/x.git", upstream)
        op = state.by_key["repo:https://h/x.git"]
        self.assertEqual(op["action"], "update")
        self.assertTrue(op["changes"])


class TestImporterScenarios(DiscoveryCase):
    """The other script scenarios, run live (they need bash, as the script tests)."""

    def test_proxmox(self):
        data = run_scenario("proxmox")
        mid = data["sections"]["machine"]["data"]["machine_id"]
        hardware = self.env["maintenance.equipment"].create({"name": "Tardis"})
        host = self.env["maintenance.host"].create({
            "name": "Tardis", "host_type": "physical", "equipment_id": hardware.id,
        })
        root = self.Importer._apply(data, host=host)
        pve = self.by_key(f"pve:{mid}")
        self.assertEqual(pve.parent_id, root)
        self.assertEqual(pve.install_type, "package")
        self.assertEqual(pve.software_version_id.display_name, "Proxmox VE 8.2.7")
        guests = self.env["maintenance.host"].search([("discovery_key", "=like", f"pve-guest:{mid}:%")])
        self.assertEqual(sorted(guests.mapped("name")), ["arpol-brain", "haos", "odoo-migrate"])
        self.assertEqual(set(guests.mapped("host_type")), {"vm"})
        self.assertEqual(guests.equipment_id, hardware)
        # a guest gone: archived
        data["sections"]["proxmox"]["data"]["guests"].pop()
        plan = self.Importer._plan(data, host=host)
        self.assertEqual([op["key"] for op in plan if op["action"] == "missing"],
                         [f"pve-guest:{mid}:104"])
        self.Importer._apply(data, host=host)
        self.assertEqual(len(guests.filtered("active")), 2)
        self.assertEqual({op["action"] for op in self.Importer._plan(data, host=host)},
                         {"unchanged"})

    def test_cloudron(self):
        data = run_scenario("cloudron")
        mid = data["sections"]["machine"]["data"]["machine_id"]
        root = self.Importer._apply(data)
        cloudron = self.by_key(f"cloudron:{mid}")
        self.assertEqual(cloudron.parent_id, root)
        self.assertEqual(cloudron.software_version_id.display_name, "Cloudron 8.1.0")
        method = self.env.ref("maintenance_sw_base.deployment_method_cloudron")
        self.assertEqual(cloudron.deployment_method_id, method)
        apps = self.Equipment.search([("discovery_key", "=like", f"cloudron-app:{mid}:%")])
        self.assertEqual(len(apps), 2)
        odoo = apps.filtered(lambda app: app.version_note == "18.0.0")
        self.assertEqual(odoo.name, "Odoo (odoo.eoloa.eu)")
        self.assertEqual(odoo.parent_id, cloudron)
        self.assertEqual(odoo.deployment_method_id, method)
        self.assertEqual({op["action"] for op in self.Importer._plan(data)}, {"unchanged"})

    def test_manual_odoo(self):
        data = run_scenario("manual_odoo")
        mid = data["sections"]["machine"]["data"]["machine_id"]
        root = self.Importer._apply(data)
        odoo = self.container("odoo-web", mid=mid)
        self.assertEqual(odoo.parent_id, root)
        self.assertEqual(odoo.deployment_method_id,
                         self.env.ref("maintenance_sw_base.deployment_method_manual"))
        # no repos.yaml, the repositories are all in the mount
        self.assertFalse(odoo.docker_image_id.component_ids)
        mount = odoo.mount_ids.filtered(lambda m: m.destination == "/mnt/extra-addons")
        self.assertEqual((mount.usage, mount.mode), ("repos", "ro"))
        self.assertEqual(sorted(mount.component_ids.mapped("path")),
                         ["/mnt/extra-addons/custom", "/mnt/extra-addons/oca-web"])
        modules = {m.name: m for m in odoo.odoo_database_ids.module_ids}
        self.assertEqual(modules["web_responsive"].component_id.path, "/mnt/extra-addons/oca-web")
        self.assertFalse(modules["base"].component_id)
