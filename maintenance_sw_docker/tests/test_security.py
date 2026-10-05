from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestDockerMultiCompany(TransactionCase):
    """Mounts, and the components they bring, follow the company of their container."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Company A test"})
        cls.company_b = cls.env["res.company"].create({"name": "Company B test"})
        repository = cls.env["git.repository"].create(
            {"name": "arpol-dev/bemade-addons", "url": "https://github.com/arpol-dev/bemade-addons.git"}
        )
        cls.image = cls.env["docker.image"].create({"repository": "mirror/odoo"})
        cls.image_component = cls.env["docker.component"].create(
            {"repository_id": repository.id, "image_id": cls.image.id}
        )
        cls.mounts = {}
        cls.mount_components = {}
        for company in (cls.company_a, cls.company_b):
            container = cls.env["maintenance.equipment"].create({
                "name": f"myc_odoo-v18_1 {company.name}",
                "equipment_kind": "software",
                "install_type": "docker_container",
                "company_id": company.id,
                "docker_image_id": cls.image.id,
            })
            mount = cls.env["docker.mount"].create({
                "equipment_id": container.id,
                "source": "/srv/datastore/data/odoo-v18/repos-arpol",
                "destination": "/opt/odoo/auto/dev",
                "usage": "repos",
            })
            cls.mounts[company] = mount
            cls.mount_components[company] = cls.env["docker.component"].create(
                {"repository_id": repository.id, "mount_id": mount.id}
            )
        cls.user_b = new_test_user(
            cls.env,
            login="maintenance_sw_docker_user_b",
            groups="base.group_user,maintenance.group_equipment_manager",
            company_id=cls.company_b.id,
            company_ids=[(6, 0, cls.company_b.ids)],
        )

    def test_mounts_follow_container_company(self):
        Mount = self.env["docker.mount"].with_user(self.user_b)
        visible = Mount.search([("id", "in", [m.id for m in self.mounts.values()])])
        self.assertEqual(visible, self.mounts[self.company_b])
        with self.assertRaises(AccessError):
            Mount.browse(self.mounts[self.company_a].id).read(["source"])

    def test_mount_components_follow_container_company(self):
        Component = self.env["docker.component"].with_user(self.user_b)
        ids = [self.image_component.id] + [c.id for c in self.mount_components.values()]
        visible = Component.search([("id", "in", ids)])
        self.assertEqual(
            visible,
            self.image_component | self.mount_components[self.company_b],
            "image components are shared, mount components follow the container",
        )
