from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger


class TestOdooDatabase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.equipment = cls.env["maintenance.equipment"].create({
            "name": "myc_odoo-v18_1",
            "equipment_kind": "software",
            "install_type": "docker_container",
        })
        cls.repository = cls.env["git.repository"].create(
            {"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"}
        )
        cls.image = cls.env["docker.image"].create({"repository": "mirror/odoo"})
        cls.component = cls.env["docker.component"].create(
            {"repository_id": cls.repository.id, "image_id": cls.image.id}
        )
        cls.database = cls.env["maintenance.odoo.database"].create({
            "name": "arpol.fr",
            "equipment_id": cls.equipment.id,
            "module_ids": [
                (0, 0, {"name": "base", "installed_version": "18.0.1.3"}),
                (0, 0, {"name": "date_range", "component_id": cls.component.id}),
            ],
        })

    def test_create_and_count(self):
        self.assertEqual(self.database.module_count, 2)
        self.assertTrue(self.database.active)
        self.assertEqual(self.database.module_ids[0].state, "installed")
        self.assertEqual(self.equipment.odoo_database_count, 1)
        self.assertEqual(self.equipment.odoo_database_ids, self.database)

    def test_unique_database_per_equipment(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env["maintenance.odoo.database"].create(
                {"name": "arpol.fr", "equipment_id": self.equipment.id}
            )

    def test_unique_module_per_database(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env["maintenance.odoo.module"].create(
                {"name": "base", "database_id": self.database.id}
            )

    def test_repository_follows_component(self):
        module = self.database.module_ids.filtered(lambda m: m.name == "date_range")
        self.assertEqual(module.repository_id, self.repository)
        base = self.database.module_ids.filtered(lambda m: m.name == "base")
        self.assertFalse(base.repository_id)
        module.component_id = False
        self.assertFalse(module.repository_id)

    def test_equipment_deletion_cascades(self):
        modules = self.database.module_ids
        self.equipment.unlink()
        self.assertFalse(self.database.exists())
        self.assertFalse(modules.exists())

    def test_component_deletion_keeps_module(self):
        module = self.database.module_ids.filtered(lambda m: m.name == "date_range")
        self.component.unlink()
        self.assertTrue(module.exists())
        self.assertFalse(module.component_id)

    def test_action_view_odoo_databases(self):
        action = self.equipment.action_view_odoo_databases()
        self.assertEqual(action["res_model"], "maintenance.odoo.database")
        found = self.env["maintenance.odoo.database"].search(action["domain"])
        self.assertEqual(found, self.database)

    def test_name_search_on_equipment(self):
        found = self.env["maintenance.odoo.database"].search([("display_name", "ilike", "myc_odoo-v18")])
        self.assertIn(self.database, found)

    def test_views(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn("odoo_database_count", arch)
        for model in ("maintenance.odoo.database", "maintenance.odoo.module"):
            for view_type in ("list", "search"):
                self.env[model].get_view(view_type=view_type)
        self.env["maintenance.odoo.database"].get_view(view_type="form")
        self.assertEqual(
            self.env.ref("maintenance_sw_odoo.menu_odoo_database").parent_id,
            self.env.ref("maintenance_sw_base.menu_sw_config"),
        )
        self.assertEqual(
            self.env.ref("maintenance_sw_odoo.menu_odoo_module").parent_id,
            self.env.ref("maintenance_sw_base.menu_sw_config"),
        )


class TestOdooMultiCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Company A test"})
        cls.company_b = cls.env["res.company"].create({"name": "Company B test"})
        cls.databases = {}
        cls.modules = {}
        for company in (cls.company_a, cls.company_b):
            equipment = cls.env["maintenance.equipment"].create({
                "name": f"odoo {company.name}",
                "equipment_kind": "software",
                "install_type": "docker_container",
                "company_id": company.id,
            })
            database = cls.env["maintenance.odoo.database"].create(
                {"name": "prod", "equipment_id": equipment.id}
            )
            cls.databases[company] = database
            cls.modules[company] = cls.env["maintenance.odoo.module"].create(
                {"name": "base", "database_id": database.id}
            )
        cls.user_b = new_test_user(
            cls.env,
            login="maintenance_sw_odoo_user_b",
            groups="base.group_user,maintenance.group_equipment_manager",
            company_id=cls.company_b.id,
            company_ids=[(6, 0, cls.company_b.ids)],
        )

    def test_databases_follow_equipment_company(self):
        Database = self.env["maintenance.odoo.database"].with_user(self.user_b)
        visible = Database.search([("id", "in", [d.id for d in self.databases.values()])])
        self.assertEqual(visible, self.databases[self.company_b])
        with self.assertRaises(AccessError):
            Database.browse(self.databases[self.company_a].id).read(["name"])

    def test_modules_follow_equipment_company(self):
        Module = self.env["maintenance.odoo.module"].with_user(self.user_b)
        visible = Module.search([("id", "in", [m.id for m in self.modules.values()])])
        self.assertEqual(visible, self.modules[self.company_b])
        with self.assertRaises(AccessError):
            Module.browse(self.modules[self.company_a].id).read(["name"])
