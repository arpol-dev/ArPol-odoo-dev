import base64
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, HttpCase, tagged

from .common import MID, REFERENCE_RAW, DiscoveryCase

ODOO = "myc_odoo-v18_1"
ROOT_KEY = f"machine:{MID}"
ODOO_KEY = f"container:{MID}:{ODOO}"


class TestWizard(DiscoveryCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["maintenance.discovery.import.wizard"]
        cls.old_os = cls.Equipment.create({
            "name": "Old server", "equipment_kind": "software", "install_type": "os",
        })
        cls.old_container = cls.Equipment.create({
            "name": "Legacy odoo", "equipment_kind": "software",
            "install_type": "docker_container",
        })

    def wizard(self, raw=REFERENCE_RAW, **values):
        return self.Wizard.create({
            "discovery_file": base64.b64encode(raw), "filename": "arpol.json", **values,
        })

    @staticmethod
    def line(wizard, key):
        return wizard.line_ids.filtered(lambda line: line.key == key)

    # ------------------------------------------------------------------ analyse
    def test_analyse_lists_creations(self):
        wizard = self.wizard()
        self.assertEqual(wizard.state, "upload")
        action = wizard.action_analyse()
        # the reopened dialog keeps its title
        self.assertEqual(action["name"], "Import Discovery")
        self.assertEqual(wizard.action_back()["name"], "Import Discovery")
        wizard.action_analyse()
        self.assertEqual(wizard.state, "preview")
        self.assertFalse(wizard.host_id)
        self.assertTrue(wizard.line_ids)
        self.assertEqual(set(wizard.line_ids.mapped("action")), {"create"})
        root = self.line(wizard, ROOT_KEY)
        self.assertEqual(root.model, "maintenance.equipment")
        self.assertTrue(root.label)
        self.assertFalse(root.match_id)
        self.assertFalse(self.Equipment.search([("discovery_key", "=", ROOT_KEY)]))

    def test_lines_sorted_by_action(self):
        self.Importer._apply(REFERENCE_RAW)
        data = self.reference()
        data["sections"]["docker"]["data"]["containers"] = [
            c for c in data["sections"]["docker"]["data"]["containers"] if c["name"] != ODOO
        ]
        wizard = self.wizard(json.dumps(data).encode())
        wizard.action_analyse()
        actions = wizard.line_ids.mapped("action")
        self.assertIn("missing", actions)
        order = ["create", "update", "unchanged", "missing"]
        self.assertEqual(actions, sorted(actions, key=order.index))
        self.assertEqual(self.line(wizard, ODOO_KEY).action, "missing")

    def test_deleted_lines_are_shown(self):
        self.Importer._apply(REFERENCE_RAW)
        data = self.reference()
        self.odoo_instance(data)["mount_repos"] = []
        wizard = self.wizard(json.dumps(data).encode())
        wizard.action_analyse()
        deleted = wizard.line_ids.filtered("deleted")
        self.assertTrue(deleted)
        self.assertEqual(set(deleted.mapped("action")), {"missing"})
        self.assertEqual(set(deleted.mapped("model")), {"docker.component"})
        self.assertFalse(wizard.line_ids.filtered(
            lambda l: l.action == "missing" and not l.deleted and l.model == "docker.component"
        ))

    def test_invalid_file_refused(self):
        with self.assertRaisesRegex(UserError, "JSON"):
            self.wizard(b"nope").action_analyse()
        with self.assertRaisesRegex(UserError, "schema"):
            self.wizard(b'{"schema_version": 3}').action_analyse()
        with self.assertRaises(UserError):
            self.Wizard.create({}).action_analyse()

    # ------------------------------------------------------------------ apply
    def test_apply_creates_tree_and_second_pass_unchanged(self):
        wizard = self.wizard()
        wizard.action_analyse()
        customer = self.env["res.partner"].create({"name": "Client"})
        wizard.customer_id = customer
        wizard.action_apply()
        self.assertEqual(wizard.state, "done")
        root = self.by_key(ROOT_KEY)
        self.assertEqual(wizard.root_equipment_id, root)
        self.assertEqual(root.customer_id, customer)
        self.assertTrue(root.last_discovery)

        second = self.wizard()
        second.action_analyse()
        self.assertEqual(second.host_id, root.physical_host_id)
        second.customer_id = customer
        second.action_refresh()
        self.assertEqual(set(second.line_ids.mapped("action")), {"unchanged"})

    def test_hostname_conflict(self):
        """A file of another host name under a known key: no preview, apply refused, until
        the user confirms it is the same server, renamed."""
        root = self.Importer._apply(REFERENCE_RAW)
        data = self.reference()
        data["sections"]["machine"]["data"]["hostname"] = "clone"
        wizard = self.wizard(json.dumps(data).encode())
        wizard.action_analyse()
        self.assertEqual(wizard.state, "preview")
        self.assertEqual(wizard.hostname_conflict, "arpol")
        self.assertFalse(wizard.line_ids)
        with self.assertRaisesRegex(UserError, "clone"):
            wizard.action_apply()
        wizard.same_server = True
        wizard.action_refresh()
        self.assertTrue(wizard.line_ids)
        self.assertEqual(self.line(wizard, ROOT_KEY).action, "update")
        wizard.action_apply()
        self.assertEqual(wizard.root_equipment_id, root)
        self.assertEqual(root.discovery_hostname, "clone")

    def test_match_attaches_existing_equipment(self):
        wizard = self.wizard()
        wizard.action_analyse()
        self.line(wizard, ROOT_KEY).match_id = self.old_os
        self.line(wizard, ODOO_KEY).match_id = self.old_container
        wizard.action_refresh()
        self.assertEqual(self.line(wizard, ROOT_KEY).action, "update")
        self.assertEqual(self.line(wizard, ROOT_KEY).match_id, self.old_os)
        wizard.action_apply()
        self.assertEqual(self.old_os.discovery_key, ROOT_KEY)
        self.assertEqual(self.old_container.discovery_key, ODOO_KEY)
        self.assertEqual(self.by_key(ROOT_KEY), self.old_os)
        self.assertEqual(wizard.root_equipment_id, self.old_os)

    def test_suggested_match_by_name(self):
        self.old_os.name = "arpol"
        wizard = self.wizard()
        wizard.action_analyse()
        self.assertEqual(self.line(wizard, ROOT_KEY).match_id, self.old_os)
        self.assertEqual(self.line(wizard, ROOT_KEY).action, "update")
        # the user can drop the suggestion
        self.line(wizard, ROOT_KEY).match_id = False
        wizard.action_apply()
        self.assertNotEqual(self.by_key(ROOT_KEY), self.old_os)

    def test_apply_replans_from_the_file(self):
        wizard = self.wizard()
        wizard.action_analyse()
        self.assertEqual(set(wizard.line_ids.mapped("action")), {"create"})
        # the server was imported meanwhile: the preview is stale
        self.Importer._apply(REFERENCE_RAW)
        count = self.Equipment.search_count([("discovery_key", "like", MID)])
        wizard.action_apply()
        self.assertEqual(self.Equipment.search_count([("discovery_key", "like", MID)]), count)

    def test_match_restricted_to_sensible_candidates(self):
        hardware = self.Equipment.create({"name": "Rack", "equipment_kind": "hardware"})
        other_software = self.Equipment.create({
            "name": "Some package", "equipment_kind": "software", "install_type": "package",
        })
        keyed = self.Equipment.create({
            "name": "Known", "equipment_kind": "software", "install_type": "os",
            "discovery_key": "machine:other",
        })
        for key, bad in (
            (ROOT_KEY, hardware), (ROOT_KEY, other_software), (ROOT_KEY, keyed),
            (ODOO_KEY, hardware), (ODOO_KEY, keyed), (ODOO_KEY, other_software),
            (ODOO_KEY, self.old_os),
        ):
            wizard = self.wizard()
            wizard.action_analyse()
            self.line(wizard, key).match_id = bad
            with self.assertRaises(UserError, msg=f"{key} / {bad.name}"):
                wizard.action_apply()
            with self.assertRaises(UserError):
                wizard.action_refresh()
        # a line that cannot be matched
        wizard = self.wizard()
        wizard.action_analyse()
        other = wizard.line_ids.filtered(lambda l: l.model != "maintenance.equipment")[:1]
        self.assertFalse(other.matchable)
        other.match_id = self.old_container
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_duplicate_choice_surfaces_importer_error(self):
        keys = [
            f"container:{MID}:{c['name']}"
            for c in self.reference()["sections"]["docker"]["data"]["containers"]
        ][:2]
        wizard = self.wizard()
        wizard.action_analyse()
        for key in keys:
            self.line(wizard, key).match_id = self.old_container
        with self.assertRaisesRegex(UserError, "several discovered objects"):
            wizard.action_apply()
        with self.assertRaisesRegex(UserError, "several discovered objects"):
            wizard.action_refresh()

    def test_container_match_accepts_stack_or_untyped(self):
        stack = self.Equipment.create({
            "name": "Old stack", "equipment_kind": "software", "install_type": "compose_stack",
        })
        untyped = self.Equipment.create({"name": "Untyped", "equipment_kind": "software"})
        names = [
            c["name"] for c in self.reference()["sections"]["docker"]["data"]["containers"]
        ]
        wizard = self.wizard()
        wizard.action_analyse()
        self.line(wizard, f"container:{MID}:{names[0]}").match_id = stack
        self.line(wizard, f"container:{MID}:{names[1]}").match_id = untyped
        wizard.action_apply()
        self.assertEqual(stack.discovery_key, f"container:{MID}:{names[0]}")
        self.assertEqual(untyped.discovery_key, f"container:{MID}:{names[1]}")

    def test_missing_filter(self):
        self.Importer._apply(REFERENCE_RAW)
        data = self.reference()
        data["sections"]["docker"]["data"]["containers"] = [
            c for c in data["sections"]["docker"]["data"]["containers"] if c["name"] != ODOO
        ]
        self.Importer._apply(data)
        view = self.env.ref("maintenance_sw_discovery.hr_equipment_view_search")
        self.assertIn("missing_since_discovery", view.get_combined_arch())
        found = self.Equipment.search([("missing_since_discovery", "=", True)])
        self.assertEqual(found, self.container(ODOO))
        arch = self.env["maintenance.equipment"].get_view(view_type="search")["arch"]
        self.assertIn('name="missing_since_discovery"', arch)

    def test_form_flow(self):
        form = Form(self.Wizard)
        form.discovery_file = base64.b64encode(REFERENCE_RAW)
        wizard = form.save()
        wizard.action_analyse()
        with Form(wizard) as preview:
            self.assertTrue(len(preview.line_ids))
            preview.customer_id = self.env["res.partner"].create({"name": "Client"})
        wizard.action_apply()
        self.assertEqual(wizard.state, "done")

    def test_back_and_open(self):
        wizard = self.wizard()
        wizard.action_analyse()
        wizard.action_back()
        self.assertEqual(wizard.state, "upload")
        self.assertFalse(wizard.line_ids)
        wizard.action_analyse()
        wizard.action_apply()
        action = wizard.action_open_root()
        self.assertEqual(action["res_model"], "maintenance.equipment")
        self.assertEqual(action["res_id"], wizard.root_equipment_id.id)
        line = self.wizard()
        line.action_analyse()
        existing = line.line_ids.filtered(lambda l: l.record_ref)[:1]
        self.assertEqual(existing.action_open()["res_id"], int(existing.record_ref.split(",")[1]))

    def test_managers_only(self):
        """The ACL keeps plain users out of the wizard; a manager can use it."""
        plain = self.env["res.users"].create({
            "name": "Plain", "login": "plain-user",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        manager = self.env["res.users"].create({
            "name": "Manager", "login": "manager-user",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("maintenance.group_equipment_manager").id,
            ])],
        })
        data = {"discovery_file": base64.b64encode(REFERENCE_RAW), "filename": "a.json"}
        with self.assertRaises(AccessError):
            self.Wizard.with_user(plain).create(data)
        wizard = self.wizard()
        with self.assertRaises(AccessError):
            wizard.with_user(plain).read(["state"])
        as_manager = self.Wizard.with_user(manager).create(data)
        as_manager.action_analyse()
        self.assertEqual(as_manager.state, "preview")
        as_manager.action_apply()
        self.assertEqual(as_manager.state, "done")

    def test_actions_refuse_non_managers(self):
        """Second layer. No non-manager can reach the record through the ACL, so the guard is
        exercised with sudo() kept on the plain user (env.user stays the plain user)."""
        plain = self.env["res.users"].create({
            "name": "Plain", "login": "plain-user",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        wizard = self.wizard()
        wizard.action_analyse()
        as_plain = wizard.with_user(plain).sudo()
        self.assertFalse(as_plain.env.user.has_group("maintenance.group_equipment_manager"))
        for action in ("action_analyse", "action_refresh", "action_apply", "action_back"):
            with self.assertRaises(AccessError, msg=action):
                getattr(as_plain, action)()
        self.assertEqual(wizard.state, "preview")

    def test_menu_for_managers(self):
        menu = self.env.ref("maintenance_sw_discovery.menu_discovery_import")
        self.assertEqual(menu.parent_id, self.env.ref("maintenance_sw_base.menu_sw_config"))
        self.assertEqual(menu.groups_id, self.env.ref("maintenance.group_equipment_manager"))
        self.assertEqual(menu.action.res_model, "maintenance.discovery.import.wizard")
        self.assertEqual(menu.action.target, "new")

    def test_equipment_discovery_fields_in_form(self):
        view = self.env["maintenance.equipment"].get_view(view_type="form")
        for name in ("discovery_key", "discovery_hostname", "last_discovery",
                     "missing_since_discovery"):
            self.assertIn(f'name="{name}"', view["arch"])


@tagged("post_install", "-at_install")
class TestScriptServed(HttpCase):
    def test_script_is_served(self):
        response = self.url_open("/maintenance_sw_discovery/static/discover.sh")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith("#!/usr/bin/env bash"))
